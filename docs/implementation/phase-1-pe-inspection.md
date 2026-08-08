# Phase 1：PE inspection 纵向切片

Core 0.9 提供 Windows 执行前的第一个只读来宾输入边界。

## 数据流

1. CLI、C ABI 或未来 daemon 提交绝对普通文件路径；
2. inspector 在分配前检查 64 MiB 上限，并把同一组已读 bytes 用于 SHA-256 与解析；
3. DOS/PE/COFF/optional header 与 section table 通过 checked arithmetic 解析；
4. import directory 的 RVA 必须落在文件支持的 section raw data 内；
5. 输出 `executable-inspection.schema.json` Schema v1。

## 明确边界

本切片不执行文件，不用 OS loader 映射文件，不读取 symbol thunk，不验证 Authenticode，不提取 icon/resource，不选择 Provider，也不产生 LaunchPlan。ForgeOS 后续只能消费报告并继续自己的权限裁决；不能把检查成功解释为授权。

## 退出标准

- 同一 fixture 在 Linux、macOS 和 Windows 返回相同结构化结果；
- 畸形长度、RVA、section/import 数量和字符串均 fail closed；
- FFI 失败时先清空输出并通过 `cf_last_error_json` 返回稳定状态；
- C consumer 证明新增 ABI 符号和所有权释放；
- repository、fmt、check、test、Clippy 全绿。
