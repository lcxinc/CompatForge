//! Deterministic, side-effect-free compilation of launch requests.

#![forbid(unsafe_code)]

use compatforge_domain::{
    CapabilityReport, ContractError, CoreConfig, CpuArchitecture, GraphicsBackendKind, GraphicsSelection, HostOs,
    LaunchPlan, LaunchRequest, NativeCommand, ProviderDescriptor, RuntimeKind, RuntimeSelection, SandboxPolicy,
    TranslatorKind, TranslatorSelection, SCHEMA_VERSION_V1,
};
use compatforge_storage::AppPaths;
use std::collections::BTreeMap;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PlanError {
    InvalidConfig(ContractError),
    InvalidRequest(ContractError),
    InvalidPlan(ContractError),
    MissingRequiredCapability(String),
    NoCompatibleRuntime,
    MissingRuntimeBinding(String),
    InvalidHostPath(&'static str),
    PlanMismatch(&'static str),
    NoCompatibleTranslator,
    NoCompatibleGraphicsBackend,
}

impl fmt::Display for PlanError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidConfig(error) => write!(formatter, "invalid core config: {error}"),
            Self::InvalidRequest(error) => write!(formatter, "invalid launch request: {error}"),
            Self::InvalidPlan(error) => write!(formatter, "invalid launch plan: {error}"),
            Self::MissingRequiredCapability(capability) => {
                write!(formatter, "required capability is unavailable: {capability}")
            }
            Self::NoCompatibleRuntime => formatter.write_str("no compatible runtime provider"),
            Self::MissingRuntimeBinding(provider) => {
                write!(formatter, "runtime provider {provider} has no pinned binding")
            }
            Self::InvalidHostPath(field) => write!(formatter, "{field} must be an absolute host path"),
            Self::PlanMismatch(field) => write!(formatter, "launch plan does not match trusted context: {field}"),
            Self::NoCompatibleTranslator => formatter.write_str("no compatible architecture translator"),
            Self::NoCompatibleGraphicsBackend => formatter.write_str("no compatible graphics backend"),
        }
    }
}

impl std::error::Error for PlanError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::InvalidConfig(error) | Self::InvalidRequest(error) | Self::InvalidPlan(error) => Some(error),
            _ => None,
        }
    }
}

pub struct PolicyEngine;

impl PolicyEngine {
    /// Compile a request to a fully serializable plan without launching a process.
    pub fn compile(config: &CoreConfig, request: &LaunchRequest) -> Result<LaunchPlan, PlanError> {
        config.validate().map_err(PlanError::InvalidConfig)?;
        request.validate().map_err(PlanError::InvalidRequest)?;
        Self::check_required_capabilities(&config.capabilities, request)?;

        if !is_absolute_host_path(&config.storage_root) {
            return Err(PlanError::InvalidHostPath("storageRoot"));
        }

        let (runtime_provider, runtime_kind) = Self::select_runtime(&config.capabilities, request)?;
        let binding = config
            .runtime_bindings
            .iter()
            .find(|candidate| candidate.provider_id == runtime_provider.id)
            .ok_or_else(|| PlanError::MissingRuntimeBinding(runtime_provider.id.clone()))?;
        if !is_absolute_host_path(&binding.executable) {
            return Err(PlanError::InvalidHostPath("runtimeBindings.executable"));
        }

        let translator = Self::select_translator(&config.capabilities, request, runtime_kind)?;
        let graphics = Self::select_graphics(&config.capabilities, request, runtime_kind)?;
        let paths = AppPaths::from_root(&config.storage_root);
        let bottle_directory = paths.bottle(&request.bottle_id);

        let mut environment = request.environment.clone();
        environment.extend(binding.environment.clone());
        if runtime_kind == RuntimeKind::Wine {
            environment.insert(
                "WINEPREFIX".into(),
                bottle_directory.join("prefix").to_string_lossy().into_owned(),
            );
        }

        let mut arguments = Vec::with_capacity(request.arguments.len() + 1);
        arguments.push(request.executable.path.clone());
        arguments.extend(request.arguments.clone());

        let working_directory = binding
            .working_directory
            .clone()
            .unwrap_or_else(|| bottle_directory.to_string_lossy().into_owned());
        if !is_absolute_host_path(&working_directory) {
            return Err(PlanError::InvalidHostPath("runtimeBindings.workingDirectory"));
        }

        let decision_trace = vec![
            format!(
                "runtime provider {} selected as {}",
                runtime_provider.id,
                runtime_kind.as_str()
            ),
            format!("translator {} selected", translator.provider.as_str()),
            format!("graphics backend {} selected", graphics.backend.as_str()),
            format!("runtime pack {} pinned by digest", binding.pack_id),
        ];

        Ok(LaunchPlan {
            schema_version: SCHEMA_VERSION_V1.into(),
            request_id: request.request_id.clone(),
            runtime: RuntimeSelection {
                provider: runtime_kind,
                pack_id: binding.pack_id.clone(),
                pack_digest: binding.pack_digest.clone(),
            },
            translator,
            graphics,
            process: NativeCommand {
                executable: binding.executable.clone(),
                arguments,
                environment,
                working_directory,
            },
            mounts: Vec::new(),
            sandbox: SandboxPolicy {
                profile: config.sandbox_profile,
                network: request.constraints.network_policy,
                allow_devices: Vec::new(),
            },
            decision_trace,
        })
    }

