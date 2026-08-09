# Phase 1：Trusted Launch Preparation

Core 0.10 将 Core 0.9 的只读 PE inspection 接入正式规划边界，但仍不在本切片执行真实 Windows PE。

## 数据流

```text
absolute source
  -> single bounded read
  -> PE inspection
  -> SHA-256 guest object
  -> trusted request rewrite
  -> LaunchPlan.guestArtifact
  -> opaque PreparedLaunch
  -> context + object re-authorization
```

Guest Artifact Store 位于配置的 `storageRoot/guest-artifacts`，不复用 Runtime Pack Store。对象路径完全由 digest 推导；已存在对象必须重新匹配大小和 SHA-256，冲突时拒绝覆盖。

`PreparedLaunch` 启动授权会：

- 比对当前 Context 指纹；
- 复验 Guest 对象的固定路径、普通文件类型、大小和 digest；
- 从私有可信请求重新编译 Runtime、Translator、Graphics、环境、sandbox、工作目录和生命周期；
- 要求重编计划与保存计划完全一致；
- 再执行既有 `PolicyEngine::authorize`。

## C ABI

```c
cf_status_t cf_launch_prepare(
    const cf_context_t *context,
    const char *absolute_executable_path,
    const char *request_json,
    cf_prepared_launch_t **out_prepared
);

cf_status_t cf_prepared_launch_inspection_get(...);
cf_status_t cf_prepared_launch_plan_get(...);
cf_status_t cf_prepared_launch_start(...);
void cf_prepared_launch_release(...);
```

所有输出指针在验证前清空；字符串继续由 `cf_string_free` 释放。Prepared handle 不暴露可变字段。

## 本切片排除项

- 真实 hello-console 执行；
- `compatforged` 与跨进程认证；
- Runtime Pack 签名密钥、撤销和 GC；
- Qt/QML、ForgeOS 或 Mac-Win 修改；
- GUI PE、DLL、驱动、EFI、ARM guest 和图形应用。
