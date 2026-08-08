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

## Phase 0 门禁

当前仓库执行：

- 所有 JSON 可解析、schema `$id` 唯一、示例含 schemaVersion；
- Markdown 本地链接有效；
- Cargo workspace 成员存在；
- 新仓库不重新引入已知开发机绝对路径；
- Rust 在 Linux/macOS/Windows 通过 fmt、check、test、clippy。
- 进程监督契约覆盖启动/输出/退出顺序、幂等终止、最大运行时限和 Wine prefix 排他租约；三平台 CI 分别编译并运行各自的 process group/Job Object 实现。
