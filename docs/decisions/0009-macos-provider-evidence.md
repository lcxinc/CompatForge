# ADR-0009：macOS Provider 使用 Pack 绑定的执行证据

- 状态：Accepted
- 日期：2026-08-08

## 背景

macOS ARM64 运行 x86_64 Wine 需要 Rosetta，但文件存在、`PATH` 命中或固定调用 `/usr/bin/arch -x86_64` 都不能证明某个 Runtime Pack 可运行，也会把旧 Mac-Win 的宿主假设重新带入 Core。D3DMetal 还具有独立授权与分发约束，不能作为内建依赖默认声明可用。

## 决策

1. macOS Provider 配置只引用已安装 Runtime Pack 的精确 `packId/packDigest` 和物化根目录内的相对入口。
2. Probe 在执行前复验 manifest、全部内容对象、入口 SHA-256、Mach-O 架构、可执行权限及 canonical root containment。
3. Wine 与 wineserver 版本探测直接执行固定入口，使用独立 argv、清空环境与五秒上限；不扫描 `PATH`、不调用 shell、不依赖 `/usr/bin/arch`。
4. ARM64 主机成功执行已验证的 x86_64 Wine 才发布该 Runtime 对应的 Rosetta Provider；native Runtime 不推断 Rosetta 已安装。
5. WineD3D 与 Wine Runtime 使用同一 digest。D3DMetal 只有作为用户提供、同 Runtime Pack 绑定且 probe file 验证成功的可选组件时才可用；Core 不下载或再分发它。
6. Provider 只产生 CapabilityReport 与固定 RuntimeBinding，选择、授权、启动、事件和终止仍由既有 Orchestrator 与 Process Supervisor 负责。

## 结果

macOS 的 `probe → context → plan → launch/event/terminate` 可以无头重放，Rosetta 结论不再是系统级猜测，Provider 也不能用可变路径替换计划中的 Runtime。当前切片假设 Pack 已由受信任物化器准备；通用 archive 解包、签名密钥和 GPU 功能认证仍是独立后续工作。
