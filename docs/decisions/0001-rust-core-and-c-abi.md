# ADR-0001：Rust 控制面与稳定 C ABI

- 状态：Accepted
- 日期：2026-08-07

## 背景

Mac-Win 的核心与 UI 都使用 Swift 6/macOS 14。核心执行代码直接依赖 Darwin、CoreText、AppKit 语义和 `/usr/bin/arch`，无法被 Linux/Android 复用。把全部代码改写为 C 会增加内存安全和并发风险；把 Wine/FEX/DXVK 等重写为 Rust 既不现实也不产生产品价值。

## 决策

- Rust 负责领域模型、策略、任务编排、Bottle/目录/诊断与安全敏感逻辑。
- C ABI 是 Swift、Kotlin/JNI、Qt/C++ 与第三方 SDK 的稳定二进制边界。
- Wine、FEX、Box64、QEMU、DXVK、vkd3d-proton、MoltenVK 保持其原生 C/C++/独立进程形态。
- 跨 ABI 只传 opaque handle、稳定标量和版本化 JSON/bytes，不暴露 Rust 内部布局。
- Desktop 可在 C ABI 之上提供守护进程 IPC；两者共享 schema。

## 结果

优点：核心可跨平台复用，内存/并发安全更好，前端可独立演进，第三方 Runtime 不必 fork 到单一语言。

代价：需要 FFI/IPC 所有权规范、绑定生成、panic 隔离和多构建系统集成；平台专用能力仍需 Swift/ObjC、C++、Kotlin 等 adapter。

## 被否决方案

- 继续以 Swift 作为跨平台核心：Linux/Android 工具链与平台 API 边界不合适，且现有耦合不会自然消失。
- 全部使用 C/C++：缺少对控制面复杂状态与安全逻辑的足够保护。
- 重写 Wine/Translator/Graphics：周期、兼容性和维护成本不可接受。
