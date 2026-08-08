use compatforge_capability::HostProbe;
use compatforge_domain::{CoreConfig, LaunchPlan, LaunchRequest, RuntimeEventKind, RuntimePackManifest};
use compatforge_inspect::inspect_path;
use compatforge_orchestrator::PolicyEngine;
use compatforge_process::{EventPoll, ProcessSupervisor};
use compatforge_provider_macos::{MacOsProviderConfig, MacOsProviderSet};
use compatforge_runtime::{sha256_digest_bytes, RejectAllSignatures, RuntimePackStore};
use std::error::Error;
use std::fs;
use std::io;
use std::path::Path;
use std::time::{Duration, Instant};

fn main() {
    if let Err(error) = run() {
        eprintln!("compatforge-cli: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    match arguments.as_slice() {
        [command] if matches!(command.as_str(), "--version" | "version") => {
            println!("compatforge-cli {}", env!("CARGO_PKG_VERSION"));
        }
        [command] if command == "probe" => {
            println!("{}", serde_json::to_string_pretty(&HostProbe::probe()?)?);
        }
        [command, executable_path] if command == "inspect" => {
            let executable_path = fs::canonicalize(executable_path)?;
            println!("{}", serde_json::to_string_pretty(&inspect_path(&executable_path)?)?);
        }
        [group, platform, command, config_path] if group == "provider" && platform == "macos" && command == "probe" => {
            let config = read_json::<MacOsProviderConfig>(Path::new(config_path))?;
            let snapshot = MacOsProviderSet::probe(&HostProbe::probe()?, &config)?;
            println!("{}", serde_json::to_string_pretty(&snapshot.capabilities)?);
        }
        [group, platform, command, config_path, storage_root]
            if group == "provider" && platform == "macos" && command == "context" =>
        {
            let config = read_json::<MacOsProviderConfig>(Path::new(config_path))?;
            let snapshot = MacOsProviderSet::probe(&HostProbe::probe()?, &config)?;
            let core_config = snapshot.core_config(storage_root.clone())?;
            println!("{}", serde_json::to_string_pretty(&core_config)?);
        }
        [command] if command == "demo-plan" => {
            let config: CoreConfig =
                serde_json::from_str(include_str!("../../../examples/context-config.linux-arm64.json"))?;
            let request: LaunchRequest = serde_json::from_str(include_str!("../../../examples/launch-request.json"))?;
            print_plan(&config, &request)?;
        }
        [command, config_path, request_path] if command == "plan" => {
            let config = read_json::<CoreConfig>(Path::new(config_path))?;
            let request = read_json::<LaunchRequest>(Path::new(request_path))?;
            print_plan(&config, &request)?;
        }
        [command, config_path, request_path] if command == "launch" => {
            let config = read_json::<CoreConfig>(Path::new(config_path))?;
            let request = read_json::<LaunchRequest>(Path::new(request_path))?;
            launch(&config, &request, None)?;
        }
        [command, config_path, request_path, milliseconds] if command == "launch-terminate" => {
            let config = read_json::<CoreConfig>(Path::new(config_path))?;
            let request = read_json::<LaunchRequest>(Path::new(request_path))?;
            let milliseconds = milliseconds.parse::<u64>()?;
            launch(&config, &request, Some(Duration::from_millis(milliseconds)))?;
        }
        [group, command, manifest_path] if group == "runtime" && command == "manifest-digest" => {
            let manifest = read_json::<RuntimePackManifest>(Path::new(manifest_path))?;
            manifest.validate()?;
            println!("{}", sha256_digest_bytes(&manifest.canonical_unsigned_bytes()?));
        }
        [group, command, store_root, bundle_root, manifest_relative] if group == "runtime" && command == "install" => {
            let receipt = RuntimePackStore::new(store_root).install_bundle(
                bundle_root,
                manifest_relative,
                &RejectAllSignatures,
            )?;
            println!("{}", serde_json::to_string_pretty(&receipt)?);
        }
        [group, command, store_root, digest] if group == "runtime" && command == "verify" => {
            let receipt = RuntimePackStore::new(store_root).verify_installed(digest)?;
            println!("{}", serde_json::to_string_pretty(&receipt)?);
        }
        [group, command, store_root, pack_id] if group == "runtime" && command == "rollback" => {
            let receipt = RuntimePackStore::new(store_root).rollback(pack_id)?;
            println!("{}", serde_json::to_string_pretty(&receipt)?);
        }
        _ => print_help(),
    }
    Ok(())
}

fn read_json<T: serde::de::DeserializeOwned>(path: &Path) -> Result<T, Box<dyn Error>> {
    let bytes = fs::read(path)?;
    Ok(serde_json::from_slice(&bytes)?)
}

fn print_plan(config: &CoreConfig, request: &LaunchRequest) -> Result<(), Box<dyn Error>> {
    let plan = PolicyEngine::compile(config, request)?;
    println!("{}", serde_json::to_string_pretty(&plan)?);
    Ok(())
}

fn launch(
    config: &CoreConfig,
    request: &LaunchRequest,
    terminate_after: Option<Duration>,
) -> Result<(), Box<dyn Error>> {
    let plan: LaunchPlan = PolicyEngine::compile(config, request)?;
    PolicyEngine::authorize(config, &plan)?;
    let handle = ProcessSupervisor::start(&plan)?;
    let started = Instant::now();
    let mut termination_requested = false;

    loop {
        if !termination_requested && terminate_after.is_some_and(|delay| started.elapsed() >= delay) {
            handle.terminate()?;
            termination_requested = true;
        }
        match handle.next_event(Duration::from_millis(250)) {
            EventPoll::Event(event) => {
                println!("{}", serde_json::to_string(&event)?);
                if event.kind == RuntimeEventKind::Exited {
                    let success = event.exit.as_ref().is_some_and(|exit| exit.success);
                    if success || termination_requested {
                        return Ok(());
                    }
                    return Err(io::Error::other("supervised process exited unsuccessfully").into());
                }
                if event.kind == RuntimeEventKind::Failed {
                    return Err(io::Error::other("process supervision failed").into());
                }
            }
            EventPoll::Timeout => {}
            EventPoll::Closed => return Err(io::Error::other("runtime event stream closed").into()),
        }
    }
}

fn print_help() {
    println!("CompatForge Core CLI");
    println!("usage:");
    println!("  compatforge-cli version");
    println!("  compatforge-cli probe");
    println!("  compatforge-cli inspect <windows-executable>");
    println!("  compatforge-cli provider macos probe <provider-config.json>");
    println!("  compatforge-cli provider macos context <provider-config.json> <storage-root>");
    println!("  compatforge-cli demo-plan");
    println!("  compatforge-cli plan <context-config.json> <launch-request.json>");
    println!("  compatforge-cli launch <context-config.json> <launch-request.json>");
    println!("  compatforge-cli launch-terminate <context-config.json> <launch-request.json> <delay-ms>");
    println!("  compatforge-cli runtime manifest-digest <manifest.json>");
    println!("  compatforge-cli runtime install <store-root> <bundle-root> <manifest-relative-path>");
    println!("  compatforge-cli runtime verify <store-root> <pack-digest>");
    println!("  compatforge-cli runtime rollback <store-root> <pack-id>");
}
