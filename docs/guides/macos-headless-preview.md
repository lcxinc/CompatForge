# Apple Silicon 本地无头真实 PE 预览

本流程只证明受限自动发现或开发者显式选择的 x86_64 Wine 可以在当前 Apple Silicon Mac 上，
经 Rosetta、PreparedLaunch 和 Process Supervisor 启动仓库提供的最小 Windows
Console probe。它不是 GUI、安装器、任意应用、Tier 1 或发行就绪证明。

## 前提

- macOS ARM64 与可用 Rosetta；
- 已构建的 `compatforge-cli` 绝对路径；
- 开发者合法取得、位于下述固定候选位置之一的本地 x86_64 Wine，或其完整显式路径；
- 显式 MinGW x86_64 C 编译器；
- 三个彼此隔离的本地目录：Runtime Store、Core Storage、空 Work Root。

CompatForge 不扫描 `PATH`、不递归搜索磁盘、不联网下载 Wine，也不接受 D3DMetal。
发现器按顺序检查 CrossOver.app、Whisky.app、Whisky 用户 Libraries，以及相邻
`Mac-Win/refs/Whisky-*-build` 开发构建的固定布局。只有 `wine` 与 `wineserver`
均位于候选根内、是可执行普通文件、是单架构 x86_64 Mach-O，并实际通过
`--version` 时才接受。不要把来源二进制、生成的 `.exe` 或证据目录加入 Git。

可先独立查看选择结果（JSON 中不包含环境变量）：

```text
python3 -S -B tools/discover_macos_wine.py
```

## 构建 CLI

```text
CARGO_TARGET_DIR=/absolute/external/cargo-target \
  cargo build -p compatforge-cli --locked
```

## 自动契约门禁

```text
python3 -S -B -m unittest tests.test_macos_headless_preview -v
```

该门禁使用受控 fixture 和 mocked 命令，不执行 Wine。

## 真实执行

```text
python3 -S -B tools/run_macos_headless_preview.py \
  --compatforge-cli /absolute/external/cargo-target/debug/compatforge-cli \
  --cc /opt/homebrew/bin/x86_64-w64-mingw32-gcc \
  --runtime-store /absolute/empty/runtime-store \
  --storage-root /absolute/empty/core-storage \
  --work-root /absolute/empty/work-root
```

如需覆盖自动选择，必须同时增加以下四项，部分覆盖会拒绝执行：

```text
  --wine-root /absolute/path/to/local-x86_64-wine \
  --wine relative/path/to/wine \
  --wineserver relative/path/to/wineserver \
  --version explicit-version
```

工具依次执行：发现并执行验证 Wine（或接受完整覆盖）、编译并检查 Console PE、
登记 preview Pack、安装/复验 Pack、Provider
probe/context、`prepared-plan`、`prepared-launch`。LaunchRequest 固定 inspection
SHA-256；Supervisor 在 spawn 前重新验证 Guest、Wine 和 wineserver。

成功时 Work Root 包含 inspection、Runtime receipts、capabilities、Context、
Prepared LaunchPlan、RuntimeEvent JSONL 和脱敏 `summary.json`。事件至少包含
`started → output → exited`，stdout 中恰有一行
`COMPATFORGE_WINDOWS_CONSOLE_OK`，退出码为 0。

probe 使用 `--no-insert-timestamp` 链接，避免 PE 时间戳造成伪 digest 漂移。
使用第二个空 Work Root 重复运行；两个 `summary.json` 应完全相同。负向验收只在
隔离副本上分别修改 Wine、wineserver 或 Guest 内容，确认在进程创建前拒绝。
绝不能修改开发者真实 Wine 安装。

## 清理

只清理本次命令中显式提供且已复核的 Work Root、Runtime Store 和 Core Storage。
不要使用主目录、仓库根、Wine 根、通配符或未展开的环境变量作为递归清理目标。

## 已知限制

- unsigned local preview；
- 仅 x86_64 Windows Console executable；
- 无 OS sandbox、Qt/QML、GUI、字体、IME、剪贴板或 GPU 认证；
- 不定义正式 Runtime 归档、下载、签名、更新、GC 或分发格式；
- 不修改 ForgeOS、ForgeTools 或 Mac-Win。
