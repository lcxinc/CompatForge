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
