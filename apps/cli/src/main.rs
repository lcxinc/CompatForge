use compatforge_capability::HostProbe;
use compatforge_domain::{CoreConfig, LaunchPlan, LaunchRequest, RuntimeEventKind};
use compatforge_orchestrator::PolicyEngine;
use compatforge_process::{EventPoll, ProcessSupervisor};
use std::error::Error;
use std::fs;
use std::io;
use std::path::Path;
use std::time::Duration;

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
            println!("compatforge-cli 0.5.0");
        }
        [command] if command == "probe" => {
            println!("{}", serde_json::to_string_pretty(&HostProbe::probe()?)?);
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
            launch(&config, &request)?;
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

fn launch(config: &CoreConfig, request: &LaunchRequest) -> Result<(), Box<dyn Error>> {
    let plan: LaunchPlan = PolicyEngine::compile(config, request)?;
    PolicyEngine::authorize(config, &plan)?;
    let handle = ProcessSupervisor::start(&plan)?;

    loop {
        match handle.next_event(Duration::from_millis(250)) {
            EventPoll::Event(event) => {
                println!("{}", serde_json::to_string(&event)?);
                if event.kind == RuntimeEventKind::Exited {
                    let success = event.exit.as_ref().is_some_and(|exit| exit.success);
                    if success {
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
    println!("  compatforge-cli demo-plan");
    println!("  compatforge-cli plan <context-config.json> <launch-request.json>");
    println!("  compatforge-cli launch <context-config.json> <launch-request.json>");
}
