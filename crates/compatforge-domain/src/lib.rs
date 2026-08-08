//! Platform-neutral types shared by every CompatForge frontend and provider.

#![forbid(unsafe_code)]

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HostOs {
    MacOs,
    Linux,
    Android,
    Windows,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CpuArchitecture {
    I386,
    X86_64,
    Arm64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RuntimeKind {
    Wine,
    VirtualMachine,
    Remote,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TranslatorKind {
    Native,
    Rosetta,
    Fex,
    Box64,
    Qemu,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GraphicsBackendKind {
    WineD3d,
    Dxvk,
    Vkd3dProton,
    D3dMetal,
    MoltenVk,
    Virtualized,
    Remote,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HostCapabilities {
    pub os: HostOs,
    pub architecture: CpuArchitecture,
    pub runtimes: Vec<RuntimeKind>,
    pub translators: Vec<TranslatorKind>,
    pub graphics_backends: Vec<GraphicsBackendKind>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LaunchRequest {
    pub bottle_id: String,
    pub executable: String,
    pub guest_architecture: CpuArchitecture,
    pub requires_kernel_driver: bool,
    pub requires_directx_12: bool,
    pub allow_virtual_machine: bool,
    pub allow_remote: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LaunchPlan {
    pub runtime: RuntimeKind,
    pub translator: TranslatorKind,
    pub graphics: GraphicsBackendKind,
    pub reason: &'static str,
}
