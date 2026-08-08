# ADR-0002：Provider 分维度选择与四级回退

- 状态：Accepted
- 日期：2026-08-07

## 背景

Mac-Win 当前启动路径把 Wine、Rosetta 和 macOS 进程方式绑定在一起；图形预设也直接生成 GPTK/DYLD/Wine 环境变量。ARM、Android、VM 和 Remote 无法在此模型中自然加入。

## 决策

将运行路径拆成独立 Provider 维度：

- Runtime：Wine、VirtualMachine、Remote；
- Architecture Translator：Native、Rosetta、FEX、Box64、QEMU；
- Graphics Backend：WineD3D、DXVK、vkd3d-proton、D3DMetal、MoltenVK、Virtualized、Remote；
- Platform Adapter：macOS、Linux、Android 的进程、文件、sandbox、显示/输入。

默认运行回退是：同架构 Wine → Wine + CPU Translator → 本地 Windows VM → Remote Windows。策略先执行硬约束，再使用相同矩阵上的认证结果评分，最后考虑性能、资源、成本和用户偏好。

## 约束

- Wine ARM64 不被当作 x86 指令翻译器；Host 与 Guest 架构分开建模。
- Provider probe 只说明“可用”，policy evaluation 才说明“适合”。
- 用户/企业可以禁止 VM、Remote、网络、设备或特定 Provider。
- driver-dependent 应用不强行选择 Wine。
- 回退必须记录 decision trace，禁止静默把本地任务上传云端。

## 结果

新平台和 Provider 可独立加入；Rosetta/GPTK 的生命周期不再决定整个产品架构。代价是组合矩阵扩大，必须依靠自动化 compat lab 与精确结果主键控制复杂度。
