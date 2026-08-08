//! Deterministic policy selection for runtime, translator, and graphics providers.

#![forbid(unsafe_code)]

use compatforge_domain::{
    CpuArchitecture, GraphicsBackendKind, HostCapabilities, HostOs, LaunchPlan, LaunchRequest,
    RuntimeKind, TranslatorKind,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlanError {
    NoCompatibleRuntime,
    NoCompatibleTranslator,
    NoCompatibleGraphicsBackend,
}

pub struct PolicyEngine;

impl PolicyEngine {
    /// Compile a request into a deterministic plan without launching a process.
    ///
    /// This Phase 0 implementation intentionally models only the primary fallback
    /// chain. Provider probes, version constraints, and signed policy overrides
    /// will be introduced behind the same boundary during Phase 1.
    pub fn compile(
        host: &HostCapabilities,
        request: &LaunchRequest,
    ) -> Result<LaunchPlan, PlanError> {
        let runtime = Self::select_runtime(host, request)?;
        let translator = Self::select_translator(host, request, runtime)?;
        let graphics = Self::select_graphics(host, request, runtime)?;

        let reason = match runtime {
            RuntimeKind::Wine => "local compatibility layer selected",
            RuntimeKind::VirtualMachine => "kernel or runtime requirements need a virtual machine",
            RuntimeKind::Remote => "local providers cannot satisfy the request",
        };

        Ok(LaunchPlan {
            runtime,
            translator,
            graphics,
            reason,
        })
    }

    fn select_runtime(
        host: &HostCapabilities,
        request: &LaunchRequest,
    ) -> Result<RuntimeKind, PlanError> {
        if request.requires_kernel_driver {
            if request.allow_virtual_machine && host.runtimes.contains(&RuntimeKind::VirtualMachine)
            {
                return Ok(RuntimeKind::VirtualMachine);
            }
            if request.allow_remote && host.runtimes.contains(&RuntimeKind::Remote) {
                return Ok(RuntimeKind::Remote);
            }
            return Err(PlanError::NoCompatibleRuntime);
        }

        if host.runtimes.contains(&RuntimeKind::Wine) {
            return Ok(RuntimeKind::Wine);
        }
        if request.allow_virtual_machine && host.runtimes.contains(&RuntimeKind::VirtualMachine) {
            return Ok(RuntimeKind::VirtualMachine);
        }
        if request.allow_remote && host.runtimes.contains(&RuntimeKind::Remote) {
            return Ok(RuntimeKind::Remote);
        }

        Err(PlanError::NoCompatibleRuntime)
    }

    fn select_translator(
        host: &HostCapabilities,
        request: &LaunchRequest,
        runtime: RuntimeKind,
    ) -> Result<TranslatorKind, PlanError> {
        if runtime != RuntimeKind::Wine {
            return Ok(TranslatorKind::Native);
        }

        let same_family = host.architecture == request.guest_architecture
            || (host.architecture == CpuArchitecture::X86_64
                && request.guest_architecture == CpuArchitecture::I386);
        if same_family && host.translators.contains(&TranslatorKind::Native) {
            return Ok(TranslatorKind::Native);
        }

        let preference: &[TranslatorKind] = match host.os {
            HostOs::MacOs => &[TranslatorKind::Rosetta, TranslatorKind::Qemu],
            HostOs::Linux => &[
                TranslatorKind::Fex,
                TranslatorKind::Box64,
                TranslatorKind::Qemu,
            ],
            HostOs::Android => &[
                TranslatorKind::Box64,
                TranslatorKind::Fex,
                TranslatorKind::Qemu,
            ],
            HostOs::Windows => &[TranslatorKind::Native],
        };

        preference
            .iter()
            .copied()
            .find(|candidate| host.translators.contains(candidate))
            .ok_or(PlanError::NoCompatibleTranslator)
    }

    fn select_graphics(
        host: &HostCapabilities,
        request: &LaunchRequest,
        runtime: RuntimeKind,
    ) -> Result<GraphicsBackendKind, PlanError> {
        match runtime {
            RuntimeKind::VirtualMachine => return Ok(GraphicsBackendKind::Virtualized),
            RuntimeKind::Remote => return Ok(GraphicsBackendKind::Remote),
            RuntimeKind::Wine => {}
        }

        let preference: &[GraphicsBackendKind] = match (host.os, request.requires_directx_12) {
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
            (_, true) => &[
                GraphicsBackendKind::Vkd3dProton,
                GraphicsBackendKind::WineD3d,
            ],
            (_, false) => &[GraphicsBackendKind::Dxvk, GraphicsBackendKind::WineD3d],
        };

        preference
            .iter()
            .copied()
            .find(|candidate| host.graphics_backends.contains(candidate))
            .ok_or(PlanError::NoCompatibleGraphicsBackend)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn linux_x86_host() -> HostCapabilities {
        HostCapabilities {
            os: HostOs::Linux,
            architecture: CpuArchitecture::X86_64,
            runtimes: vec![RuntimeKind::Wine, RuntimeKind::VirtualMachine],
            translators: vec![TranslatorKind::Native],
            graphics_backends: vec![
                GraphicsBackendKind::Dxvk,
                GraphicsBackendKind::Vkd3dProton,
            ],
        }
    }

    fn request() -> LaunchRequest {
        LaunchRequest {
            bottle_id: "example".into(),
            executable: "C:\\Program Files\\Example\\example.exe".into(),
            guest_architecture: CpuArchitecture::X86_64,
            requires_kernel_driver: false,
            requires_directx_12: false,
            allow_virtual_machine: true,
            allow_remote: true,
        }
    }

    #[test]
    fn selects_native_wine_and_dxvk_on_linux_x86_64() {
        let plan = PolicyEngine::compile(&linux_x86_host(), &request()).unwrap();
        assert_eq!(plan.runtime, RuntimeKind::Wine);
        assert_eq!(plan.translator, TranslatorKind::Native);
        assert_eq!(plan.graphics, GraphicsBackendKind::Dxvk);
    }

    #[test]
    fn selects_fex_for_x86_64_guest_on_linux_arm64() {
        let mut host = linux_x86_host();
        host.architecture = CpuArchitecture::Arm64;
        host.translators = vec![TranslatorKind::Fex, TranslatorKind::Qemu];

        let plan = PolicyEngine::compile(&host, &request()).unwrap();
        assert_eq!(plan.translator, TranslatorKind::Fex);
    }

    #[test]
    fn sends_driver_dependent_software_to_a_vm() {
        let mut request = request();
        request.requires_kernel_driver = true;

        let plan = PolicyEngine::compile(&linux_x86_host(), &request).unwrap();
        assert_eq!(plan.runtime, RuntimeKind::VirtualMachine);
        assert_eq!(plan.graphics, GraphicsBackendKind::Virtualized);
    }

    #[test]
    fn returns_an_error_when_translation_is_unavailable() {
        let mut host = linux_x86_host();
        host.architecture = CpuArchitecture::Arm64;
        host.translators.clear();

        assert_eq!(
            PolicyEngine::compile(&host, &request()),
            Err(PlanError::NoCompatibleTranslator)
        );
    }
}
