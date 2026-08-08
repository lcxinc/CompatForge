# ADR-0003：签名 Runtime Pack 与 Recipe 分离

- 状态：Accepted
- 日期：2026-08-07

## 背景

Mac-Win 的 EngineRegistry 使用本地绝对路径，Compatibility Profile 编译进 Swift。二者都无法安全独立升级，也无法把一次兼容测试绑定到精确组件组合。

## 决策

- Runtime Pack 描述可执行组件：Wine、translator、graphics、helper、entrypoint、来源、许可证、digest、SBOM 与签名。
- Recipe 描述应用知识：installer digest、Bottle 默认值、平台条件、启动器、typed fixes、测试和 provenance。
- Bottle 固定 `{runtimePackId, digest}` 与已应用 Recipe digest，不跟随浮动 channel 自动变化。
- 远程 catalog 和 Runtime index 必须签名；下载对象必须验证 digest。
- Runtime 更新与 Recipe 更新分开发布、灰度、撤销和回滚。

## 结果

兼容结论可复现，Runtime 可回滚，应用规则可快速更新，许可证/SBOM 边界清晰。代价是需要内容寻址存储、签名密钥生命周期、canonical serialization 与旧版本保留策略。

## 安全说明

Recipe 签名不意味着任意 action 安全。Core 只实现有限 typed action，并按风险、策略和快照要求执行；未识别 action 默认拒绝。
