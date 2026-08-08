# ADR-0010：有界、只读的 PE 检查边界

- 状态：Accepted
- 日期：2026-08-08

## 背景

ForgeOS 已完成 user/mount namespace、seccomp、Landlock 与 cgroup v2 的行为门禁，下一集成阶段需要在执行前识别一个可再分发 Windows fixture。PE 元数据属于 CompatForge；若 ForgeOS 自行解析，会产生第二套不一致且高权限的解析器。

## 决策

Core 0.9 新增独立 `compatforge-inspect` crate 和 ABI v1 additive symbol `cf_inspect_executable`。输入必须是绝对、非符号链接的普通文件，读取上限为 64 MiB。解析器使用 checked arithmetic，限制 optional header、section 和 import 数量，拒绝重叠 section、未映射 RVA、未终止 import table、非法名称以及 machine/magic 不一致。

Schema v1 只公开 SHA-256、文件大小、PE32/PE32+、架构、image/subsystem、入口 RVA、节权限摘要与规范化 import DLL 名。检查不创建 Context、不读取 Runtime Pack/Bottle、不调用 Provider、不生成 LaunchPlan、不写文件、不联网并且不映射或执行来宾代码。

`cf_abi_version()` 保持 1；语义 API 升级为 0.9.0。调用方必须先检查 API，再解析新增符号。未来 `compatforged` 可以复用同一 DTO，但 daemon 的认证和 framing 需要独立决策。

## 后果

恶意 PE 仍进入复杂二进制解析边界，因此 fuzzing 和 corpus 扩充是后续发布门禁。当前实现故意只读取 import library 名，不解析 symbol、资源、签名或调试目录，也不把“能解析”当作“允许启动”。

## 验证与回滚

- 单元测试覆盖头截断、machine/magic 冲突、RVA 越界、import 未终止和相对路径；
- 确定性 `hello-x86_64.exe` 由仓库脚本生成，不包含可执行代码；
- Linux C consumer 先验证 API 0.9.0/ABI 1，再动态解析并释放检查报告；
- 三平台 CLI 均只读检查同一 fixture；
- 回滚删除 additive symbol/crate/schema，ABI major 不需要迁移。