    /// Re-authorize a serialized plan before it crosses the process boundary.
    ///
    /// A frontend may cache or transport a plan, but it cannot replace the
    /// pinned runtime executable, digest, protected environment, sandbox, or
    /// storage location selected by the trusted context.
    pub fn authorize(config: &CoreConfig, plan: &LaunchPlan) -> Result<(), PlanError> {
        config.validate().map_err(PlanError::InvalidConfig)?;
        plan.validate().map_err(PlanError::InvalidPlan)?;

        if !is_absolute_host_path(&config.storage_root) {
            return Err(PlanError::InvalidHostPath("storageRoot"));
        }
        if !is_absolute_host_path(&plan.process.executable) {
            return Err(PlanError::InvalidHostPath("process.executable"));
        }
        if !is_absolute_host_path(&plan.process.working_directory) {
            return Err(PlanError::InvalidHostPath("process.workingDirectory"));
        }

        let binding = config
            .runtime_bindings
            .iter()
            .find(|candidate| {
                candidate.pack_id == plan.runtime.pack_id && candidate.pack_digest == plan.runtime.pack_digest
            })
            .ok_or(PlanError::PlanMismatch("runtime pack or digest"))?;
        if binding.executable != plan.process.executable {
            return Err(PlanError::PlanMismatch("runtime executable"));
        }
        let provider_matches = config.capabilities.runtime_providers.iter().any(|provider| {
            provider.available && provider.id == binding.provider_id && provider.kind == plan.runtime.provider.as_str()
        });
        if !provider_matches {
            return Err(PlanError::PlanMismatch("runtime provider"));
        }
        if plan.sandbox.profile != config.sandbox_profile {
            return Err(PlanError::PlanMismatch("sandbox profile"));
        }
        if !host_path_is_within(&config.storage_root, &plan.process.working_directory) {
            return Err(PlanError::PlanMismatch("working directory"));
        }
        for (key, value) in &binding.environment {
            if plan.process.environment.get(key) != Some(value) {
                return Err(PlanError::PlanMismatch("protected runtime environment"));
            }
        }
        if plan.runtime.provider == RuntimeKind::Wine {
            let wine_prefix = plan
                .process
                .environment
                .get("WINEPREFIX")
                .ok_or(PlanError::PlanMismatch("WINEPREFIX"))?;
            if !host_path_is_within(&config.storage_root, wine_prefix) {
                return Err(PlanError::PlanMismatch("WINEPREFIX"));
            }
        }
        Ok(())
    }

