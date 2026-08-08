//! Versioned, platform-neutral contracts shared by every CompatForge client.

#![forbid(unsafe_code)]

use serde::{Deserialize, Deserializer, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const SCHEMA_VERSION_V1: &str = "1";
pub const DEFAULT_TERMINATION_GRACE_MILLISECONDS: u64 = 3_000;
pub const MAX_TERMINATION_GRACE_MILLISECONDS: u64 = 60_000;
pub const MAX_RUNTIME_MILLISECONDS: u64 = 7 * 24 * 60 * 60 * 1_000;

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum HostOs {
    MacOs,
    Linux,
    Android,
    Windows,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
pub enum CpuArchitecture {
    #[serde(rename = "i386")]
    I386,
    #[serde(rename = "x86_64")]
    X86_64,
    #[serde(rename = "arm64")]
    Arm64,
    #[serde(rename = "unknown")]
    Unknown,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
pub enum RuntimeKind {
    #[serde(rename = "wine")]
    Wine,
    #[serde(rename = "virtual-machine")]
    VirtualMachine,
    #[serde(rename = "remote")]
    Remote,
}

impl RuntimeKind {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Wine => "wine",
            Self::VirtualMachine => "virtual-machine",
            Self::Remote => "remote",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
pub enum TranslatorKind {
    #[serde(rename = "native")]
    Native,
    #[serde(rename = "rosetta")]
    Rosetta,
    #[serde(rename = "fex")]
    Fex,
    #[serde(rename = "box64")]
    Box64,
    #[serde(rename = "qemu")]
    Qemu,
    #[serde(rename = "remote")]
    Remote,
}

impl TranslatorKind {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Native => "native",
            Self::Rosetta => "rosetta",
            Self::Fex => "fex",
            Self::Box64 => "box64",
            Self::Qemu => "qemu",
            Self::Remote => "remote",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
pub enum GraphicsBackendKind {
    #[serde(rename = "wined3d")]
    WineD3d,
    #[serde(rename = "dxvk")]
    Dxvk,
    #[serde(rename = "vkd3d-proton")]
    Vkd3dProton,
    #[serde(rename = "d3dmetal")]
    D3dMetal,
    #[serde(rename = "moltenvk")]
    MoltenVk,
    #[serde(rename = "virtualized")]
    Virtualized,
    #[serde(rename = "remote")]
    Remote,
}

impl GraphicsBackendKind {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::WineD3d => "wined3d",
            Self::Dxvk => "dxvk",
            Self::Vkd3dProton => "vkd3d-proton",
            Self::D3dMetal => "d3dmetal",
            Self::MoltenVk => "moltenvk",
            Self::Virtualized => "virtualized",
            Self::Remote => "remote",
        }
    }
}

#[derive(Debug, Clone, Copy, Default, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum NetworkPolicy {
    #[default]
    Deny,
    InstallerOnly,
    Allow,
}

#[derive(Debug, Clone, Copy, Default, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum SandboxProfile {
    Strict,
    #[default]
    Desktop,
    Game,
    Developer,
    Unconfined,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct HostDescriptor {
    pub os: HostOs,
    pub os_version: String,
    pub architecture: CpuArchitecture,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub kernel: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub device_model: Option<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ProviderDescriptor {
    pub id: String,
    pub kind: String,
    pub version: String,
    pub available: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub capabilities: Vec<String>,
}

impl ProviderDescriptor {
    pub fn validate(&self) -> Result<(), ContractError> {
        validate_id("provider.id", &self.id)?;
        if self.kind.is_empty() {
            return Err(ContractError::MissingField("provider.kind"));
        }
        if self.version.is_empty() {
            return Err(ContractError::MissingField("provider.version"));
        }
        if !self.available && self.reason.as_deref().map_or(true, str::is_empty) {
            return Err(ContractError::MissingField("provider.reason"));
        }
        let mut capabilities = BTreeSet::new();
        for capability in &self.capabilities {
            if capability.is_empty() {
                return Err(ContractError::MissingField("provider.capabilities"));
            }
            if !capabilities.insert(capability) {
                return Err(ContractError::DuplicateValue("provider.capabilities"));
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ProbeStatus {
    Detected,
    Unavailable,
    Unknown,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ProbeSource {
    RustStandardLibrary,
    OperatingSystemFile,
    OperatingSystemApi,
    BuiltIn,
    RuntimePack,
    Configuration,
}

/// A Schema v1 capability value.
///
/// Keeping this as a closed scalar type prevents domain objects from carrying
/// arrays, objects, or JSON null into public capability reports.
#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(untagged)]
pub enum CapabilityValue {
    Boolean(bool),
    String(String),
    Number(serde_json::Number),
}

impl CapabilityValue {
    #[must_use]
    pub const fn as_bool(&self) -> Option<bool> {
        match self {
            Self::Boolean(value) => Some(*value),
            Self::String(_) | Self::Number(_) => None,
        }
    }
}

impl From<bool> for CapabilityValue {
    fn from(value: bool) -> Self {
        Self::Boolean(value)
    }
}

impl From<String> for CapabilityValue {
    fn from(value: String) -> Self {
        Self::String(value)
    }
}

impl From<&str> for CapabilityValue {
    fn from(value: &str) -> Self {
        Self::String(value.into())
    }
}

impl From<u64> for CapabilityValue {
    fn from(value: u64) -> Self {
        Self::Number(value.into())
    }
}

fn deserialize_optional_capability_value<'de, D>(deserializer: D) -> Result<Option<CapabilityValue>, D::Error>
where
    D: Deserializer<'de>,
{
    CapabilityValue::deserialize(deserializer).map(Some)
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CapabilityObservation {
    pub id: String,
    pub category: String,
    pub status: ProbeStatus,
    pub source: ProbeSource,
    #[serde(
        default,
        deserialize_with = "deserialize_optional_capability_value",
        skip_serializing_if = "Option::is_none"
    )]
    pub value: Option<CapabilityValue>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

impl CapabilityObservation {
    pub fn validate(&self) -> Result<(), ContractError> {
        validate_id("observations.id", &self.id)?;
        if self.category.is_empty() {
            return Err(ContractError::MissingField("observations.category"));
        }
        match self.status {
            ProbeStatus::Detected if self.value.is_none() => Err(ContractError::MissingField("observations.value")),
            ProbeStatus::Unavailable | ProbeStatus::Unknown if self.reason.as_deref().map_or(true, str::is_empty) => {
                Err(ContractError::MissingField("observations.reason"))
            }
            _ => Ok(()),
        }
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CapabilityReport {
    pub schema_version: String,
    pub host: HostDescriptor,
    pub runtime_providers: Vec<ProviderDescriptor>,
    pub translators: Vec<ProviderDescriptor>,
    pub graphics_backends: Vec<ProviderDescriptor>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub observations: Vec<CapabilityObservation>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub features: BTreeMap<String, CapabilityValue>,
}

impl CapabilityReport {
    pub fn validate(&self) -> Result<(), ContractError> {
        validate_schema_version(&self.schema_version)?;
        if self.host.os_version.is_empty() {
            return Err(ContractError::MissingField("host.osVersion"));
        }
        if self.host.architecture == CpuArchitecture::Unknown {
            return Err(ContractError::UnsupportedValue("host.architecture"));
        }

        let mut provider_ids = BTreeSet::new();
        for provider in self
            .runtime_providers
            .iter()
            .chain(self.translators.iter())
            .chain(self.graphics_backends.iter())
        {
            provider.validate()?;
            if !provider_ids.insert(&provider.id) {
                return Err(ContractError::DuplicateValue("provider.id"));
            }
        }

        let mut observation_ids = BTreeSet::new();
        for observation in &self.observations {
            observation.validate()?;
            if !observation_ids.insert(&observation.id) {
                return Err(ContractError::DuplicateValue("observations.id"));
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ExecutableRequest {
    pub path: String,
    pub architecture: CpuArchitecture,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sha256: Option<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LaunchConstraints {
    pub allow_virtual_machine: bool,
    pub allow_remote: bool,
    #[serde(default)]
    pub requires_kernel_driver: bool,
    #[serde(default)]
    pub requires_direct_x12: bool,
    #[serde(default)]
    pub network_policy: NetworkPolicy,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub required_capabilities: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SupervisorPolicy {
    #[serde(default = "default_termination_grace_milliseconds")]
    pub termination_grace_milliseconds: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub maximum_runtime_milliseconds: Option<u64>,
}

impl Default for SupervisorPolicy {
    fn default() -> Self {
        Self {
            termination_grace_milliseconds: DEFAULT_TERMINATION_GRACE_MILLISECONDS,
            maximum_runtime_milliseconds: None,
        }
    }
}

impl SupervisorPolicy {
    pub fn validate(&self) -> Result<(), ContractError> {
        if !(1..=MAX_TERMINATION_GRACE_MILLISECONDS).contains(&self.termination_grace_milliseconds) {
            return Err(ContractError::UnsupportedValue(
                "supervisor.terminationGraceMilliseconds",
            ));
        }
        if self
            .maximum_runtime_milliseconds
            .is_some_and(|value| value == 0 || value > MAX_RUNTIME_MILLISECONDS)
        {
            return Err(ContractError::UnsupportedValue("supervisor.maximumRuntimeMilliseconds"));
        }
        Ok(())
    }
}

const fn default_termination_grace_milliseconds() -> u64 {
    DEFAULT_TERMINATION_GRACE_MILLISECONDS
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LaunchRequest {
    pub schema_version: String,
    pub request_id: String,
    pub bottle_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recipe_id: Option<String>,
    pub executable: ExecutableRequest,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub arguments: Vec<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub environment: BTreeMap<String, String>,
    pub constraints: LaunchConstraints,
}

impl LaunchRequest {
    pub fn validate(&self) -> Result<(), ContractError> {
        validate_schema_version(&self.schema_version)?;
        validate_id("bottleId", &self.bottle_id)?;
        if let Some(recipe_id) = &self.recipe_id {
            validate_id("recipeId", recipe_id)?;
        }
        if self.request_id.is_empty() {
            return Err(ContractError::MissingField("requestId"));
        }
        if self.executable.path.is_empty() {
            return Err(ContractError::MissingField("executable.path"));
        }
        if self.executable.architecture == CpuArchitecture::Unknown {
            return Err(ContractError::UnsupportedValue("executable.architecture"));
        }
        if let Some(digest) = &self.executable.sha256 {
            validate_sha256("executable.sha256", digest)?;
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RuntimeBinding {
    pub provider_id: String,
    pub pack_id: String,
    pub pack_digest: String,
    pub executable: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub wineserver_executable: Option<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub environment: BTreeMap<String, String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub working_directory: Option<String>,
}

impl RuntimeBinding {
    pub fn validate(&self) -> Result<(), ContractError> {
        validate_id("runtimeBindings.providerId", &self.provider_id)?;
        validate_id("runtimeBindings.packId", &self.pack_id)?;
        validate_digest("runtimeBindings.packDigest", &self.pack_digest)?;
        if self.executable.is_empty() {
            return Err(ContractError::MissingField("runtimeBindings.executable"));
        }
        if self.wineserver_executable.as_deref() == Some("") {
            return Err(ContractError::MissingField("runtimeBindings.wineserverExecutable"));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CoreConfig {
    pub schema_version: String,
    pub capabilities: CapabilityReport,
    pub runtime_bindings: Vec<RuntimeBinding>,
    pub storage_root: String,
    #[serde(default)]
    pub sandbox_profile: SandboxProfile,
    #[serde(default)]
    pub supervisor: SupervisorPolicy,
}

impl CoreConfig {
    pub fn validate(&self) -> Result<(), ContractError> {
        validate_schema_version(&self.schema_version)?;
        self.capabilities.validate()?;
        if self.storage_root.is_empty() {
            return Err(ContractError::MissingField("storageRoot"));
        }
        for binding in &self.runtime_bindings {
            binding.validate()?;
        }
        self.supervisor.validate()?;
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RuntimeSelection {
    pub provider: RuntimeKind,
    pub pack_id: String,
    pub pack_digest: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct TranslatorSelection {
    pub provider: TranslatorKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct GraphicsSelection {
    pub backend: GraphicsBackendKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub options: BTreeMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct NativeCommand {
    pub executable: String,
    pub arguments: Vec<String>,
    pub environment: BTreeMap<String, String>,
    pub working_directory: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Mount {
    pub source: String,
    pub destination: String,
    pub access: MountAccess,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum MountAccess {
    ReadOnly,
    ReadWrite,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SandboxPolicy {
    pub profile: SandboxProfile,
    pub network: NetworkPolicy,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub allow_devices: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct WineServerLifecycle {
    pub executable: String,
    pub prefix: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ProcessLifecycle {
    #[serde(default = "default_termination_grace_milliseconds")]
    pub termination_grace_milliseconds: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub maximum_runtime_milliseconds: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub wineserver: Option<WineServerLifecycle>,
}

impl Default for ProcessLifecycle {
    fn default() -> Self {
        Self {
            termination_grace_milliseconds: DEFAULT_TERMINATION_GRACE_MILLISECONDS,
            maximum_runtime_milliseconds: None,
            wineserver: None,
        }
    }
}

impl ProcessLifecycle {
    pub fn validate(&self) -> Result<(), ContractError> {
        SupervisorPolicy {
            termination_grace_milliseconds: self.termination_grace_milliseconds,
            maximum_runtime_milliseconds: self.maximum_runtime_milliseconds,
        }
        .validate()?;
        if let Some(wineserver) = &self.wineserver {
            if wineserver.executable.is_empty() {
                return Err(ContractError::MissingField("lifecycle.wineserver.executable"));
            }
            if wineserver.prefix.is_empty() {
                return Err(ContractError::MissingField("lifecycle.wineserver.prefix"));
            }
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LaunchPlan {
    pub schema_version: String,
    pub request_id: String,
    pub runtime: RuntimeSelection,
    pub translator: TranslatorSelection,
    pub graphics: GraphicsSelection,
    pub process: NativeCommand,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub mounts: Vec<Mount>,
    pub sandbox: SandboxPolicy,
    #[serde(default)]
    pub lifecycle: ProcessLifecycle,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub decision_trace: Vec<String>,
}

impl LaunchPlan {
    pub fn validate(&self) -> Result<(), ContractError> {
        validate_schema_version(&self.schema_version)?;
        if self.request_id.is_empty() {
            return Err(ContractError::MissingField("requestId"));
        }
        validate_id("runtime.packId", &self.runtime.pack_id)?;
        validate_digest("runtime.packDigest", &self.runtime.pack_digest)?;
        if self.process.executable.is_empty() {
            return Err(ContractError::MissingField("process.executable"));
        }
        if self.process.working_directory.is_empty() {
            return Err(ContractError::MissingField("process.workingDirectory"));
        }
        self.lifecycle.validate()?;
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum RuntimeEventKind {
    Started,
    Output,
    TerminateRequested,
    TimedOut,
    GracePeriodExpired,
    WineServerStopRequested,
    Exited,
    Failed,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum OutputStream {
    Stdout,
    Stderr,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ProcessOutput {
    pub stream: OutputStream,
    pub text: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ProcessExit {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<i32>,
    pub success: bool,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RuntimeEvent {
    pub schema_version: String,
    pub request_id: String,
    pub sequence: u64,
    pub elapsed_milliseconds: u64,
    pub kind: RuntimeEventKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub process_id: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output: Option<ProcessOutput>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub exit: Option<ProcessExit>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct BottleManifest {
    pub schema_version: String,
    pub id: String,
    pub name: String,
    pub guest: BottleGuest,
    pub runtime_pack: RuntimePackReference,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub recipes: Vec<RecipeReference>,
    pub storage: BottleStorage,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct BottleGuest {
    pub windows_version: WindowsVersion,
    pub architecture: CpuArchitecture,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum WindowsVersion {
    Win7,
    Win10,
    Win11,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RuntimePackReference {
    pub id: String,
    pub digest: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RecipeReference {
    pub id: String,
    pub version: String,
    pub digest: String,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct BottleStorage {
    pub layout_version: u32,
    pub state: BottleState,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum BottleState {
    Ready,
    Preparing,
    Migrating,
    Repairing,
    Failed,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RuntimePackManifest {
    pub schema_version: String,
    pub id: String,
    pub version: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub channel: Option<RuntimeChannel>,
    pub host: RuntimeHost,
    pub components: Vec<RuntimeComponent>,
    pub capabilities: Vec<String>,
    pub digest: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signature: Option<ManifestSignature>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sbom: Option<String>,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum RuntimeChannel {
    Stable,
    Candidate,
    Preview,
    Development,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RuntimeHost {
    pub os: HostOs,
    pub architecture: CpuArchitecture,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub minimum_version: Option<String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RuntimeComponent {
    pub name: String,
    pub version: String,
    pub license: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
    pub digest: String,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub entrypoints: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ManifestSignature {
    pub key_id: String,
    pub algorithm: SignatureAlgorithm,
    pub value: String,
}

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq, Serialize)]
pub enum SignatureAlgorithm {
    #[serde(rename = "ed25519")]
    Ed25519,
    #[serde(rename = "p256-sha256")]
    P256Sha256,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContractError {
    UnsupportedSchemaVersion,
    MissingField(&'static str),
    InvalidIdentifier(&'static str),
    InvalidDigest(&'static str),
    DuplicateValue(&'static str),
    UnsupportedValue(&'static str),
}

impl fmt::Display for ContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnsupportedSchemaVersion => formatter.write_str("unsupported schemaVersion"),
            Self::MissingField(field) => write!(formatter, "missing required field {field}"),
            Self::InvalidIdentifier(field) => write!(formatter, "invalid identifier in {field}"),
            Self::InvalidDigest(field) => write!(formatter, "invalid digest in {field}"),
            Self::DuplicateValue(field) => write!(formatter, "duplicate value in {field}"),
            Self::UnsupportedValue(field) => write!(formatter, "unsupported value in {field}"),
        }
    }
}

impl std::error::Error for ContractError {}

pub fn validate_schema_version(version: &str) -> Result<(), ContractError> {
    if version == SCHEMA_VERSION_V1 {
        Ok(())
    } else {
        Err(ContractError::UnsupportedSchemaVersion)
    }
}

pub fn validate_id(field: &'static str, value: &str) -> Result<(), ContractError> {
    let mut characters = value.chars();
    let first_is_valid = characters
        .next()
        .is_some_and(|character| character.is_ascii_lowercase() || character.is_ascii_digit());
    let rest_is_valid = characters.all(|character| {
        character.is_ascii_lowercase() || character.is_ascii_digit() || matches!(character, '.' | '_' | '-')
    });
    if first_is_valid && rest_is_valid && value.len() >= 2 {
        Ok(())
    } else {
        Err(ContractError::InvalidIdentifier(field))
    }
}

pub fn validate_sha256(field: &'static str, value: &str) -> Result<(), ContractError> {
    if value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        Ok(())
    } else {
        Err(ContractError::InvalidDigest(field))
    }
}

pub fn validate_digest(field: &'static str, value: &str) -> Result<(), ContractError> {
    value
        .strip_prefix("sha256:")
        .ok_or(ContractError::InvalidDigest(field))
        .and_then(|digest| validate_sha256(field, digest))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_checked_in_contract_examples() {
        let capability: CapabilityReport =
            serde_json::from_str(include_str!("../../../examples/capability-report.linux-arm64.json")).unwrap();
        assert_eq!(capability.host.architecture, CpuArchitecture::Arm64);

        let request: LaunchRequest =
            serde_json::from_str(include_str!("../../../examples/launch-request.json")).unwrap();
        request.validate().unwrap();

        let plan: LaunchPlan = serde_json::from_str(include_str!("../../../examples/launch-plan.json")).unwrap();
        assert_eq!(plan.runtime.provider, RuntimeKind::Wine);
        plan.validate().unwrap();

        let config: CoreConfig =
            serde_json::from_str(include_str!("../../../examples/context-config.linux-arm64.json")).unwrap();
        config.validate().unwrap();

        let event: RuntimeEvent = serde_json::from_str(include_str!("../../../examples/runtime-event.json")).unwrap();
        assert_eq!(event.kind, RuntimeEventKind::Output);

        let runtime: RuntimePackManifest = serde_json::from_str(include_str!(
            "../../../examples/runtime-packs/wine-linux-arm64-fex.json"
        ))
        .unwrap();
        assert_eq!(runtime.host.os, HostOs::Linux);

        let bottle: BottleManifest =
            serde_json::from_str(include_str!("../../../examples/bottles/7zip-default.json")).unwrap();
        assert_eq!(bottle.storage.state, BottleState::Ready);
    }

    #[test]
    fn rejects_unknown_security_relevant_fields() {
        let json = r#"{
            "schemaVersion":"1",
            "requestId":"018fe3cb-9d12-7b52-b334-1cce0e857fc9",
            "bottleId":"example-bottle",
            "executable":{"path":"C:\\\\example.exe","architecture":"x86_64"},
            "constraints":{"allowVirtualMachine":false,"allowRemote":false,"unexpected":true}
        }"#;
        assert!(serde_json::from_str::<LaunchRequest>(json).is_err());
    }

    #[test]
    fn validates_identifiers_and_digests() {
        assert!(validate_id("id", "wine-linux-arm64").is_ok());
        assert!(validate_id("id", "../escape").is_err());
        assert!(validate_digest("digest", &format!("sha256:{}", "a".repeat(64))).is_ok());
        assert!(validate_digest("digest", "latest").is_err());
    }

    #[test]
    fn rejects_unbounded_supervisor_policies() {
        assert!(SupervisorPolicy {
            termination_grace_milliseconds: 0,
            maximum_runtime_milliseconds: None,
        }
        .validate()
        .is_err());
        assert!(SupervisorPolicy {
            termination_grace_milliseconds: DEFAULT_TERMINATION_GRACE_MILLISECONDS,
            maximum_runtime_milliseconds: Some(MAX_RUNTIME_MILLISECONDS + 1),
        }
        .validate()
        .is_err());
    }

    #[test]
    fn validates_capability_observation_evidence() {
        let mut report: CapabilityReport =
            serde_json::from_str(include_str!("../../../examples/capability-report.linux-arm64.json")).unwrap();
        report.validate().unwrap();

        report.observations.push(report.observations[0].clone());
        assert_eq!(report.validate(), Err(ContractError::DuplicateValue("observations.id")));

        let mut observation = report.observations[0].clone();
        observation.status = ProbeStatus::Unknown;
        observation.value = None;
        observation.reason = None;
        assert_eq!(
            observation.validate(),
            Err(ContractError::MissingField("observations.reason"))
        );
    }

    #[test]
    fn rejects_non_scalar_capability_values() {
        let report: CapabilityReport =
            serde_json::from_str(include_str!("../../../examples/capability-report.linux-arm64.json")).unwrap();

        for invalid in [serde_json::json!({"nested": true}), serde_json::json!([true])] {
            let mut value = serde_json::to_value(&report).unwrap();
            value["features"]["vulkan"] = invalid.clone();
            assert!(serde_json::from_value::<CapabilityReport>(value).is_err());

            let mut value = serde_json::to_value(&report).unwrap();
            value["observations"][0]["value"] = invalid;
            assert!(serde_json::from_value::<CapabilityReport>(value).is_err());
        }

        let mut null_feature = serde_json::to_value(&report).unwrap();
        null_feature["features"]["vulkan"] = serde_json::Value::Null;
        assert!(serde_json::from_value::<CapabilityReport>(null_feature).is_err());

        let mut null_observation = serde_json::to_value(&report).unwrap();
        null_observation["observations"][0]["value"] = serde_json::Value::Null;
        assert!(serde_json::from_value::<CapabilityReport>(null_observation).is_err());
    }
}
