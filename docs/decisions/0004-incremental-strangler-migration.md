# ADR-0004：采用 Strangler 增量迁移

- 状态：Accepted
- 日期：2026-08-07

## 背景

Mac-Win 拥有超过 5 万行 Swift、数十个服务、大量测试/Recipe/patch/fixture。一次性重写会冻结产品、丢失隐含兼容知识，也无法逐步比较新旧行为。

## 决策

- 先在 Swift 引入 RuntimeClient、BottleClient、CatalogClient、DiagnosticsClient；
- Legacy Swift Adapter 与 CompatForge Adapter 同时实现接口；
- 每个 use case 使用 contract/golden tests 比较新旧后端；
- 以 feature flag/开发设置逐步把默认路径切到 Rust；
- 只有达到迁移退出门槛后才删除对应 legacy 逻辑；
- Bottle 采用双读、单写新版本、快照和原子迁移，不进行原地不可逆升级。

## 优先顺序

host probe → LaunchPlan → process supervisor → Wine/translator provider → Recipe → installer → Bottle 写入。UI 拆分与后端迁移并行，但 UI 重写不是前置条件。

## 结果

项目可持续交付和回滚，兼容差异可测量，已有 UI/测试资产继续工作。代价是迁移期存在双实现和额外 contract tests，必须防止 Legacy Adapter 成为永久依赖。

## 删除规则

没有实机矩阵、Bottle 恢复验证、结构化诊断和代表应用回归结果的模块，不得仅因“新代码已存在”而删除旧实现。