    fn check_required_capabilities(capabilities: &CapabilityReport, request: &LaunchRequest) -> Result<(), PlanError> {
        for required in &request.constraints.required_capabilities {
            let feature_available = capabilities
                .features
                .get(required)
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false);
            let provider_available = capabilities
                .runtime_providers
                .iter()
                .chain(capabilities.translators.iter())
                .chain(capabilities.graphics_backends.iter())
                .filter(|provider| provider.available)
                .any(|provider| provider.capabilities.contains(required));
            if !feature_available && !provider_available {
                return Err(PlanError::MissingRequiredCapability(required.clone()));
            }
        }
        Ok(())
    }

    fn select_runtime<'a>(
        capabilities: &'a CapabilityReport,
        request: &LaunchRequest,
    ) -> Result<(&'a ProviderDescriptor, RuntimeKind), PlanError> {
        let candidates: &[RuntimeKind] = if request.constraints.requires_kernel_driver {
            if request.constraints.allow_virtual_machine {
                &[RuntimeKind::VirtualMachine, RuntimeKind::Remote]
            } else {
                &[RuntimeKind::Remote]
            }
        } else {
            &[RuntimeKind::Wine, RuntimeKind::VirtualMachine, RuntimeKind::Remote]
        };

        for kind in candidates {
            if *kind == RuntimeKind::VirtualMachine && !request.constraints.allow_virtual_machine {
                continue;
            }
            if *kind == RuntimeKind::Remote && !request.constraints.allow_remote {
                continue;
            }
            if let Some(provider) = available_provider(&capabilities.runtime_providers, kind.as_str()) {
                return Ok((provider, *kind));
            }
        }
        Err(PlanError::NoCompatibleRuntime)
    }

    fn select_translator(
        capabilities: &CapabilityReport,
        request: &LaunchRequest,
        runtime: RuntimeKind,
    ) -> Result<TranslatorSelection, PlanError> {
        if runtime == RuntimeKind::Remote {
            return Ok(TranslatorSelection {
                provider: TranslatorKind::Remote,
                version: None,
            });
        }
        if runtime == RuntimeKind::VirtualMachine {
            return Ok(TranslatorSelection {
                provider: TranslatorKind::Native,
                version: None,
            });
        }

        let host_architecture = capabilities.host.architecture;
        let guest_architecture = request.executable.architecture;
        let same_family = host_architecture == guest_architecture
            || (host_architecture == CpuArchitecture::X86_64 && guest_architecture == CpuArchitecture::I386);
        if same_family {
            return Ok(TranslatorSelection {
                provider: TranslatorKind::Native,
                version: None,
            });
        }

        let preference: &[TranslatorKind] = match capabilities.host.os {
            HostOs::MacOs => &[TranslatorKind::Rosetta, TranslatorKind::Qemu],
            HostOs::Linux => &[TranslatorKind::Fex, TranslatorKind::Box64, TranslatorKind::Qemu],
            HostOs::Android => &[TranslatorKind::Box64, TranslatorKind::Fex, TranslatorKind::Qemu],
            HostOs::Windows => &[TranslatorKind::Native],
        };

        preference
            .iter()
            .find_map(|kind| {
                available_provider(&capabilities.translators, kind.as_str()).map(|provider| TranslatorSelection {
                    provider: *kind,
                    version: Some(provider.version.clone()),
                })
            })
            .ok_or(PlanError::NoCompatibleTranslator)
    }

    fn select_graphics(
        capabilities: &CapabilityReport,
        request: &LaunchRequest,
        runtime: RuntimeKind,
    ) -> Result<GraphicsSelection, PlanError> {
        if runtime == RuntimeKind::Remote {
            return Ok(GraphicsSelection {
                backend: GraphicsBackendKind::Remote,
                version: None,
                options: BTreeMap::new(),
            });
        }
        if runtime == RuntimeKind::VirtualMachine {
            return Ok(GraphicsSelection {
                backend: GraphicsBackendKind::Virtualized,
                version: None,
                options: BTreeMap::new(),
            });
        }

        let preference: &[GraphicsBackendKind] = match (capabilities.host.os, request.constraints.requires_direct_x12) {
            (HostOs::MacOs, true) => &[
                GraphicsBackendKind::D3dMetal,
                GraphicsBackendKind::Vkd3dProton,
                GraphicsBackendKind::WineD3d,
            ],
            (HostOs::MacOs, false) => &[
                GraphicsBackendKind::D3dMetal,
                GraphicsBackendKind::MoltenVk,
                GraphicsBackendKind::WineD3d,
            ],
            (_, true) => &[GraphicsBackendKind::Vkd3dProton, GraphicsBackendKind::WineD3d],
            (_, false) => &[GraphicsBackendKind::Dxvk, GraphicsBackendKind::WineD3d],
        };

        preference
            .iter()
            .find_map(|kind| {
                available_provider(&capabilities.graphics_backends, kind.as_str()).map(|provider| GraphicsSelection {
                    backend: *kind,
                    version: Some(provider.version.clone()),
                    options: BTreeMap::new(),
                })
            })
            .ok_or(PlanError::NoCompatibleGraphicsBackend)
    }
}

fn available_provider<'a>(providers: &'a [ProviderDescriptor], kind: &str) -> Option<&'a ProviderDescriptor> {
    providers
        .iter()
        .find(|provider| provider.available && provider.kind == kind)
}

fn is_absolute_host_path(value: &str) -> bool {
    normalize_host_path(value).is_some()
}

