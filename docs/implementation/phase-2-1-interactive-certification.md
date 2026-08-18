# Phase 2.1：交互式兼容认证与矩阵扩展

本阶段把 Phase 2 的“可启动、可观察、可清理”升级为可重复的应用兼容认证，但不把自动截图或长跑成功冒充人工功能验收。

## 里程碑范围

- 默认基线保持 7-Zip x64、SumatraPDF 和 Notepad++；
- 显式矩阵扩到 Firefox、Krita、7-Zip x86、VLC、WinMerge、Audacity x86 和 Everything x86，共十项；
- 每项固定官方 URL、SHA-256、架构、安装/启动参数、窗口标题与交互闭集；
- 每次运行输出原始应用证据和标准 Compatibility Result；
- 失败必须归入闭集，桌面基础设施阻塞与产品兼容失败分开统计。

## 人工证据边界

`tools/prepare_gui_interaction_evidence.py` 只生成工作表：检查初始值全部为 `false`，`observedAt` 为空。观察者必须在真实窗口中完成操作后填写时间并逐项改为 `true`。Runner 只接受 schemaVersion 2、`mode=human`、非空观察者、带时区时间、无未知字段且所选应用检查精确完整的文件。自动化或旧 v1 文件不能产生 `accepted`。验证后的观察者与观察时间会复制到每个应用的外部证据文件，避免汇总时丢失人工签署上下文；仓库和默认 CI 不保存该记录。

## 可观察性分类

macOS Runner 在窗口探测前读取登录会话状态：

- 锁屏、Accessibility、AppleScript 或 screencapture 不可用：`test-infrastructure`；
- 可观察桌面上目标标题缺失：`runtime-regression`；
- 安装器退出但固定可执行文件不存在：`installer-upstream`；
- 窗口、截图、退出与清理完整但缺少人类签署：`policy-blocked`。

所有分类都保留 `unverified`/`failed`，不得通过汇总工具提升为 passed。

## 发布门禁

十项应用的标准结果由 `tools/summarize_gui_compatibility.py` 汇总：任何 failed 使门禁 failed；没有 failed 但存在 blocked 时门禁 blocked；只有全部 passed 才是 passed。发布结论仍绑定准确的 Host、Runtime Pack、安装器、矩阵摘要和测试套件版本，不能外推到其他版本或设备。

## 后续边界

MSI、.NET/WPF、LibreOffice、D3D probes 和 Linux x86_64 桌面产品化仍需独立设计。当前 Trusted Launch 只接受 inspection-bound PE；不能为了增加应用数量绕过 PE 检查或把 MSI 当作可执行文件。
