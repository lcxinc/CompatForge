# Mac-Win 源工程审计基线

## 基线

- 源仓库：[`a1112/Mac-Win`](https://github.com/a1112/Mac-Win)
- 分支：`main`
- 审计提交：[`4282ed9e3d743219d5b35b8bda47ac29a7c663d5`](https://github.com/a1112/Mac-Win/commit/4282ed9e3d743219d5b35b8bda47ac29a7c663d5)
- 审计日期：2026-08-07
- 初始平台提交：`8e214fffae98bda57502b908a1bea7856b5324b6`

本文件把调研报告结论固定到可复核的代码事实。迁移开始后不随源仓库漂移；若重新基线，新增记录并说明差异。

## 构建与平台锁定

`MacWinManager/Package.swift` 使用 Swift tools 6.0，只声明 `.macOS(.v14)`，产品是 `MacWinCore` 与 `MacWinManagerApp`。核心名称虽已分层，但仍属于只在 macOS 编译的 Swift target。

## 重点规模与耦合

| 文件 | 行数 | 观察 | 迁移风险 |
|---|---:|---|---:|
| `WineRunner.swift` | 3,783 | 导入 Darwin/CoreText；多处 `/usr/bin/arch -x86_64`；运行、修复、日志、终止混合 | 最高 |
| `BottleService.swift` | 3,581 | Bottle 生命周期、注册表、字体、网络、应用发现混合 | 最高 |
| `ApplicationCompatibilityProfile.swift` | 1,962 | 约 40 类应用特例编译为 enum/分支 | 高 |
| `MacWinStore.swift` | 3,217 | 大量 `@Published` 状态与二十多个服务实例 | 高 |
| `ContentView.swift` | 7,013 | 从窗口 chrome 到测试/支持/日志的大量 View 集中 | 高 |
| `WindowsDesktopView.swift` | 1,828 | AppKit/ImageIO/SwiftUI 混合，桌面外观与运行状态相连 | 中高 |
| `EngineRegistry.swift` | 353 | Runtime、Wine、Rosetta 和 probe 使用开发机绝对路径 | 最高 |
| `GraphicsPreset.swift` | 103 | WineD3D/GPTK/DXR 与 `DYLD_*`/DLL override 写在 enum | 高 |
| `Models.swift` | 456 | Engine/Bottle/Recipe/Catalog 概念有保留价值，但缺 Host/Guest/Provider 维度 | 中 |
| `MacWinPaths.swift` | 50 | 固定 macOS Application Support 与目录命名 | 中 |
| `JSONStore.swift` | 49 | 原子文件写思想可保留，但无跨进程事务/索引 | 中 |
| `CatalogService.swift` | 204 | 已有 P-256 签名与 Recipe SHA-256 验证，是重要资产 | 中 |

## 直接证据

### 运行器

在审计基线中：

- `WineRunner.swift:1-2`：`import Darwin`、`import CoreText`；
- `WineRunner.swift:163`：command line 固定为 `/usr/bin/arch -x86_64 ...`；
- `WineRunner.swift:299-302`、`416-418`、`727-729`：多条进程路径重复同一假设；
- `WineRunner.swift:471-474`、`1067-1071`：直接以 Darwin signal 管理进程；
- `WineRunner.swift:1149-1155`：wineserver 终止也固定走 `arch -x86_64`。

这证明 Wine Runtime、CPU Translator 与 Platform Process Launcher 尚未分离。

### Engine Registry

`EngineRegistry.swift:7-10` 包含 `/Users/.../project/Mac-Win/refs/...` 形式的 Wine build、WoW64 build、CrossOver runtime 与 Rosetta helper 路径；`174-175` 还把测试 EXE 的开发机路径写进 health check。

这类值不能通过“换一个默认目录”修复，必须改为 Runtime Pack manifest + content-addressed store + host configuration。

### 兼容知识

`ApplicationCompatibilityProfile.swift` 从第 4 行开始列出浏览器、CEF、Qt、Java、Office、CAD/EDA、切片器等大量特例。它们是有价值的经验，但代码表示导致：

- 新规则必须重新编译应用；
- 无法独立签名、回滚、灰度和社区审查；
- 难以表达 OS/CPU/GPU/Runtime 版本条件；
- 规则动作与匹配逻辑、环境变量、参数耦合。

迁移目标是 Recipe v2 与 typed repair action，不是简单把 enum 名称复制成 JSON。

### 现有数据资产

资源目录已有签名 catalog index、7-Zip/Firefox/LibreOffice/Steam/VLC 等 Recipe，以及大量兼容/测试/诊断服务和 Windows probe fixture。`CatalogService.swift` 验证 P-256 签名与每个 Recipe SHA-256，说明供应链基础概念已存在。

这些资产应优先提取：它们比现有 GUI 或某个本地 Wine build 更能形成长期兼容数据库。

## 迁移分类

### 保留并升级

- Bottle/Engine/Launcher/Recipe/Catalog 领域概念；
- 签名 catalog 与 digest 校验；
- Windows executable inspector/icon extractor；
- 软件样本、冒烟矩阵、测试计划、运行历史；
- 诊断分类、修复审计、支持分诊与支持包；
- Wine patches 和 probe fixtures。

### 过渡适配

- SwiftUI/macOS UI；
- macOS 原生窗口、输入、字体与图标集成；
- 当前 Bottle 目录和 JSON manifest；
- Rosetta 与 D3DMetal（作为可选平台 Provider）。

### 重新实现

- LaunchPlan 与 Provider 策略；
- Wine/VM/Remote Runtime Provider；
- CPU Translator Manager；
- Graphics Backend Manager；
- 进程监督、结构化事件与跨平台取消；
- Runtime Pack registry/update；
- 跨平台文件系统、sandbox、mount 和 device policy。

## 审计局限

该基线是工程迁移设计审计，不替代：

- 在真实 macOS 环境构建和运行完整 Swift test suite；
- Wine/patch 的逐项许可证与上游状态审查；
- Runtime 二进制的 SBOM/漏洞扫描；
- 实机 GPU/应用兼容认证；
- 公开发布前的安全审计。
