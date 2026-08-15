# Phase 2：Qt 薄壳与首批 GUI 兼容基线

本阶段把 macOS ARM64 的第一个可审计 GUI 纵向切片落到 Core、C ABI、Qt 和 opt-in 真实验收。它建立兼容基线，不宣称已经达到完整 Mac-Win 功能或 Tier 1。

## Runtime bootstrap

`cf_macos_local_context_create` 是唯一的 macOS 本地 Runtime 发现真源。它只检查固定候选：CrossOver 应用、Whisky 应用/本地库，以及仓库外 Mac-Win 开发构建；不读取 PATH、不启动 shell、不联网，也不递归扫描。候选必须通过：

1. 绝对路径、普通可执行文件和受限 Mach-O 架构检查；
2. 直接 argv `--version` 探测，要求 `wine-<version>`；
3. wineserver 同样的 bounded probe；
4. Rust `RuntimePackStore` 的 Preview Pack 内容寻址登记与幂等验证；
5. `MacOsProviderSet::probe_with` 的入口哈希、Pack、架构和 Rosetta 证据复验。

Bootstrap 请求只允许 `schemaVersion`、绝对 `runtimeStoreRoot`、绝对 `storageRoot`，以及必须完整出现的 `materializedRoot/wine/wineserver/version` 覆盖四元组。Receipt 只返回来源标签、版本、架构、Pack ID/digest 和能力；私有 Core 配置由 CLI 的可选 context-output 或 FFI opaque handle 持有。

## Launch binding

`immutableArtifact` 继续把 PE 写入内容寻址 Guest Artifact store；`bottleInPlace` 只允许 `<storageRoot>/bottles/<bottleId>/prefix/drive_c` 下的无符号链接普通文件，并把安装后的 EXE、架构、子系统、大小和 SHA-256 绑定进 `LaunchPlan.bottleExecutable`。DLL、插件和相邻资源仍由 Bottle 原位解析，摘要不覆盖它们，因此 Bottle 不等于安全沙箱。`ProcessSupervisor` 在授权、哈希复验后才物化 working directory/WINEPREFIX，并拒绝 symlink/path collision。

## Qt shell

`apps/desktop` 只负责状态呈现与受控动作：Runtime/Rosetta/WineD3D 卡片、EXE 选择、三个 GUI baseline 卡片、inspection/plan、RuntimeEvent 和错误详情。C++ RAII wrapper 将 `cf_context_t`、`cf_prepared_launch_t`、`cf_launch_t` 的释放和窗口关闭终止集中在 worker thread；QML 不直接调用阻塞 FFI。QML 文案全部 `qsTr`，稳定 `objectName`/accessibility 名称用于 Qt Test 和辅助功能。

本阶段不实现应用商店、完整 Bottle 设置、Recipe 编辑器、D3DMetal 配置、原生对话框桥、签名发布或 notarization。

## GUI evidence

`tools/download_gui_assets.py` 固定官方 URL、重定向主机、流式大小上限和 SHA-256，只有 `--allow-network` 才下载，缓存必须在仓库外。`tools/run_gui_baseline.py` 为 7-Zip、SumatraPDF、Notepad++ 各建独立 Bottle，先以 immutable installer 启动，再以 `bottleInPlace` 启动安装后的 EXE，并记录 inspection、LaunchPlan、RuntimeEvent、窗口/截图和清理。空白窗口或仅进程启动只能得到 `unverified`。

默认 CI 只执行 Rust/FFI、仓库合同、Qt build/offscreen smoke 与 Qt Test；真实下载、Wine 安装、窗口 Accessibility 和截图只在本机显式 opt-in。
