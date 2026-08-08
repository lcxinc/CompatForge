use compatforge_domain::{
    CpuArchitecture, GraphicsBackendKind, HostCapabilities, HostOs, LaunchRequest, RuntimeKind,
    TranslatorKind,
};
use compatforge_orchestrator::PolicyEngine;

fn main() {
    let command = std::env::args().nth(1);
    match command.as_deref() {
        Some("--version" | "version") => println!("compatforge-cli 0.1.0"),
        Some("demo-plan") => demo_plan(),
        _ => {
            println!("CompatForge Phase 0 CLI");
            println!("usage: compatforge-cli [version|demo-plan]");
        }
    }
}

fn demo_plan() {
    let host = HostCapabilities {
        os: HostOs::Linux,
        architecture: CpuArchitecture::Arm64,
        runtimes: vec![RuntimeKind::Wine, RuntimeKind::Remote],
        translators: vec![TranslatorKind::Fex, TranslatorKind::Qemu],
        graphics_backends: vec![
            GraphicsBackendKind::Dxvk,
            GraphicsBackendKind::Vkd3dProton,
            GraphicsBackendKind::WineD3d,
        ],
    };
    let request = LaunchRequest {
        bottle_id: "demo".into(),
        executable: "C:\\Program Files\\7-Zip\\7zFM.exe".into(),
        guest_architecture: CpuArchitecture::X86_64,
        requires_kernel_driver: false,
        requires_directx_12: false,
        allow_virtual_machine: false,
        allow_remote: true,
    };

    match PolicyEngine::compile(&host, &request) {
        Ok(plan) => println!("{plan:#?}"),
        Err(error) => {
            eprintln!("planning failed: {error:?}");
            std::process::exit(1);
        }
    }
}
