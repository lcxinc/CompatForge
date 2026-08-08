# Phase 0 首个纵向切片

版本 `0.2.0` 打通无副作用计划编译链：

```mermaid
flowchart TD
    A["Context JSON"] --> C["契约与 digest 校验"]
    B["LaunchRequest JSON"] --> C
    C --> D["Provider 硬约束与回退"]
    D --> E["固定 Runtime Pack"]
    E --> F["LaunchPlan JSON"]
    F --> G["C ABI / CLI"]
```

## 输入

- `CoreConfig`：Host 能力快照、可用 Provider、Provider 到 Runtime Pack 的固定绑定、存储根目录与默认沙箱档位；
- `LaunchRequest`：请求 ID、Bottle、Windows 可执行文件、参数、环境和 VM/Remote/网络等约束。

Provider 可用但没有 `packDigest` 绑定时，计划失败；不会退回到浮动的 `latest`。Runtime executable 和 storage root 必须是绝对宿主路径。命令始终使用 `executable + arguments[] + environment{}` 表达，不生成 shell 字符串。

## 输出与所有权

`cf_compile_launch` 返回符合 `launch-plan.schema.json` 的调用方持有字符串。调用方必须使用 `cf_string_free` 释放；Context 使用 `cf_context_release`。Rust panic 在 ABI 边界被截获并映射为稳定状态码，详细错误可由 `cf_last_error_json` 取得。

## 明确边界

该切片本身只编译计划：不下载 Runtime、不启动 Wine、不创建 Bottle、不修改注册表。后续 `0.3.0` 已在[受控进程纵向切片](phase-0-process-supervisor.md)加入再授权、启动、事件和退出闭环。Mac-Win Bridge 作为历史检查点保留，不再继续维护。
