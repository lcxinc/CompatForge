# 迁移工作分解与退出标准

工作按能力依赖排序，不按 UI 页面排序。总路线是 macOS 解耦 → Linux x86_64 → Linux ARM64 → Android ARM64；允许团队并行，但不在核心契约未稳定前启动完整 Android 产品化。

## Phase 0：契约与仓库基线

目标周期：2–4 周。当前仓库已交付设计骨架，仍需完成与 Mac-Win 的首轮集成验证。

### 当前实现检查点（0.2.0）

- 已完成：版本化 Rust DTO、Context/LaunchRequest → LaunchPlan、固定 Runtime digest、跨平台路径、JSON Store、opaque C context、结构化 FFI 错误；
- 待接入 Mac-Win：`RuntimeClient` protocol、动态/静态库装载、Swift smoke test；
- 仍未实现：host probe、进程启动/监督、Runtime 安装、Bottle 迁移写入。

### 工作包

- P0.1：确认根许可证、贡献方式和第三方合规负责人；
- P0.2：稳定 schema v1/v2、canonical JSON 与签名算法 ADR；
- P0.3：给 Mac-Win 增加 `RuntimeClient`/`BottleClient`/`DiagnosticsClient` protocols；
- P0.4：建立 Swift ↔ C ABI smoke target；
- P0.5：把源 Wine/Recipe/fixture 清单导出为带 digest 的迁移 inventory；
- P0.6：建立 macOS 实机 CI runner 与代表应用最小集合。

### 退出标准

- Rust workspace 在 Linux/macOS/Windows CI 通过；
- Swift 能读取 ABI/API 版本并执行一次无副作用 plan；
- Recipe v1→v2 转换器对现有 catalog 全量通过；
- 所有迁移输入固定到源 commit 与 digest；
- 根许可证与第三方分发政策明确。

## Phase 1：macOS 核心解耦

目标周期：3–4 个月；建议 4–6 人。

### 工作包

| 编号 | 工作 | 主要交付 |
|---|---|---|
| P1.1 | Host Capability | macOS/CPU/GPU/Rosetta/Wine/图形能力结构化 probe |
| P1.2 | Runtime Pack | manifest、内容存储、签名、安装、固定、回滚 |
| P1.3 | Launch Planner | hard constraints、provider scoring、decision trace |
| P1.4 | Process Supervisor | 进程组、stdout/stderr events、取消、超时、wineserver 清理 |
| P1.5 | macOS Providers | Wine、Rosetta、D3DMetal/WineD3D、App Support/沙箱适配 |
| P1.6 | Recipe v2 | 现有 profile/recipes 数据化、typed action、签名与灰度 |
| P1.7 | Bottle Bridge | 旧 manifest 双读、snapshot、layout migration、rollback |
| P1.8 | SwiftUI Strangler | feature clients、legacy/new backend toggle、Store/View 拆分 |
| P1.9 | Diagnostics | 结构化事件、脱敏、support bundle、repair audit |
| P1.10 | macOS Lab | Intel/Apple Silicon、20 个代表应用、图形/IME/字体 probes |

### 切换顺序

1. host probe；
2. compile LaunchPlan（仍交给 legacy launch）；
3. process supervisor；
4. Wine + Rosetta provider；
5. Recipe/compatibility profile；
6. install flow；
7. Bottle 写入与迁移；
8. 删除 legacy runner 分支。

### 退出标准

- UI 或 Bottle 不再假设 `/usr/bin/arch -x86_64`；
- 无开发机绝对路径进入发行包；
- 主要 macOS use case 默认走 Rust Core，legacy backend 可关闭；
- Bottle 固定精确 Runtime Pack digest 且可一键回滚；
- 至少 20 个代表应用在 Intel/Apple Silicon 有结构化结果；
- Runtime、Recipe、SBOM、NOTICE 和签名进入发行流水线。

## Phase 2：Linux x86_64 产品化

目标周期：4–5 个月；建议 6–8 人。

### 工作包

- Linux platform adapter：XDG、进程、namespace、portal、字体、IME；
- Wine 新 WoW64 与 NTSync capability/provider；
- DXVK、vkd3d-proton、WineD3D backend；
- X11/Wayland、PipeWire/PulseAudio；
- CLI-first 管理、安装、诊断与 lab；
- Flatpak/原生包的权限与 Runtime 分发评估；
- AMD/Intel/NVIDIA 固定硬件矩阵；
- 共享 Recipe 与跨平台差异覆盖规则。

### 退出标准

- 30–50 个代表应用完成自动安装或启动验证；
- D3D9/11/12 与 32/64 位 probes 完整；
- Runtime Pack 可升级/回滚，Bottle 不需要重建；
- 默认只映射用户选择目录；
- macOS/Linux 使用同一 Recipe schema 和结果模型。

## Phase 3：Linux ARM64 与 Apple Silicon 长期路线

目标周期：5–6 个月；建议 8–10 人。

### 工作包

- Translator Provider API 稳定化；
- FEX 默认后端、Box64 兼容补充、QEMU correctness；
- rootfs 管理、许可与更新；
- Host/Guest/Process 架构解析与 WoW64 组合测试；
- ARM64 CI + 实机实验室；
- Apple Silicon 在 Rosetta 受限情形的替代研究；
- ARM64 Wine/ARM64 Windows 应用实验路径；
- 性能、JIT、安全与崩溃诊断。

### 退出标准

- Linux ARM64 至少 20 个非驱动应用通过 smoke；
- i386/x86_64 probes 均可执行；
- Recipe 可固定 translator，策略也可按认证结果自动选择；
- translator 失败能回退并给出结构化原因；
- macOS Core 不再把 Rosetta 当必然存在的系统能力。

## Phase 4：Android ARM64 与企业能力

目标周期：6–8 个月；建议 10–14 人。

### 工作包

- Kotlin/Compose shell 与 JNI；
- Wine/Translator Runtime Pack 的 Android 分发策略；
- Surface/XServer、触摸/鼠标/键盘/手柄/IME/剪贴板；
- SAF、外接显示器、生命周期、前台服务；
- Adreno/Mali、4 KB/16 KB page、温控与内存矩阵；
- 企业私有 catalog、策略、设备管理、审计和证书；
- Remote Provider 与本地失败回退；
- AI Repair 候选生成与受控验证流水线。

### 退出标准

- 两类 GPU、三档 SoC 的认证矩阵；
- 生命周期和升级不破坏 Bottle；
- 目标渠道对 JIT/动态 Runtime 的政策通过；
- 用户文件只通过 SAF 显式授权；
- Linux ARM64 与 Android ARM64 共享大部分 Recipe 规则。

## 人力与节奏

深度调研给出的完整产品估算约 150–220 人月、18–24 个月。应按季度重新估算，不把研究值当承诺日期。最小长期角色包括：Rust/core、Wine/native、图形/translator、Swift/Linux/Android frontend、QA/compat lab、DevOps/release、安全/许可与产品兼容工程。

## 决策门

每个 Phase 启动前重新确认：

- 上一阶段 schema/ABI 是否稳定；
- Runtime 组件许可证和分发是否可行；
- 实机与代表应用是否到位；
- 失败是否能诊断和回滚；
- 新平台是否带来足够用户价值，而不是只增加组合爆炸。
