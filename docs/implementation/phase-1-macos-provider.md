# Core 0.8：macOS Provider 纵向切片

`compatforge-provider-macos` 把 Core 0.7 的 Runtime Store、Capability、Planner 与 Process Supervisor 接成首条 macOS 实际运行链路。

## 输入与输出

输入 `macos-provider.schema.json`，其中只包含固定 Runtime Pack、物化根目录、相对入口和入口 digest。Probe 输出：

- Wine Runtime Provider；
- HostProbe 已证明的 Native CPU Provider；
- 仅由 x86_64 Wine 实际执行证明的 Rosetta CPU Provider；
- 与 Wine 同 Pack 的 WineD3D；
- 可选且同 Pack 绑定的外部 D3DMetal Provider；
- 可直接交给 PolicyEngine 的 RuntimeBinding。

## 失败语义

配置结构、ID、digest 或 capability 越界属于契约错误并拒绝加载。Pack、物化根、入口 digest、Mach-O 架构或版本命令失败会产生 unavailable Provider，不生成 RuntimeBinding，也不会继续执行未验证入口。CoreConfig 只能从 available snapshot 建立。

## 明确边界

- 不下载、解包或更新 Runtime；
- 不扫描 `PATH`，不执行 shell；
- 不使用 `/usr/bin/arch`；
- 不把 Rosetta 推断为系统永久能力；
- 不捆绑 D3DMetal；
- 不修改 Mac-Win 或 ForgeOS。

## 本地无头预览补充

`tools/register_macos_local_wine.py` 是只接受显式本地路径的开发预览工具，
不是正式 Runtime materializer。它不发现、下载、执行或分发 Wine，只生成
unsigned preview bundle、既有 schema v1 Provider 配置和本地 receipt。

外层 opt-in 验收工具可调用 `tools/discover_macos_wine.py`。发现器不扫描
`PATH` 或递归遍历磁盘，只检查 CrossOver、Whisky 与相邻 Mac-Win 开发构建的
固定候选位置；候选必须是同一根内的普通可执行文件、两个入口均为单架构
x86_64 Mach-O，并在受限环境中实际通过 `--version`。发现结果随后仍进入相同的
显式登记、Provider 和 PreparedLaunch 信任链。调用方也可显式提供完整四元组
`root/wine/wineserver/version` 覆盖自动选择。

Provider 生成 Runtime Binding 时把已验证的 Wine 与 wineserver SHA-256 放入
受保护环境项。Process Supervisor 在创建进程前重新验证两个固定入口；请求环境
不能覆盖这些值。该机制补齐 Provider probe 与 PreparedLaunch 启动之间的本地
Runtime 漂移窗口，但不把 preview Pack 提升为 stable/candidate 信任等级。
