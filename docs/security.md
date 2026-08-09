# 安全模型

CompatForge 运行来源和质量不一的 Windows 二进制，并组合多个 JIT/图形/系统组件。安全目标不是宣称 Wine Bottle 等同虚拟机，而是减少默认权限、保证供应链可追溯、让变更可回滚并避免敏感信息泄漏。

## 信任边界

| 边界 | 主要风险 | 控制 |
|---|---|---|
| Recipe catalog | 恶意参数、DLL、注册表修改、过期签名 | 签名索引、typed action、风险级别、有效期与回滚保护 |
| Runtime Pack | 被替换的 Wine/translator/graphics 二进制 | digest、签名、SBOM、内容寻址、不可变安装 |
| Installer | 上游劫持、版本漂移、静默更新 | HTTPS + SHA-256 + 来源 allowlist；签名验证能力后续加入 |
| Bottle | Windows 恶意软件访问用户文件/网络 | 最小目录映射、显式网络/设备策略、OS sandbox |
| Provider | 命令注入、越权挂载、泄露 secret | argv API、能力约束、Provider conformance tests |
| 日志/支持包 | 用户名、文件名、token、许可证密钥 | 结构化字段、默认脱敏、用户预览、最短保留 |
| AI Repair | 幻觉修复、未知下载、绕过安全 | 只生成候选；克隆 Bottle 验证；人工/规则审批 |

## 默认策略

- 未签名 Runtime Pack 不进入 stable/candidate channel。
- Runtime Pack 的 pack digest 只覆盖规范化 unsigned manifest；`digest` 自身与可轮换 signature envelope 不进入哈希。组件 artifact 必须在 active ref 切换前逐个通过 SHA-256。
- stable/candidate 没有签名时拒绝安装；存在签名但没有配置可信验证器时同样拒绝。preview/development 可使用未签名本地 bundle，但不会因此获得 stable 信任等级。
- Runtime Pack 安装只读取 bundle 内受限相对路径，拒绝绝对路径、反斜杠、盘符、`.`/`..` 与逃逸 symlink；当前不下载、不解包也不执行 artifact。
- 内容对象与 manifest 在 active ref 之前发布；失败不会暴露半安装 Pack。回滚重新校验目标 manifest 与所有对象，且不删除现有内容。
- 下载资产必须固定 digest；浮动 `latest` 只能用于开发 channel。
- Bottle 默认只能访问自身 prefix、临时目录和用户显式选择目录。
- 网络权限由 Recipe 与用户/管理员策略取交集，而不是 Recipe 单方面扩大。
- USB、串口、摄像头、麦克风和输入注入是高敏感设备能力，默认关闭。
- 高风险修复必须创建快照，显示动作，并要求确认。
- 远程 Provider 不接收本地完整文件树；上传按任务和目录逐项授权。
- PID 和进程树只归 process supervisor 所有；前端释放 handle 时内核仍完成分级终止，Unix process group 与 Windows Job Object 防止后代脱离清理。
- `wineserver` 必须由固定 Runtime Binding 提供绝对路径；Core 只用标准 argv 执行 `-k/-w`，并以 prefix 排他租约避免清理同前缀的并发会话。
- 基线 Host Capability probe 不扫描 PATH、不执行发现的二进制；Provider 的 available 结论必须绑定 Runtime Pack 或受信任平台适配器证据。
- Context capability 查询只公开类型化、白名单化的 CapabilityReport 投影，不序列化 Runtime Binding、存储根、环境变量或任意 Context observations。未知 feature/capability 被排除，Host/Provider 自由文本不原样复制，公开 observation 只由类型化 OS/架构重建；查询只做内存投影、校验和排序，不下载、不写入、不联网、不执行 Provider，也不解析来宾 PE。
- PE inspection 将来宾文件视为敌对输入：只读绝对且非符号链接的普通文件、64 MiB 上限、96 sections、256 import libraries、checked RVA/offset、重叠 section 拒绝和受限 ASCII 名称。解析成功不授予启动权限，也不调用 Provider、OS loader 或 shell。
- PreparedLaunch 对所选 PE 只读取一次，并把同一缓冲的 inspection 与 SHA-256 对象绑定；来源文件随后变化不会改变计划。第一版只接受 i386/x86_64 Windows Console executable，拒绝 DLL、GUI、Native、EFI、ARM、符号链接和父目录遍历。
- Guest Artifact Store 与 Runtime Pack Store 分离。对象路径只能由 digest 推导；计划和进程层都会在创建进程前复验普通文件类型、大小和 SHA-256。Context、Runtime、受保护环境、sandbox 或工作目录变化会使 opaque PreparedLaunch 授权失败。

## Bottle 不是安全边界

Wine prefix 提供配置隔离，不提供完整内核级隔离。桌面发行版需要结合宿主机制：

- macOS：App Sandbox/seatbelt 可行性、Hardened Runtime、签名/notarization；
- Linux：namespace、seccomp、Landlock/portal、Flatpak 权限；
- Android：应用 UID sandbox、SAF、前台服务和受控 native/JIT 路径。

对高风险或未知来源应用，应建议 VM/Remote，而不是提高 Wine Bottle 的营销承诺。

## Secret 与隐私

- LaunchPlan 只包含 secret reference，不包含 token/password 原文。
- 环境变量日志使用 allowlist；包含 `TOKEN`、`PASSWORD`、`SECRET`、`KEY` 等名称默认遮盖。
- Windows 用户名、宿主绝对路径和文档名在支持包中使用稳定匿名标识替换。
- Telemetry 默认关闭或最小化；启用前展示字段、目的、保留期和删除方式。
- 本地诊断与云端兼容数据库分开，上传必须 opt-in。

## AI Repair 限制

允许：日志分类、已知问题匹配、解释候选 Recipe diff、生成待审核 typed actions。

禁止：任意下载 DLL、禁用 sandbox/签名、修改系统目录、上传用户文件名或密钥、未经测试自动发布、在真实 Bottle 上试错。

验证链：结构化日志 → 确定性规则 → 候选 patch → 克隆 Bottle → smoke/regression → 审核与签名。

## 安全发布门禁

- 依赖与 Runtime SBOM；
- 第三方许可证与 NOTICE；
- 可复现或至少可审计构建记录；
- 签名密钥分离、轮换与撤销流程；
- Runtime/Recipe rollback protection；
- 威胁模型复审和关键 Provider fuzzing；
- 安全问题报告渠道在公开发布前建立。
