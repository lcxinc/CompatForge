#![forbid(unsafe_code)]

use compatforge_capability::{ContextCapabilityQuery, HostProbe};
use compatforge_domain::{CapabilityReport, ProviderDescriptor, SCHEMA_VERSION_V1};
use compatforge_provider_macos::{create_local_context, MacOsLocalContextReceipt, MacOsLocalContextRequest};
use compatforge_service::{AutomationService, ServiceConfig, ServiceRequest, ServiceResponse};
use serde::Serialize;
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::Duration;
use tauri::{AppHandle, Manager, RunEvent, State, TitleBarStyle, WebviewUrl, WebviewWindowBuilder, WindowEvent};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct CapabilityView {
    id: String,
    label: String,
    status: String,
    available: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeSnapshot {
    runtime_ready: bool,
    runtime_status: String,
    smoke_mode: bool,
    capabilities: Vec<CapabilityView>,
    receipt: Option<Value>,
    error: Option<String>,
}

struct DesktopRuntime {
    runtime_store_root: PathBuf,
    storage_root: PathBuf,
    service_root: PathBuf,
    smoke_mode: bool,
    service: Option<Arc<AutomationService>>,
    receipt: Option<MacOsLocalContextReceipt>,
    capabilities: Option<CapabilityReport>,
    runtime_status: String,
    error: Option<String>,
}

impl DesktopRuntime {
    fn new(base: PathBuf, smoke_mode: bool) -> Self {
        Self {
            runtime_store_root: base.join("runtime-store"),
            storage_root: base.join("storage"),
            service_root: base.join("service"),
            smoke_mode,
            service: None,
            receipt: None,
            capabilities: None,
            runtime_status: if smoke_mode {
                "Smoke 模式：未执行 Runtime Bootstrap".into()
            } else {
                "正在准备运行环境…".into()
            },
            error: None,
        }
    }

    fn snapshot(&self) -> RuntimeSnapshot {
        RuntimeSnapshot {
            runtime_ready: self.service.is_some(),
            runtime_status: self.runtime_status.clone(),
            smoke_mode: self.smoke_mode,
            capabilities: self
                .capabilities
                .as_ref()
                .map(capability_views)
                .unwrap_or_else(waiting_capabilities),
            receipt: self
                .receipt
                .as_ref()
                .and_then(|receipt| serde_json::to_value(receipt).ok()),
            error: self.error.clone(),
        }
    }
}

struct BootstrapResult {
    service: Arc<AutomationService>,
    receipt: MacOsLocalContextReceipt,
    capabilities: CapabilityReport,
}

struct AppState {
    runtime: Mutex<DesktopRuntime>,
    bootstrap: Mutex<()>,
}

impl AppState {
    fn new(runtime: DesktopRuntime) -> Self {
        Self {
            runtime: Mutex::new(runtime),
            bootstrap: Mutex::new(()),
        }
    }

    fn shutdown(&self) {
        if let Ok(mut runtime) = self.runtime.lock() {
            runtime.service = None;
        }
    }
}

fn lock_runtime<'a>(state: &'a State<'_, AppState>) -> Result<MutexGuard<'a, DesktopRuntime>, String> {
    state.runtime.lock().map_err(|_| "桌面运行状态锁已损坏".into())
}

fn service(state: &State<'_, AppState>) -> Result<Arc<AutomationService>, String> {
    lock_runtime(state)?
        .service
        .clone()
        .ok_or_else(|| "运行环境尚未完成 Bootstrap".into())
}

#[tauri::command]
fn state_snapshot(state: State<'_, AppState>) -> Result<RuntimeSnapshot, String> {
    Ok(lock_runtime(&state)?.snapshot())
}

#[tauri::command]
async fn bootstrap_runtime(state: State<'_, AppState>) -> Result<RuntimeSnapshot, String> {
    let _bootstrap = state.bootstrap.lock().map_err(|_| "Bootstrap 状态锁已损坏")?;
    let (runtime_store_root, storage_root, service_root) = {
        let runtime = lock_runtime(&state)?;
        (
            runtime.runtime_store_root.clone(),
            runtime.storage_root.clone(),
            runtime.service_root.clone(),
        )
    };
    let result = bootstrap_core(&runtime_store_root, &storage_root, &service_root);
    let mut runtime = lock_runtime(&state)?;
    match result {
        Ok(result) => {
            runtime.runtime_status = format!("运行环境就绪 · {} · {}", result.receipt.version, result.receipt.pack_id);
            runtime.service = Some(result.service);
            runtime.receipt = Some(result.receipt);
            runtime.capabilities = Some(result.capabilities);
            runtime.error = None;
            Ok(runtime.snapshot())
        }
        Err(message) => {
            runtime.runtime_status = "Runtime Bootstrap 失败".into();
            runtime.error = Some(message.clone());
            Err(message)
        }
    }
}

#[tauri::command]
async fn service_call(request: ServiceRequest, state: State<'_, AppState>) -> Result<ServiceResponse, String> {
    service(&state)?.call(request).map_err(|error| error.to_string())
}

#[tauri::command]
fn clear_error(state: State<'_, AppState>) -> Result<RuntimeSnapshot, String> {
    let mut runtime = lock_runtime(&state)?;
    runtime.error = None;
    Ok(runtime.snapshot())
}

#[tauri::command]
fn open_settings(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("settings") {
        window.show().map_err(|error| error.to_string())?;
        window.set_focus().map_err(|error| error.to_string())?;
        return Ok(());
    }
    WebviewWindowBuilder::new(&app, "settings", WebviewUrl::App("settings.html".into()))
        .title("CompatForge 设置")
        .inner_size(980.0, 680.0)
        .min_inner_size(760.0, 560.0)
        .resizable(true)
        .decorations(true)
        .hidden_title(true)
        .title_bar_style(TitleBarStyle::Overlay)
        .build()
        .map_err(|error| error.to_string())?;
    Ok(())
}

fn bootstrap_core(
    runtime_store_root: &Path,
    storage_root: &Path,
    service_root: &Path,
) -> Result<BootstrapResult, String> {
    create_directory(runtime_store_root, "Runtime Store")?;
    create_directory(storage_root, "存储目录")?;
    create_directory(service_root, "服务目录")?;
    let host = HostProbe::probe().map_err(|error| format!("主机能力探测失败：{error}"))?;
    let request = MacOsLocalContextRequest {
        schema_version: SCHEMA_VERSION_V1.into(),
        runtime_store_root: path_text(runtime_store_root)?,
        storage_root: path_text(storage_root)?,
        materialized_root: None,
        wine: None,
        wineserver: None,
        version: None,
    };
    let local = create_local_context(&host, &request).map_err(|error| format!("Runtime Bootstrap 失败：{error}"))?;
    let capabilities =
        ContextCapabilityQuery::report(&local.config).map_err(|error| format!("能力报告生成失败：{error}"))?;
    let service = AutomationService::new(
        local.config,
        ServiceConfig {
            schema_version: SCHEMA_VERSION_V1.into(),
            service_root: path_text(service_root)?,
        },
    )
    .map_err(|error| format!("应用服务初始化失败：{error}"))?;
    service
        .seed_default_applications()
        .map_err(|error| format!("默认应用登记失败：{error}"))?;
    Ok(BootstrapResult {
        service: Arc::new(service),
        receipt: local.receipt,
        capabilities,
    })
}

fn create_directory(path: &Path, label: &str) -> Result<(), String> {
    std::fs::create_dir_all(path).map_err(|error| format!("无法创建{label}：{error}"))
}

fn path_text(path: &Path) -> Result<String, String> {
    path.to_str()
        .map(str::to_owned)
        .ok_or_else(|| "路径不是有效 UTF-8".into())
}

fn capability_views(report: &CapabilityReport) -> Vec<CapabilityView> {
    vec![
        capability_view("runtime", "Wine Runtime", &report.runtime_providers, "wine"),
        capability_view("rosetta", "Rosetta 2", &report.translators, "rosetta"),
        capability_view("graphics", "图形兼容", &report.graphics_backends, "wined3d"),
    ]
}

fn waiting_capabilities() -> Vec<CapabilityView> {
    [
        ("runtime", "Wine Runtime"),
        ("rosetta", "Rosetta 2"),
        ("graphics", "图形兼容"),
    ]
    .into_iter()
    .map(|(id, label)| CapabilityView {
        id: id.into(),
        label: label.into(),
        status: "等待 Bootstrap".into(),
        available: false,
    })
    .collect()
}

fn capability_view(id: &str, label: &str, providers: &[ProviderDescriptor], kind: &str) -> CapabilityView {
    let provider = providers.iter().find(|provider| provider.kind == kind);
    let (status, available) = match provider {
        Some(provider) if provider.available => {
            let status = if provider.version.is_empty() {
                "可用".into()
            } else {
                format!("可用 · {}", provider.version)
            };
            (status, true)
        }
        Some(provider) => (provider.reason.clone().unwrap_or_else(|| "不可用".into()), false),
        None => ("未报告".into(), false),
    };
    CapabilityView {
        id: id.into(),
        label: label.into(),
        status,
        available,
    }
}

pub fn run() {
    let application = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let base = app.path().app_local_data_dir()?;
            std::fs::create_dir_all(&base)?;
            let smoke_mode = std::env::var_os("COMPATFORGE_DESKTOP_SMOKE").is_some();
            app.manage(AppState::new(DesktopRuntime::new(base, smoke_mode)));
            if smoke_mode {
                println!("COMPATFORGE_TAURI_SMOKE_READY");
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_secs(2));
                    handle.exit(0);
                });
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            state_snapshot,
            bootstrap_runtime,
            service_call,
            clear_error,
            open_settings
        ])
        .build(tauri::generate_context!())
        .expect("failed to build CompatForge desktop application");

    application.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit)
            || matches!(
                event,
                RunEvent::WindowEvent {
                    ref label,
                    event: WindowEvent::CloseRequested { .. },
                    ..
                } if label == "main"
            )
        {
            app_handle.state::<AppState>().shutdown();
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initial_snapshot_is_not_service_ready() {
        let runtime = DesktopRuntime::new(PathBuf::from("/tmp/compatforge-tauri-test"), true);
        let snapshot = runtime.snapshot();
        assert!(snapshot.smoke_mode);
        assert!(!snapshot.runtime_ready);
        assert_eq!(snapshot.capabilities.len(), 3);
    }

    #[test]
    fn waiting_capability_cards_have_stable_ids() {
        let cards = waiting_capabilities();
        assert_eq!(
            cards.iter().map(|card| card.id.as_str()).collect::<Vec<_>>(),
            ["runtime", "rosetta", "graphics"]
        );
    }
}
