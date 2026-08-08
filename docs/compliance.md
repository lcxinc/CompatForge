# 第三方合规门禁

CompatForge 可以商业化，但不能把组合 Runtime 当成“一个许可证”。每个版本的 Runtime Pack 都必须记录其完整组件图、链接方式、修改、补丁、源码对应物和分发义务。

## 初始组件清单

| 组件 | 常见许可证方向 | 集成建议 | 发行前动作 |
|---|---|---|---|
| Wine | LGPL-2.1-or-later | 独立 Runtime/动态边界 | 保存精确源码、修改补丁、构建说明与替换能力 |
| DXVK | Zlib | Runtime 组件 | 保留版权/许可，记录版本与 digest |
| vkd3d-proton | LGPL-2.1 | Runtime 组件 | 核对链接和修改义务，提供对应源码 |
| FEX | MIT | 独立 translator Provider | 保留许可证，审计 rootfs 内容 |
| Box64 | MIT | 独立 translator Provider | 保留许可证，审计打包的 x86 库 |
| QEMU | GPL-2.0 | 独立进程兜底 | 避免静态嵌入闭源核心；履行源码义务 |
| MoltenVK | Apache-2.0 | macOS graphics component | 保留 NOTICE 与许可证，审计依赖 |
| GPTK/D3DMetal | Apple 专有条款 | 可选外部/合规 Provider | 每版检查可再分发、用途与渠道限制 |
| Windows VM/Image | Microsoft/用户许可 | 不随意再分发镜像 | 验证 Windows、RDS/VDI、用户与应用许可 |

表中是工程设计提示，不替代法律意见；实际条款以所固定版本和分发方式为准。

## Runtime Pack 必填证据

- 组件名、版本、上游 URL、commit/tag、SHA-256；
- SPDX identifier 或许可证全文；
- 是否修改及 patch 列表、上游状态；
- 构建工具链、选项、依赖和目标平台；
- SPDX/CycloneDX SBOM；
- source offer/源码下载位置（适用时）；
- NOTICE 与归属；
- 安全扫描和签名信息；
- 禁止/限制的应用与地域说明（适用时）。

## 项目根许可证

当前未替仓库所有者决定根许可证。决定前建议评估：

- Rust Core/SDK 是否采用 Apache-2.0 OR MIT 双许可；
- 官方 Runtime Builder、兼容数据库和企业策略是否分仓或采用不同许可；
- 外部贡献是否使用 DCO 或 CLA；
- 复制现有 GPL 项目代码是否会改变预期许可边界。

未确定不等于默认开源许可。公开接受贡献前必须完成这一决策并添加根 `LICENSE`。
