# ADR-0007：Host Capability 事实与 Provider 可用性分离

- 状态：Accepted
- 日期：2026-08-08

## 背景

Planner 需要 OS、CPU、Translator、Graphics 与 Runtime 能力，但“PATH 中存在一个同名文件”既不能证明来源可信，也不能证明版本、依赖和运行能力满足要求。若基线探测直接扫描并执行系统二进制，启动决策会受环境注入、未固定升级和不可复现结果影响。

## 决策

1. `compatforge-capability` 负责单次、只读的主机快照；当前只读取 Rust 编译目标事实、OS API 和只读系统文件。
2. `CapabilityReport.observations` 为每个事实记录 `source`、`status`、`value` 或失败原因。缺失信息写为 `unknown`，不伪造默认版本。
3. 基线探测只声明 Core 确定拥有的 native translator，不扫描 PATH，也不执行发现的 Wine、FEX、Box64、QEMU、DXVK 或其他 Provider。
4. Runtime、Translator 和 Graphics Provider 的 `available` 必须由固定 Runtime Pack、受信任平台适配器或远端认证产生；Policy 仍独立判断 suitable。
5. CLI 与 C ABI 返回同一版本化 CapabilityReport，Qt/QML 只消费快照，不自行补写探测结论。

## 结果

- 相同主机事实可追溯到明确来源，未知状态不会被误当成不可用或可用；
- 环境 PATH 和未知二进制不能影响基线能力报告；
- 后续 GPU/driver、Rosetta/FEX 和 Wine probe 可在同一证据契约上增量加入；
- 当前 Context 仍可加载受信任的静态 Provider 快照，Desktop daemon 建立后应成为实时 snapshot 的权威所有者。
