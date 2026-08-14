# 测试与兼容认证策略

CompatForge 的核心交付物不是“能启动一次”，而是可复现的兼容结论。测试分为代码正确性、契约、Provider、迁移、应用兼容和非功能六层。

## 测试层级

| 层 | 目标 | 示例 | 合并门禁 |
|---|---|---|---|
| Unit | 纯策略和模型 | Provider 过滤、回退顺序、版本比较 | 每次提交 |
| Contract | Schema/C ABI/IPC 兼容 | JSON golden、旧 reader、新 writer | 每次提交 |
| Provider | 适配器符合统一语义 | probe 无副作用、argv 无 shell、terminate 幂等 | Provider 变更 |
| Migration | 旧 Bottle/Recipe 可恢复迁移 | v1→v2、断电点、回滚、双读 | 存储变更 |
| Windows probes | Win32/64 API 与图形能力 | 窗口、字体、IME、COM、WIC、D3D、网络 | Runtime 变更 |
| App smoke | 代表应用真实路径 | 安装、首启、窗口、文件读写、退出 | Release candidate |
| Non-functional | 性能、安全、资源与稳定性 | 冷启动、FPS、内存、温控、fuzz、长跑 | 发布门禁 |

## 兼容结果主键

结果必须绑定：

```text
recipe digest
+ installer digest
+ runtime pack digest
+ host OS/version/architecture
+ GPU/driver/device family
+ translator/backend versions
+ test suite version
```

任何一项变化都产生新结果，不覆盖旧记录。兼容评级由规则汇总多个认证结果，不能由单次手工测试直接修改。

## 代表应用分组

- 基础 Win32：7-Zip、Notepad++、SumatraPDF；
- 浏览器/CEF/Electron：Firefox、Chromium 系应用；
- Office/生产力：LibreOffice/WPS 类；
- Java/SWT/JavaFX：DBeaver、JabRef、ProjectLibre；
- Qt/OpenGL：JASP、Krita、FreeCAD、切片器；
- 图形与游戏：D3D9、D3D11、D3D12 probes，Steam bootstrap；
- 工业：PLC、串口/USB 只在隔离实验室和合法设备上；
- 32 位：i386 安装器与运行程序；
- 字体/IME/本地化：中日韩输入、时区、文件名和系统字体。

应用清单需要可公开分发或由测试环境合法提供。CI 不提交商业安装包。

## 平台实验室

### macOS

- Apple Silicon 至少两代；当前与下一主版本；
- Rosetta 可用/不可用；
- D3DMetal、WineD3D、可选 MoltenVK；
- Retina、外接屏、输入法、休眠/唤醒。

### Linux

- AMD/Intel/NVIDIA，Mesa 与 proprietary driver；
- X11/Wayland；PipeWire/PulseAudio；
- x86_64 与 ARM64；FEX/Box64/QEMU；
- NTSync 可用/不可用；Flatpak/原生包。

### Android

- Adreno/Mali、三档 SoC；
- Android 版本和 4 KB/16 KB page；
- 触摸/鼠标/键盘/手柄/IME/外接屏；
- 生命周期、热限制、内存压力、后台恢复。

## 失败分类

每个失败至少归入：unsupported、runtime-regression、recipe-regression、host-driver、translator、graphics、installer-upstream、policy-blocked、test-infrastructure。未知失败不能自动发布为兼容 Recipe。

## Mac-Win portable asset 离线门禁

[Mac-Win portable asset 迁移边界](migration/macwin-portable-assets.md)记录冻结源身份、90 条输入的真实状态、隔离/延期条件和精确输出摘要；[Mac-Win patch 来源证据](migration/macwin-patch-provenance.md)进一步绑定 11 个 patch 的上游基线、许可证判定、逐项隔离原因和 committed bytes。当前 patch 结果为 0 retained / 11 quarantined，全局结果为 2 converted + 4 deferred + 84 quarantined。该门禁只验证离线表示与副作用边界，不执行或应用迁移资产，也不产生应用兼容结论。

```text
python -B tools/convert_macwin_assets.py --check
python -B scripts/validate_repository.py
```

评审生成变化时还需显式运行两次 `python -B tools/convert_macwin_assets.py --write`，确认第二次保持字节完全不变，并复核 source pack、generated graph、Git 元数据、Runtime Pack store、Bottle fixtures 与外部 sentinel 的前后快照。

## Phase 0 门禁

当前仓库执行：

- 所有 JSON 可解析、schema `$id` 唯一、示例含 schemaVersion；
- Markdown 本地链接有效；
- Cargo workspace 成员存在；
- 新仓库不重新引入已知开发机绝对路径；
- Rust 在 Linux/macOS/Windows 通过 fmt、check、test、clippy。
- 进程监督契约覆盖启动/输出/退出顺序、幂等终止、最大运行时限和 Wine prefix 排他租约；三平台 CI 分别编译并运行各自的 process group/Job Object 实现。
- Host Capability 在三平台 Runner 实际执行；报告必须通过 Domain 校验，并证明基线探测不会声明未固定 Runtime/Graphics Provider。
- macOS Runner 构建真实 x86_64 Mach-O Wine fixture；Provider 必须复验 Runtime Pack/入口 digest，生成 Context 与 LaunchPlan，实际输出事件并通过显式 terminate 清理进程树。Apple Silicon Runner 上该执行同时是 Rosetta 的 Pack 级证据，Intel Runner 则必须保持 Native。
- ForgeOS C fixture 在 Linux CI 中使用 `dlopen`/`dlsym`，先校验 API `0.6.0`/ABI 1，再解析新增 ABI v1 符号；随后创建已验证 Context、调用 `cf_capabilities_get` 并以 `cf_string_free` 释放独立输出 buffer。
- CapabilityReport Domain 使用 boolean/string/number 标量闭集；负向测试拒绝 feature 与 observation value 中的 object、array 和 null，FFI 输出再经过严格 DTO 反序列化、Domain 条件/唯一性校验及 Schema v1 标量断言。
- Context capability 查询覆盖 Linux x86_64/ARM64 映射、空 Provider、不可用 Provider、NULL 输出语义、确定性排序、无文件/进程物化边界，以及 token、用户路径、任意进程 observation 不进入公开报告；该路径不依赖或调用 PE 解析模块。
- PE inspection 覆盖 DOS/PE signature、optional header/machine 一致性、section/header 上限、RVA 映射、import 终止和名称闭集；确定性无代码 fixture 在三平台 CLI 检查，Linux C consumer 先验证 API 0.9.0/ABI 1 再解析 additive symbol。
- PreparedLaunch 覆盖来源修改不影响固定对象、对象篡改、符号链接、路径/架构/digest 伪报、Context/sandbox/工作目录漂移和确定性重编。Linux 动态 C consumer 验证 API 0.10.0/ABI 1 的 `prepare → inspection-get → plan-get`；该 fixture 不调用 start，不执行真实 PE。
- Runtime Pack 覆盖 NIST SHA-256 vectors、流式边界、manifest 规范化排序、组件/manifest digest 失败、stable/candidate 签名 fail-closed、幂等安装、对象复用、active ref 原子可见性、目标重校验与回滚。
- 三平台 CI 使用两个本地 preview bundle 执行 `install v1 → install v2 → verify v2 → rollback v1`；fixture 只包含可公开文本 blob，不包含 Wine 或商业二进制。
