# 平台支持矩阵

“支持”按 Host OS × Host CPU × Guest EXE CPU × Runtime × Graphics 组合定义，不用一个模糊的应用兼容标签覆盖全部设备。

## 目标矩阵

| Host | Host CPU | Guest | 默认 Runtime | Translator | Graphics | 级别 |
|---|---|---|---|---|---|---|
| macOS | ARM64 | x86 / x86_64 | Wine | Rosetta 过渡；替代 Provider 必须可插拔 | D3DMetal、WineD3D；MoltenVK 路径可选 | Tier 1 |
| macOS | ARM64 | ARM64 | ARM64 Wine 实验路径 | Native | WineD3D/Metal | Preview |
| macOS | x86_64 | x86 / x86_64 | Wine | Native | WineD3D | Maintenance |
| Linux | x86_64 | x86 / x86_64 | Wine / 适配后的 Proton 组件 | Native、新 WoW64 | DXVK、vkd3d-proton、WineD3D | Tier 1 |
| Linux | ARM64 | x86 / x86_64 | Wine | FEX 首选，Box64 补充，QEMU correctness | DXVK、vkd3d-proton、WineD3D | Tier 2 |
| Linux | ARM64 | ARM64 | ARM64 Wine | Native | WineD3D/Vulkan | Preview |
| Android | ARM64 | x86 / x86_64 | Wine Android | Box64/FEX 类 Provider | DXVK + vendor Vulkan；Zink/WineD3D 回退 | Preview |
| Android | ARM64 | ARM64 | ARM64 Wine 实验路径 | Native | vendor Vulkan | Experimental |

## Windows 开发主机

可以在 Windows 上开发和验证以下内容：

- Rust domain/orchestrator/ABI 与 CLI；
- JSON Schema、Recipe 编译、签名和迁移器；
- 策略单测、golden tests、模拟 Provider；
- Windows probe EXE 构建；
- 通过 Hyper-V/VMware/WSL2 运行 Linux 集成环境。

Windows 不能替代 macOS Metal/AppKit/Rosetta、Linux NTSync/Wayland/Vulkan 驱动或 Android Surface/SAF 的实机认证。CI 中的 Windows job 是可移植性门禁，不表示 Windows 本身是首期运行目标。

## Tier 定义

| 级别 | 承诺 |
|---|---|
| Tier 1 | 每次合并 CI，固定实机矩阵，阻塞性回归修复，发行包与升级/回滚 |
| Tier 2 | 定期实机矩阵，限定设备/驱动清单，允许已知性能差异 |
| Preview | 明确设备白名单，数据格式向前兼容，不承诺所有应用 |
| Experimental | 研究验证；不进入默认选择，不承诺迁移稳定性 |
| Maintenance | 只修安全和严重回归，不扩展新能力 |

## 不支持与自动回退

以下应用默认不强行走 Wine：

- 需要 Windows 内核驱动、反作弊内核模块、专用 USB 驱动或低层过滤驱动；
- 依赖无法替代的 Windows 服务、Hyper-V、特定企业身份组件；
- 安装器或 EULA 禁止目标环境；
- 认证矩阵明确标记本地路径不可靠。

策略在用户允许时选择本地 Windows VM；设备或授权不满足时再选择 Remote Provider。回退原因必须显示给用户并写入 decision trace。

## Android 特殊门禁

进入 Preview 前至少满足：

- Adreno 与 Mali 各一个设备族，三档 SoC 性能档位；
- 16 KB page-size 构建；
- 触摸、鼠标、键盘、手柄、IME、剪贴板和外接显示器用例；
- Android 生命周期切换不破坏 Bottle；
- SAF 只映射用户选择目录；
- 渠道对动态代码、下载 Runtime 和 JIT 的政策评审；
- 崩溃、温控、内存压力和后台限制测试。
