# ADR-0011：Inspection-bound Guest Artifact 与 PreparedLaunch

## 状态

Accepted，Core 0.10。

## 背景

Core 0.9 的 PE inspection 与 LaunchPlan 是两条独立链路。调用方可以在检查后继续提交自行声明的架构、摘要和可变宿主路径；原文件也可能在检查与启动之间被替换。Runtime Pack 已固定到内容摘要，但来宾程序没有同等的证据边界。

## 决策

新增独立 `compatforge-guest-artifact` 内容库和 opaque `PreparedLaunch`：

1. 只接受绝对、无父目录遍历、非符号链接的普通文件；一次读取最多 64 MiB。
2. 对同一字节缓冲执行有界 PE inspection，再以报告的 SHA-256 物化到 `guest-artifacts/objects/sha256/<digest>`。
3. 第一版仅接受 x86/i386 或 x86_64 的 Windows Console executable；DLL、GUI、Native、EFI、ARM 和驱动 fail closed。
4. 调用方声明的路径、架构和可选 SHA 必须与选择文件及 inspection 一致；规划只使用内容库路径和检查架构。
5. `LaunchPlan.guestArtifact` 固定 digest、大小、对象路径、原始文件名、架构、image kind、subsystem 和 inspection schema。
6. `PreparedLaunch` 私有保存可信请求、完整 inspection、计划及 Context 指纹。启动前必须用当前 Context 重新编译并逐字段相等，复验对象路径、大小和 digest。
7. 带 `guestArtifact` 的旧序列化 LaunchPlan 在进入进程创建前同样复验对象内容；不带该字段的既有受信任 helper 保持兼容。

C ABI major 保持 1，API 升至 0.10.0，并新增 `cf_launch_prepare`、两个只读 getter、`cf_prepared_launch_start` 和 release 函数。

## 后果

- 修改原始来源文件不会改变已准备计划。
- 来宾架构自动进入 Translator 选择，不能由前端伪报。
- Guest Artifact 与 Runtime Pack 保持独立生命周期和信任策略。
- 当前内容复验与进程创建之间仍依赖同一用户存储权限；真正的 daemon/OS sandbox 应进一步使用受保护目录和句柄级执行策略。
- 本切片不执行 fixture，不新增 daemon、Qt/QML、ForgeOS 源码或图形路径。
