# ADR-0008：Runtime Pack 内容寻址存储与原子激活

- 状态：Accepted
- 日期：2026-08-08

## 背景

LaunchPlan 已固定 Runtime Pack digest，但此前没有可信的本地安装来源。直接把可变目录或版本名当 Runtime 会让 Provider 在计划后被替换，也无法可靠升级和回滚。

## 决策

- Runtime Pack bundle 的每个组件是 opaque artifact；Schema v1 使用可选 portable `artifact` 相对路径定位，缺省为 `components/<name>.blob`，Core 不在安装阶段解包或执行它。
- 组件 digest 是 artifact 原始字节的 SHA-256。对象发布到 `objects/sha256/<hex>`，同 digest 只存一份且不可变。
- SHA-256 使用 RustCrypto `sha2` 0.10 系列的纯 Rust 实现，并保留 NIST vectors 与流式边界测试；不调用 shell 或平台散列命令。
- Pack digest 是规范化 compact JSON 的 SHA-256：排除自引用的 `digest` 和可轮换的 `signature`，按组件名和 capability 排序，entrypoint 使用有序 map。
- stable/candidate 必须有签名；签名存在时必须由注入的可信 verifier 对同一份规范化 bytes 验证。默认 verifier 拒绝所有签名。
- 安装先验证并发布全部对象，再发布 manifest，最后用可恢复 JSON 原子替换 `refs/<pack-id>/current.json`。对象/manifest 孤立是安全状态，半安装 Pack 不可见。
- active ref 保存最多 32 个旧 digest。回滚先重新计算目标 manifest 与全部对象 digest，再原子切换 ref；对象不随回滚删除。
- 当前 CLI/Core 作为单 writer 串行化进程内写入。跨进程 writer、下载、归档物化、密钥撤销与垃圾回收另行实现。

## 结果

Planner 可以把一个已安装 Runtime 绑定到不可变内容；安装失败不会改变 active 选择，升级后可恢复到经过重新验证的旧版本。代价是旧对象会暂时保留，且在可信密钥和归档物化接入前，stable/candidate 不能通过默认 CLI 安装。

## 安全说明

bundle 路径拒绝绝对路径、反斜杠、盘符和 `.`/`..`，canonical path 必须仍位于 bundle root。安装不联网、不运行 shell、不执行 artifact，也不把 signature 字段的存在等同于签名有效。
