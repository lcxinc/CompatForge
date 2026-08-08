# ADR-0005：使用 serde 实现版本化 JSON 契约

- 状态：Accepted
- 日期：2026-08-08

## 背景

Phase 0 骨架用纯 Rust 结构表达策略，但无法可靠读取 Schema 示例、向 Swift 返回 LaunchPlan，或实现通用 JSON Store。手写 JSON parser/serializer 会扩大安全边界，并容易在转义、未知字段和数值处理上产生不兼容。

## 决策

公共 DTO 使用 `serde` derive，JSON 边界使用 `serde_json`。安全相关对象启用 `deny_unknown_fields`，字段名由显式 rename 规则与 checked-in Schema/示例共同约束。Core 在反序列化后仍执行语义校验；成功解析不等于允许执行。

当前只批准 `serde` 与 `serde_json`。异步运行时、数据库、网络客户端和遥测库必须在出现明确用例后分别评审。

## 后果

- C ABI、CLI、测试与 JSON Store 共享同一 DTO，不再维护手写映射；
- 首次构建需要访问 Rust crate registry，发布构建必须提交并使用锁文件；
- Schema 与 Rust DTO 仍可能漂移，因此示例必须同时通过 Schema 检查和 Rust round-trip 测试；
- canonical JSON 和签名仍是独立议题，不能直接把 pretty JSON 当签名字节。
