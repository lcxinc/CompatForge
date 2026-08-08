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

Phase 0 最初只公开版本探针；首个纵向切片已经加入无副作用的 plan API：

```c
const char *cf_api_version(void);
uint32_t cf_abi_version(void);
typedef struct cf_context cf_context_t;
typedef uint32_t cf_status_t;

cf_status_t cf_probe_capabilities(char **out_capabilities_json);
cf_status_t cf_context_create(const char *config_json, cf_context_t **out);
cf_status_t cf_capabilities_get(
    const cf_context_t *context,
    char **out_report_json
);
cf_status_t cf_compile_launch(
    const cf_context_t *context,
    const char *request_json,
    char **out_plan_json
);
cf_status_t cf_last_error_json(char **out_error_json);
void cf_string_free(char *value);
void cf_context_release(cf_context_t *context);
```

Core `0.4.0` 已在相同 opaque-handle 规则下加入进程树启动、事件与分级终止 API：

```c
typedef struct cf_launch cf_launch_t;

cf_status_t cf_launch_start(
    cf_context_t *context,
    const char *plan_json,
    cf_launch_t **out
);
cf_status_t cf_launch_next_event(
    const cf_launch_t *launch,
    uint32_t timeout_ms,
    char **out_event_json
);
cf_status_t cf_launch_terminate(const cf_launch_t *launch);
void cf_launch_release(cf_launch_t *launch);
```

C ABI 约束：

- ABI major 不兼容时拒绝初始化；API schema 可独立演进。
- 所有跨边界对象由创建方释放，文档明确所有权。
- 不跨 FFI 抛出 panic/exception；映射为稳定 status + structured error。
- `cf_compile_launch` 只编译计划，没有下载、文件修改或进程副作用。
- `cf_probe_capabilities` 只读取 OS API/只读系统文件与 Rust 编译目标事实；不扫描 PATH、不执行发现的 Provider、不把未固定组件标记为 available。
- `cf_capabilities_get` 只克隆 Context 中已验证的 CapabilityReport，并在内存中确定性排序 Provider、capabilities 与 observations；它不读取文件、不访问网络、不执行 Provider、不修改 Bottle/Runtime Pack，也不进入 PE 解析路径。失败时输出保持 `NULL`，成功字符串由 `cf_string_free` 释放。
- `cf_launch_start` 会把输入计划与 Context 的 Runtime digest、入口、受保护环境、沙箱和存储根再次比对；前端不能借序列化计划执行任意宿主命令。
- `cf_launch_next_event` 返回 `runtime-event.schema.json`；timeout 与 event-stream end 使用独立稳定状态码。
- 回调默认不在 UI 主线程执行；客户端自行调度。
- Qt/C++、Swift/Kotlin 不持有 Rust 引用，只持有 opaque pointer。

进程层拥有 PID 与全部后代：Unix 使用独立 process group，Windows 使用 Job Object。Context 固定的 supervisor policy 会进入 LaunchPlan 并在启动前再次授权；UI 不能延长最大运行时间或替换 wineserver。受管 Wine prefix 在同一 Core 进程内具有排他租约，终止或根进程退出后执行前缀级 `wineserver -k/-w`，再清理残留进程树。

CapabilityReport 中的 `observations` 记录事实来源、检测状态和值/失败原因。Core 内建 probe 只声明 native translator；Wine、FEX/Box64/QEMU、DXVK/vkd3d/D3DMetal 等必须由固定 Runtime Pack、受信任系统适配器或远端认证提供证据，不能由文件名或 PATH 命中推断。

ForgeOS 的能力协商路径在取得有效 Context 后只解析 `cf_api_version`、`cf_abi_version`、`cf_capabilities_get`、`cf_last_error_json` 与 `cf_string_free`。Context 的创建与配置验证属于宿主集成初始化，不会在能力查询过程中隐式发生。ABI v1 客户端必须容忍后续 additive symbol，且不得依赖 Rust 对象布局。

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
