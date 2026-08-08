# 贡献指南

CompatForge 当前处于架构与契约收敛期。贡献应优先减少平台耦合、提高可验证性，并保持 Mac-Win 的增量迁移能力。

## 开发约束

- 核心领域和策略代码不得依赖 Swift、Qt、Android SDK 或具体 Wine 文件布局。
- Provider 只返回能力和结构化命令，不直接修改全局策略。
- 禁止通过 shell 字符串拼接启动进程；使用 executable + argv + environment。
- 新持久化格式必须有 `schemaVersion`、迁移函数、回滚方案和示例。
- Runtime/Recipe 下载必须固定 SHA-256；发行路径还必须验证签名。
- Bottle 不是安全沙箱。新增设备、目录或网络权限必须显式出现在 LaunchPlan。
- 不接受来源不明的 DLL、字体、Windows 镜像、密钥或二进制补丁。

## 提交前检查

```bash
python scripts/validate_repository.py
cargo fmt --all --check
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
```

涉及 Recipe、Runtime Pack、迁移器或 Provider 的变更还应附带：

- 至少一个结构化契约示例；
- 单元测试或代表应用 smoke test；
- 失败与回滚路径；
- 第三方来源、版本、许可证和 digest；
- 必要时新增或更新 ADR。

## 架构决策

改变稳定 ABI、Provider 选择顺序、持久化格式、信任根、平台 Tier 或迁移删除门槛前，先在 `docs/decisions/` 增加 ADR。ADR 一旦 Accepted，不直接重写历史；使用新 ADR 标记 Superseded。

## 许可证提醒

根项目许可证仍待所有者决定。未完成该决定和贡献条款前，不应接受无法明确授权的外部代码。第三方组件按 [合规门禁](docs/compliance.md) 处理。
