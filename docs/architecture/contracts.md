# Provider、IPC 与 C ABI 契约

## Provider 生命周期

所有 Provider 遵循同一逻辑生命周期：

1. `probe(host) -> ProbeResult`：只读、可缓存、带版本和失败原因。
2. `evaluate(request, context) -> Suitability`：无副作用，返回硬阻塞与评分因素。
3. `prepare(plan) -> PreparedAssets`：允许下载/解包/快照，但必须可取消和回滚。
4. `compile(request, assets) -> NativeCommand`：输出 executable、argv、environment、mounts。
5. `launch(command) -> LaunchHandle`：交给 process supervisor，不自行脱离监督。
6. `terminate(handle)`：幂等，先优雅后强制，并记录进程组清理结果。

Runtime、Translator 和 Graphics Provider 分开建模。Translator 只包装 NativeCommand；Graphics Provider 只声明 DLL/库注入和能力，不负责选择 Runtime。

## 建议 Rust 接口

以下是 Phase 1 目标，不要求 Phase 0 立即引入 async runtime：

```rust
pub trait RuntimeProvider: Send + Sync {
    fn id(&self) -> &'static str;
    async fn probe(&self, host: &HostCapabilities) -> Result<RuntimeProbe>;
    fn evaluate(&self, request: &LaunchRequest, ctx: &PlanContext) -> Suitability;
    async fn prepare(&self, plan: &LaunchPlan) -> Result<PreparedRuntime>;
    fn compile(&self, request: &LaunchRequest, prepared: &PreparedRuntime)
        -> Result<NativeCommand>;
}

pub trait ArchitectureTranslator: Send + Sync {
    fn kind(&self) -> TranslatorKind;
    async fn probe(&self) -> Result<TranslatorProbe>;
    fn supports(&self, host: CpuArch, guest: CpuArch) -> bool;
    fn wrap(&self, command: NativeCommand) -> Result<NativeCommand>;
}

pub trait GraphicsBackend: Send + Sync {
    fn kind(&self) -> GraphicsKind;
    fn evaluate(&self, app: &GraphicsRequirements, host: &GpuCapabilities)
        -> Suitability;
    fn materialize(&self, bottle: &Bottle, runtime: &RuntimePack)
        -> Result<GraphicsInjection>;
}
```

## NativeCommand 规则

- `executable` 是规范化绝对路径或由已验证 Runtime Pack 解析的入口点。
- `arguments` 是字符串数组，禁止把整个命令序列化为 shell 字符串。
- `environment` 从四层合并：受控宿主白名单 → Runtime → Recipe → 用户覆盖；高风险 key 可由策略禁止覆盖。
- `mounts` 和 `devices` 必须显式列出，不能靠宿主默认全盘可见。
- secret 以受保护引用传递，不进入 LaunchPlan JSON、日志或进程列表。

## C ABI

Phase 0 只公开：

```c
const char *cf_api_version(void);
uint32_t cf_abi_version(void);
```

Phase 1 使用 opaque handle 和调用方可释放字符串：

```c
typedef struct cf_context cf_context_t;
typedef struct cf_launch cf_launch_t;

cf_status_t cf_context_create(const char *config_json, cf_context_t **out);
cf_status_t cf_compile_launch(
    cf_context_t *context,
    const char *request_json,
    char **out_plan_json
);
cf_status_t cf_launch_start(
    cf_context_t *context,
    const char *plan_json,
    cf_launch_t **out
);
cf_status_t cf_launch_next_event(
    cf_launch_t *launch,
    uint32_t timeout_ms,
    char **out_event_json
);
void cf_string_free(char *value);
void cf_launch_release(cf_launch_t *launch);
void cf_context_release(cf_context_t *context);
```

C ABI 约束：

- ABI major 不兼容时拒绝初始化；API schema 可独立演进。
- 所有跨边界对象由创建方释放，文档明确所有权。
- 不跨 FFI 抛出 panic/exception；映射为稳定 status + structured error。
- 回调默认不在 UI 主线程执行；客户端自行调度。
- Swift/Kotlin 不持有 Rust 引用，只持有 opaque pointer。

## Desktop IPC

桌面守护进程使用本机认证的 UDS/Named Pipe。初期可使用长度前缀 JSON-RPC；需要高吞吐事件时再评估 protobuf。协议至少包含：

- `hello`：ABI/API 版本、client identity、feature negotiation；
- `capabilities.get`；
- `launch.compile/start/cancel/events`；
- `bottle.list/create/snapshot/migrate/restore`；
- `catalog.list/verify/install`；
- `diagnostics.query/export`。

IPC 权限默认限制为当前用户。守护进程拒绝未签名客户端的企业部署模式由后续安全 ADR 决定。

## Schema 演进

- additive optional field：同一 major schemaVersion；
- 修改语义、类型或 required 集：提升 major；
- Reader 至少支持当前版本与上一个 major；
- Writer 只写当前版本，不静默降级；
- 未识别安全字段默认拒绝，不采用“忽略继续”；
- 签名对象必须先定义 canonical JSON 规则，不能签 pretty-printed 原始字节后再随意重排。
