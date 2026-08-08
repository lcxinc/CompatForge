# ADR-0006：进程树与 Wine prefix 生命周期归 Core 所有

- 状态：Accepted
- 日期：2026-08-08

## 背景

直接持有 `std::process::Child` 只能可靠终止根进程。Wine、安装器和启动器会创建后代进程，`wineserver` 还可能在应用退出后继续驻留。若 PID、终止时限或 `wineserver` 命令交给 Qt/QML，前端会重新承担平台差异与安全边界。

## 决策

1. `compatforge-process` 拥有根进程与全部后代；Qt/QML、CLI 和其他客户端只持有 opaque launch handle。
2. Unix 子进程在 `exec` 前创建独立 process group；Windows 子进程进入带 `KILL_ON_JOB_CLOSE` 的 Job Object。
3. `SupervisorPolicy` 来自受信任 `CoreConfig`，编译进 LaunchPlan 后在启动前重新授权。终止依次执行软终止、宽限期、Wine 清理和强制树终止。
4. Wine Runtime Binding 可固定 `wineserverExecutable`。Core 使用同一受控环境与 `WINEPREFIX` 执行标准 `-k`、`-w`，不拼接 shell 命令。
5. 一个 Core 进程内，同一受管 prefix 同时只允许一个 launch lease。这样 prefix 级清理不会终止另一个受管会话。

## 结果

- handle 释放、用户取消和超时使用同一幂等清理路径；
- Unix 后代与 Windows 子进程树不再依赖前端逐个追踪；
- RuntimeEvent 可解释软终止、超时、升级与 wineserver 清理；
- Windows 控制台软终止是尽力而为，Job Object 提供可靠强制兜底；
- 当前 prefix 租约只在单个 Core 进程内有效。Desktop daemon 出现后，租约必须提升为 daemon 权威状态或跨进程文件锁；
- 本决策不等于 OS sandbox，namespace/seccomp/Landlock、seatbelt 与资源限制需要独立 ADR。
