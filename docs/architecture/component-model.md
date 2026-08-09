# 组件模型与所有权

## Phase 0 已建立

| 组件 | 路径 | 当前责任 | 下一步 |
|---|---|---|---|
| Domain | `crates/compatforge-domain` | 与 Schema 对齐的能力、请求、计划、Bottle、Runtime Pack DTO 与校验 | 生成 Swift/Kotlin 绑定，拆分公共 API 与内部模型 |
| Capability | `crates/compatforge-capability` | 三平台 OS/架构/版本/设备基线、native translator 与来源化 observations | Runtime Pack、GPU/driver 与 translator 专项 probe |
| Inspect | `crates/compatforge-inspect` | 64 MiB 内 PE32/PE32+ 只读解析、SHA-256、section/import 摘要 | fuzz corpus、签名/资源的独立有界解析 |
| Guest Artifact | `crates/compatforge-guest-artifact` | 单次读取、inspection-bound SHA-256 对象物化、启动前内容复验 | daemon 受保护目录、租约与 GC |
| Storage | `crates/compatforge-storage` | macOS/XDG/Windows/Android 路径解析、受限相对路径、可恢复 JSON 写入 | manifest locking、snapshot 与迁移事务 |
| Runtime Pack | `crates/compatforge-runtime` | 规范化 manifest digest、artifact SHA-256、内容寻址发布、原子 active ref、校验与回滚 | 可信密钥 provider、归档物化、垃圾回收与跨进程 writer |
| Orchestrator | `crates/compatforge-orchestrator` | 硬约束、Provider 回退、固定 Runtime Pack、PreparedLaunch 和完整 LaunchPlan | Provider probe、认证结果评分、可解释 scoring |
| Process | `crates/compatforge-process` | Unix process group、Windows Job Object、有序事件、超时/分级终止、prefix 排他租约与 wineserver 清理 | OS sandbox、资源限制、daemon 级持久租约 |
| C ABI | `crates/compatforge-ffi` | capabilities/plan/start/events/terminate、opaque handle、稳定 status 与所有权释放 | IPC daemon 与 Qt C++ wrapper |
| CLI | `apps/cli` | probe、plan、受控 launch 与 Runtime Pack install/verify/rollback | doctor、lab 子命令 |
| Contracts | `schemas/` | 版本化交换格式 | 生成绑定、兼容性测试、签名 canonicalization |

Phase 0.1 仅引入 `serde`/`serde_json`，并把反序列化设置为拒绝未知字段，避免安全相关配置被静默忽略。异步运行时、数据库和遥测仍留到相应 Provider/进程监督需求出现后单独决策。

## 目标 Workspace

| 目标 crate/组件 | 责任 | 首个迁移来源 |
|---|---|---|
| `compatforge-api` | 公共 DTO、版本协商、错误码 | `Models.swift` |
| `compatforge-capability` | CPU/GPU/OS/Provider 探测 | `HostEnvironmentService`、Diagnostics |
| `compatforge-provider-macos` | 固定 Runtime Pack 的 Wine/Native/Rosetta/WineD3D/D3DMetal 专项 probe 与 Context 绑定 | Mac-Win `WineRunner`、`RosettaService`、图形预设 |
| `compatforge-orchestrator` | 硬约束、评分、回退、LaunchPlan | `WineRunner` 的选择逻辑 |
| `compatforge-runtime-wine` | Wine probe/prepare/compile/launch | `WineRunner.swift` |
| `compatforge-runtime-vm` | Windows VM Provider | 新建 |
| `compatforge-runtime-remote` | RemoteApp/云 Provider | 新建 |
| `compatforge-translator` | Native/Rosetta/FEX/Box64/QEMU | `WineRunner` 的 `/usr/bin/arch` 路径 |
| `compatforge-graphics` | WineD3D/DXVK/vkd3d/D3DMetal/MoltenVK | `GraphicsPreset.swift` |
| `compatforge-process` | 进程组、事件、取消、超时 | `WineRunner`、RuntimeProcess 服务 |
| `compatforge-bottle` | manifest、锁、事务、快照、迁移 | `BottleService.swift` |
| `compatforge-catalog` | Recipe 索引、签名、缓存、回滚保护 | `CatalogService.swift` |
| `compatforge-diagnostics` | 结构化事件、规则分类、脱敏、支持包 | Log/Diagnostics/Support 服务 |
| `compatforge-lab` | 测试计划、矩阵、产物、认证结果 | Smoke/Test/Sample 服务 |
| `compatforge-security` | 信任根、策略、签名、secret redaction | CatalogTrust、SupportBundle |
| `platform-macos` | App Support、进程、Rosetta、Metal、输入/窗口 | Darwin/CoreText/AppKit 代码 |
| `platform-linux` | XDG、namespace、Wayland/X11、PipeWire、NTSync | 新建 |
| `platform-android` | SAF、Surface、输入、生命周期、16 KB page | 新建 |

## 前端边界

### macOS 与 Linux Desktop

两端统一采用 Qt 6/QML，并保持为 Core 的薄客户端：

- `RuntimeClient`：capabilities、compile、launch、events、terminate；
- `BottleClient`：list、create、snapshot、migrate、restore；
- `CatalogClient`：refresh、list、verify、install；
- `DiagnosticsClient`：query events、run checks、export redacted bundle。

QML 不读取 Bottle/Runtime 文件、不持有 PID、不拼接命令。C++ client 只管理 opaque handle、JSON DTO 与线程调度；平台差异限制在窗口、输入、portal/权限与发行适配器。Mac-Win/SwiftUI 暂停维护，不再作为过渡交付路径。

### Android

Kotlin/Compose 通过 JNI/C ABI 调用同一 Rust Core。显示、触摸、IME、手柄、剪贴板和 SAF 是 platform adapter，不进入 Wine Provider 的通用接口。

## 数据所有权

| 数据 | 权威所有者 | 可缓存者 |
|---|---|---|
| HostCapabilities | capability service（单次 probe snapshot） | UI、orchestrator |
| Runtime Pack manifest | signed runtime registry | 本地内容存储 |
| Recipe | signed catalog | compat-db、UI |
| Bottle manifest | bottle manager | UI 只读 view model |
| LaunchPlan | orchestrator | diagnostics、process supervisor |
| GuestArtifactBinding / PE inspection | Guest Artifact Store | PreparedLaunch、process supervisor 只读复验 |
| RuntimeEvent | process supervisor | diagnostics store、UI |
| CompatibilityResult | compat-lab | policy scorer、catalog publishing pipeline |

任何组件不得绕过权威所有者直接修改其文件。尤其 UI 不直接编辑 Bottle JSON，Provider 不直接更新 Recipe，测试结果不直接提升兼容等级。