fn host_path_is_within(root: &str, candidate: &str) -> bool {
    let Some((root_namespace, root_components)) = normalize_host_path(root) else {
        return false;
    };
    let Some((candidate_namespace, candidate_components)) = normalize_host_path(candidate) else {
        return false;
    };
    root_namespace == candidate_namespace && candidate_components.starts_with(&root_components)
}

/// Normalize a serialized host path without depending on the OS compiling the
/// planner. Windows namespaces are case-insensitive; POSIX components retain
/// case. Parent traversal is rejected instead of being lexically contained.
fn normalize_host_path(value: &str) -> Option<(String, Vec<String>)> {
    let path = value.replace('\\', "/");
    let (namespace, remainder, case_insensitive) = if let Some(unc) = path.strip_prefix("//") {
        let mut components = unc.split('/').filter(|component| !component.is_empty());
        let server = components.next()?;
        let share = components.next()?;
        let namespace = format!("unc:{server}/{share}").to_ascii_lowercase();
        let remainder = components.collect::<Vec<_>>().join("/");
        (namespace, remainder, true)
    } else if path
        .as_bytes()
        .first()
        .is_some_and(|character| character.is_ascii_alphabetic())
        && path.as_bytes().get(1) == Some(&b':')
        && path.as_bytes().get(2) == Some(&b'/')
    {
        let drive = path[..1].to_ascii_lowercase();
        (format!("drive:{drive}"), path[3..].to_owned(), true)
    } else if let Some(remainder) = path.strip_prefix('/') {
        ("posix".to_owned(), remainder.to_owned(), false)
    } else {
        return None;
    };

    let mut normalized = Vec::new();
    for component in remainder.split('/') {
        match component {
            "" | "." => {}
            ".." => return None,
            component => {
                normalized.push(if case_insensitive {
                    component.to_ascii_lowercase()
                } else {
                    component.to_owned()
                });
            }
        }
    }
    Some((namespace, normalized))
}

#[cfg(test)]
mod tests {
    use super::*;
    use compatforge_domain::{
        ExecutableRequest, HostDescriptor, LaunchConstraints, NetworkPolicy, RuntimeBinding, SandboxProfile,
    };

    fn provider(id: &str, kind: &str) -> ProviderDescriptor {
        ProviderDescriptor {
            id: id.into(),
            kind: kind.into(),
            version: "test".into(),
            available: true,
            reason: None,
            capabilities: Vec::new(),
        }
    }

    fn config(host_architecture: CpuArchitecture) -> CoreConfig {
        CoreConfig {
            schema_version: SCHEMA_VERSION_V1.into(),
            capabilities: CapabilityReport {
                schema_version: SCHEMA_VERSION_V1.into(),
                host: HostDescriptor {
                    os: HostOs::Linux,
                    os_version: "test".into(),
                    architecture: host_architecture,
                    kernel: None,
                    device_model: None,
                },
                runtime_providers: vec![provider("wine-local", "wine"), provider("vm-local", "virtual-machine")],
                translators: vec![provider("fex-local", "fex")],
                graphics_backends: vec![provider("dxvk-local", "dxvk")],
                features: BTreeMap::new(),
            },
            runtime_bindings: vec![
                RuntimeBinding {
                    provider_id: "wine-local".into(),
                    pack_id: "wine-test".into(),
                    pack_digest: format!("sha256:{}", "0".repeat(64)),
                    executable: "/opt/compatforge/wine/bin/wine".into(),
                    environment: BTreeMap::new(),
                    working_directory: None,
                },
                RuntimeBinding {
                    provider_id: "vm-local".into(),
                    pack_id: "vm-test".into(),
                    pack_digest: format!("sha256:{}", "1".repeat(64)),
                    executable: "/opt/compatforge/vm/bin/launch".into(),
                    environment: BTreeMap::new(),
                    working_directory: None,
                },
            ],
            storage_root: "/var/lib/compatforge".into(),
            sandbox_profile: SandboxProfile::Desktop,
        }
    }

    fn request() -> LaunchRequest {
        LaunchRequest {
            schema_version: SCHEMA_VERSION_V1.into(),
            request_id: "018fe3cb-9d12-7b52-b334-1cce0e857fc9".into(),
            bottle_id: "example-bottle".into(),
            recipe_id: None,
            executable: ExecutableRequest {
                path: "C:\\Program Files\\Example\\example.exe".into(),
                architecture: CpuArchitecture::X86_64,
                sha256: None,
            },
            arguments: vec!["--safe".into()],
            environment: BTreeMap::new(),
            constraints: LaunchConstraints {
                allow_virtual_machine: true,
                allow_remote: false,
                requires_kernel_driver: false,
                requires_direct_x12: false,
                network_policy: NetworkPolicy::Deny,
                required_capabilities: Vec::new(),
            },
        }
    }

