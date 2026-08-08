# 组件模型与所有权

## Phase 0 已建立

| 组件 | 路径 | 当前责任 | 下一步 |
|---|---|---|---|
| Domain | `crates/compatforge-domain` | 平台无关枚举、能力、请求与计划概念 | 接入 schema codegen/serde，拆分稳定 API 与内部模型 |
| Orchestrator | `crates/compatforge-orchestrator` | 无副作用的基本回退策略与测试 | Provider probe、约束求解、认证结果评分、decision trace |
| C ABI | `crates/compatforge-ffi` | ABI/API 版本探针和 C header | opaque context、JSON request/response、事件与释放函数 |
| CLI | `apps/cli` | 演示策略编译 | host probe、validate、plan、launch、doctor、lab 子命令 |
| Contracts | `schemas/` | 版本化交换格式 | 生成绑定、兼容性测试、签名 canonicalization |

Phase 0 代码刻意不依赖第三方 crate，以保证新仓库能在三大桌面 CI 上快速建立基线。这不是长期限制；Phase 1 可在 ADR 评审后加入 serde、tokio、tracing、rusqlite 等依赖。

## 目标 Workspace

| 目标 crate/组件 | 责任 | 首个迁移来源 |
|---|---|---|
| `compatforge-api` | 公共 DTO、版本协商、错误码 | `Models.swift` |
| `compatforge-capability` | CPU/GPU/OS/Provider 探测 | `HostEnvironmentService`、Diagnostics |
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

### macOS

保留现有 SwiftUI 作为 Phase 1 过渡前端，但先定义：

- `RuntimeClient`：capabilities、compile、launch、events、terminate；
- `BottleClient`：list、create、snapshot、migrate、restore；
- `CatalogClient`：refresh、list、verify、install；
- `DiagnosticsClient`：query events、run checks、export redacted bundle。

`MacWinStore` 拆成 feature model，`ContentView` 按 Desktop、Bottle、Catalog、Diagnostics、Lab、Settings 分文件。新 feature 不得直接实例化 `WineRunner`。

### Linux

Phase 2 采用 CLI-first，稳定 API 后再选择 Qt 6/QML 或 GTK4。UI 选择不能改变 Core/Provider 边界。

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
| RuntimeEvent | process supervisor | diagnostics store、UI |
| CompatibilityResult | compat-lab | policy scorer、catalog publishing pipeline |

任何组件不得绕过权威所有者直接修改其文件。尤其 UI 不直接编辑 Bottle JSON，Provider 不直接更新 Recipe，测试结果不直接提升兼容等级。