    #[test]
    fn compiles_native_linux_plan_without_shell_commands() {
        let plan = PolicyEngine::compile(&config(CpuArchitecture::X86_64), &request()).unwrap();
        assert_eq!(plan.runtime.provider, RuntimeKind::Wine);
        assert_eq!(plan.translator.provider, TranslatorKind::Native);
        assert_eq!(plan.graphics.backend, GraphicsBackendKind::Dxvk);
        assert_eq!(plan.process.arguments[0], request().executable.path);
        assert_eq!(
            plan.process.environment["WINEPREFIX"],
            "/var/lib/compatforge/bottles/example-bottle/prefix"
        );
    }

    #[test]
    fn selects_fex_for_x86_64_guest_on_linux_arm64() {
        let plan = PolicyEngine::compile(&config(CpuArchitecture::Arm64), &request()).unwrap();
        assert_eq!(plan.translator.provider, TranslatorKind::Fex);
    }

    #[test]
    fn sends_driver_dependent_software_to_a_vm() {
        let mut request = request();
        request.constraints.requires_kernel_driver = true;
        let plan = PolicyEngine::compile(&config(CpuArchitecture::X86_64), &request).unwrap();
        assert_eq!(plan.runtime.provider, RuntimeKind::VirtualMachine);
        assert_eq!(plan.graphics.backend, GraphicsBackendKind::Virtualized);
    }

    #[test]
    fn refuses_unpinned_runtime_provider() {
        let mut config = config(CpuArchitecture::X86_64);
        config.runtime_bindings.clear();
        assert!(matches!(
            PolicyEngine::compile(&config, &request()),
            Err(PlanError::MissingRuntimeBinding(_))
        ));
    }

    #[test]
    fn authorizes_a_freshly_compiled_plan() {
        let config = config(CpuArchitecture::X86_64);
        let plan = PolicyEngine::compile(&config, &request()).unwrap();
        PolicyEngine::authorize(&config, &plan).unwrap();
    }

    #[test]
    fn rejects_a_plan_with_a_replaced_runtime_executable() {
        let config = config(CpuArchitecture::X86_64);
        let mut plan = PolicyEngine::compile(&config, &request()).unwrap();
        plan.process.executable = "/tmp/untrusted-runtime".into();
        assert!(matches!(
            PolicyEngine::authorize(&config, &plan),
            Err(PlanError::PlanMismatch("runtime executable"))
        ));
    }

    #[test]
    fn runtime_binding_environment_cannot_be_overridden_by_a_request() {
        let mut config = config(CpuArchitecture::X86_64);
        config.runtime_bindings[0]
            .environment
            .insert("COMPATFORGE_RUNTIME_PACK".into(), "trusted".into());
        let mut request = request();
        request
            .environment
            .insert("COMPATFORGE_RUNTIME_PACK".into(), "untrusted".into());
        let plan = PolicyEngine::compile(&config, &request).unwrap();
        assert_eq!(plan.process.environment["COMPATFORGE_RUNTIME_PACK"], "trusted");
        PolicyEngine::authorize(&config, &plan).unwrap();
    }

    #[test]
    fn recognizes_serialized_absolute_paths_independent_of_build_host() {
        assert!(is_absolute_host_path("/var/lib/compatforge"));
        assert!(is_absolute_host_path("C:\\Program Files\\CompatForge"));
        assert!(is_absolute_host_path("\\\\server\\share\\CompatForge"));
        assert!(!is_absolute_host_path("relative/path"));
        assert!(!is_absolute_host_path("C:relative"));
    }

    #[test]
    fn host_path_containment_is_cross_platform_and_rejects_traversal() {
        assert!(host_path_is_within(
            "/var/lib/compatforge",
            "/var/lib/compatforge/bottles/example"
        ));
        assert!(host_path_is_within(
            "C:\\Program Files\\CompatForge",
            "c:/program files/compatforge/bottles/example"
        ));
        assert!(!host_path_is_within(
            "/var/lib/compatforge",
            "/var/lib/compatforge/../outside"
        ));
        assert!(!host_path_is_within(
            "C:\\Program Files\\CompatForge",
            "D:\\Program Files\\CompatForge"
        ));
    }
}
