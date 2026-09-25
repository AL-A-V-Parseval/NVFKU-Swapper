"""User-facing text owned by the ReShade route: ReShade + dxgi.dll through Proton.

Keys are namespaced ``rh.`` so they cannot collide with another route's.
``EN`` and ``ZH`` must hold exactly the same keys: a missing entry falls back to
English and produces a half-translated plan, which the test suite checks for.

Identifiers stay verbatim across both languages — ``ReShade``, ``dxgi.dll``,
``ReShade.ini``, ``ReShade.log``, ``ReShadePreset.ini``, ``reshade-shaders``,
``nvngx_dlssnr.dll``, ``dlss5-bridge.addon64``, ``--headless``, ``--api dxgi``,
``Z:\\`` paths, digests and sizes. A user compares this text against Steam's
properties dialog and against ReShade.log, so translating an identifier would
break the correspondence.

Two entries are instructional prose rather than labels, and their Chinese reads
as a native sentence instead of a word-for-word rendering:

*   ``rh.check.api.vulkan_fix`` — why a Vulkan game cannot use this route.
*   ``rh.manual.check_log`` — what to look for in ``ReShade.log``.
"""

from __future__ import annotations

EN: dict[str, str] = {
    # Route title and summary
    "rh.title.nested": "ReShade {version}",
    "rh.title.full": "ReShade {version} (DXGI proxy, installed through Proton)",
    "rh.summary": (
        "Download the official ReShade setup tool, verify its digest, and run it "
        "headless inside this game's Proton prefix to place dxgi.dll and "
        "ReShade.ini beside the executable. No Vulkan layer is used, because "
        "Wine cannot load one."
    ),
    # Words reused by several entries
    "rh.unknown": "unknown",
    "rh.proton.placeholder": "<Proton>",
    # Separators between machine-readable items, which Chinese punctuates its own way
    "rh.sep.comma": ", ",
    "rh.sep.semicolon": "; ",
    # Check names
    "rh.check.launch_exe": "launch executable",
    "rh.check.proton": "Proton",
    "rh.check.prefix": "Proton prefix",
    "rh.check.reshade": "ReShade",
    "rh.check.api": "rendering API",
    "rh.check.install_dir": "install directory",
    # The launch executable
    "rh.check.launch_exe.block_detail": "no executable could be identified for this game",
    "rh.check.launch_exe.fix": "Install ReShade manually and point it at the game's .exe.",
    # Proton discovery
    "rh.check.proton.block_detail": "no Proton build could be found to run the installer",
    "rh.check.proton.fix": (
        "Install a Proton build, or run ReShade's setup inside the prefix by hand."
    ),
    "rh.proton.describe": "{name} ({source}) — prefix {state}",
    "rh.proton.state.create": "will be created",
    "rh.proton.state.exists": "already exists",
    # The Proton prefix
    "rh.check.prefix.warn_detail": (
        "{prefix} exists but has never been initialised (no config_info), so this "
        "will create it"
    ),
    "rh.check.prefix.warn_fix": (
        "Expected only for a game that has never been launched. Steam may recreate "
        "its own settings on first launch."
    ),
    "rh.check.prefix.ok_detail": "already used by Steam ({prefix})",
    # ReShade itself
    "rh.check.reshade.ok_detail": "already installed beside the executable",
    "rh.check.reshade.warn_detail": "not installed beside the executable",
    "rh.check.reshade.warn_fix": (
        "This downloads the official {version} setup tool, verifies its sha256, and "
        "runs it headless inside the game's prefix."
    ),
    # The rendering API: the Vulkan explanation is instructional prose
    "rh.check.api.vulkan_detail": "Vulkan game",
    "rh.check.api.vulkan_fix": (
        "Wine's Vulkan loader does not enumerate third-party layers, so a "
        "Vulkan-layer ReShade cannot load under Proton. There is no DXGI proxy path "
        "for a Vulkan-only title."
    ),
    "rh.check.api.ok_detail": "{api} — DXGI proxy applies",
    "rh.check.api.other_fix": (
        "Only the DXGI proxy is installed; a D3D9/OpenGL title would need its own "
        "proxy DLL."
    ),
    # The install directory
    "rh.check.install_dir.warn_detail": "{chosen} was selected over {other}",
    "rh.check.install_dir.warn_fix": (
        "The game contains more than one copy of the executable; the one that ships "
        "with the game was chosen."
    ),
    # Actions. The invocation itself is an identifier and is embedded unchanged.
    "rh.action.proxy_reason": "ReShade proxy, extracted by its own installer",
    "rh.action.ini_reason": "ReShade's own configuration for this proxy",
    "rh.action.run_installer": (
        "run ReShade_Setup_{version}.exe --headless --api dxgi {target} through "
        "{runtime}"
    ),
    "rh.action.run_installer_reason": (
        "the installer is a Windows program and is driven through Proton"
    ),
    "rh.action.create_prefix": "create the Proton prefix at {prefix}",
    "rh.action.create_prefix_reason": (
        "this game has never been launched, so it has no usable prefix"
    ),
    # Manual steps
    "rh.manual.overlay": (
        "Press the ReShade overlay key once in game and confirm the effect list is "
        "populated; the required packages are installed, a fuller set is not."
    ),
    "rh.manual.check_log": (
        "Check ReShade.log for an 'nr-fwd: model nvngx_dlssnr.dll' line. Its absence "
        "means the bridge add-on did not load, which is the difference between a "
        "working chain and a ReShade that injects and does nothing."
    ),
    # Reasons attached to the install-directory ranking, shown in the install log
    "rh.reason.ranking": "chosen by the engine's own executable ranking",
    "rh.reason.shared_engine": "sits beside a shared Engine tree",
    # Progress lines. The indent is applied by the caller, so these hold no spaces.
    "rh.log.recorded_tool_missing": "recorded tool {tool} is not installed; falling back",
    "rh.log.copies_found": "{count} copies of {name} found:",
    "rh.log.cached_installer": "using cached installer ({size})",
    "rh.log.cached_rejected": "cached installer rejected: {error}",
    "rh.log.downloading": "downloading {url}",
    "rh.log.verified_sha": "verified sha256 {digest}...",
    "rh.log.manifest_unreadable": (
        "could not read the effect manifest ({error}); using the standard package"
    ),
    "rh.log.fetching_effects": "fetching effects from {host}",
    "rh.log.effects_fetch_failed": "could not fetch {url}: {error}",
    "rh.log.not_zip": "{url} was not a zip archive: {error}",
    "rh.log.prefix_ready": "prefix already initialised ({prefix})",
    "rh.log.prefix_creating": "creating prefix with {tool} — this takes a minute",
    "rh.log.prefix_created": "prefix created ({prefix})",
    # install(), top-level progress
    "rh.install.header": "ReShade {version} for {game}",
    "rh.install.target": "target: {target}",
    "rh.install.effects_failed": "effects could not be installed: {error}",
    # InstallResult.verified
    "rh.verified.written": "{name} written ({size})",
    # InstallResult.notes
    "rh.note.installed_by": "installed by ReShade_Setup_{version}.exe --headless --api dxgi",
    "rh.note.prefix": "prefix: {prefix}",
    "rh.note.created": "created: {names}",
    "rh.note.replaced": "replaced: {names}",
    "rh.note.prefix_created": "the prefix was created by this run",
    "rh.note.effects": "effects: {count} file(s) in {directory}",
    "rh.note.effects_none": "effects: none installed — ReShade will report an empty effect list",
    "rh.note.manifest": "manifest: {manifest}",
    # install() refusals
    "rh.refuse.blocked": "ReShade cannot be installed here — {blockers}",
    "rh.refuse.no_yes": "refusing to write without --yes",
    "rh.refuse.no_proton": "no Proton build available",
    "rh.refuse.no_directory": "could not decide which directory the game runs from",
    # Errors raised while installing
    "rh.error.installer_size": (
        "installer is {actual}, expected {expected} — the download was probably an "
        "error page or a changed release"
    ),
    "rh.error.installer_digest": (
        "installer digest is {actual}..., expected {expected}... — refusing to run a "
        "binary that is not the reviewed build"
    ),
    "rh.error.not_executable": "installer does not look like a Windows executable",
    "rh.error.download_empty": "{url} returned nothing",
    "rh.error.prefix_create_failed": "could not create the Proton prefix: {detail}",
    "rh.error.prefix_exit": "exit {code}",
    "rh.error.no_dll": (
        "the installer ran but did not produce {dll} — nothing was installed"
    ),
    "rh.error.limited_addon": (
        "the installed {dll} is a build with limited add-on functionality, so it "
        "would skip dlss5-bridge.addon64. This tool fetches {asset}; a standard "
        "ReShade_Setup*.exe must not be used."
    ),
}

ZH: dict[str, str] = {
    # 路线标题与摘要
    "rh.title.nested": "ReShade {version}",
    "rh.title.full": "ReShade {version}（DXGI 代理，通过 Proton 安装）",
    "rh.summary": (
        "下载官方 ReShade 安装工具，校验其摘要，并在该游戏的 Proton 前缀内以 "
        "headless 方式运行，把 dxgi.dll 与 ReShade.ini 放到可执行文件旁。"
        "不使用 Vulkan layer，因为 Wine 无法加载它。"
    ),
    # 多处复用的词
    "rh.unknown": "未知",
    "rh.proton.placeholder": "<Proton>",
    # 机器可读条目之间的分隔符，中文用全角标点
    "rh.sep.comma": "、",
    "rh.sep.semicolon": "；",
    # 检查项名称
    "rh.check.launch_exe": "启动可执行文件",
    "rh.check.proton": "Proton",
    "rh.check.prefix": "Proton 前缀",
    "rh.check.reshade": "ReShade",
    "rh.check.api": "渲染 API",
    "rh.check.install_dir": "安装目录",
    # 启动可执行文件
    "rh.check.launch_exe.block_detail": "无法为该游戏确定可执行文件",
    "rh.check.launch_exe.fix": "请手动安装 ReShade，并让它指向该游戏的 .exe。",
    # Proton 查找
    "rh.check.proton.block_detail": "找不到可用于运行安装器的 Proton 构建",
    "rh.check.proton.fix": "请安装一个 Proton 构建，或手动在该前缀内运行 ReShade 的安装程序。",
    "rh.proton.describe": "{name}（{source}）— 前缀{state}",
    "rh.proton.state.create": "将被创建",
    "rh.proton.state.exists": "已存在",
    # Proton 前缀
    "rh.check.prefix.warn_detail": (
        "{prefix} 已存在但从未初始化（没有 config_info），因此本次会创建它"
    ),
    "rh.check.prefix.warn_fix": (
        "只有从未启动过的游戏才会如此。Steam 可能在首次启动时重建它自己的设置。"
    ),
    "rh.check.prefix.ok_detail": "Steam 已经使用过（{prefix}）",
    # ReShade 本身
    "rh.check.reshade.ok_detail": "已安装在可执行文件旁",
    "rh.check.reshade.warn_detail": "未安装在可执行文件旁",
    "rh.check.reshade.warn_fix": (
        "这会下载官方 {version} 安装工具，校验其 sha256，并在游戏前缀内以 "
        "headless 方式运行它。"
    ),
    # 渲染 API：Vulkan 的说明是给用户看的操作指引
    "rh.check.api.vulkan_detail": "Vulkan 游戏",
    "rh.check.api.vulkan_fix": (
        "Wine 的 Vulkan 加载器不会枚举第三方 layer，因此以 Vulkan layer 方式安装的 "
        "ReShade 无法在 Proton 下加载。对于只支持 Vulkan 的游戏，也没有 DXGI 代理"
        "这条路可走。"
    ),
    "rh.check.api.ok_detail": "{api} — 适用 DXGI 代理",
    "rh.check.api.other_fix": "本工具只安装 DXGI 代理；D3D9/OpenGL 游戏需要自己的代理 DLL。",
    # 安装目录
    "rh.check.install_dir.warn_detail": "已选择 {chosen}，而不是 {other}",
    "rh.check.install_dir.warn_fix": (
        "该游戏包含不止一份可执行文件；这里选择的是随游戏发行的那一份。"
    ),
    # 操作。调用命令本身是标识符，原样嵌入。
    "rh.action.proxy_reason": "ReShade 代理，由其自带安装器解出",
    "rh.action.ini_reason": "ReShade 为该代理生成的自身配置",
    "rh.action.run_installer": (
        "通过 {runtime} 运行 ReShade_Setup_{version}.exe --headless --api dxgi {target}"
    ),
    "rh.action.run_installer_reason": "安装器是 Windows 程序，需要通过 Proton 驱动",
    "rh.action.create_prefix": "在 {prefix} 创建 Proton 前缀",
    "rh.action.create_prefix_reason": "该游戏从未启动过，因此没有可用的前缀",
    # 手动步骤
    "rh.manual.overlay": (
        "在游戏中按一次 ReShade 覆盖层快捷键，确认效果列表已有内容；这里只安装了"
        "必需的包，没有安装更完整的集合。"
    ),
    "rh.manual.check_log": (
        "请在 ReShade.log 中确认存在 'nr-fwd: model nvngx_dlssnr.dll' 这一行。"
        "如果没有这一行，说明 bridge add-on 没有加载；这正是整条链路正常工作与 "
        "ReShade 注入后毫无作用之间的区别。"
    ),
    # 安装目录排序的理由，出现在安装日志中
    "rh.reason.ranking": "由引擎自身的可执行文件排序选中",
    "rh.reason.shared_engine": "位于共享的 Engine 目录树旁",
    # 进度行。缩进由调用方添加，这些条目本身不含空格。
    "rh.log.recorded_tool_missing": "记录的工具 {tool} 未安装；改用其他构建",
    "rh.log.copies_found": "找到 {count} 份 {name}：",
    "rh.log.cached_installer": "使用缓存的安装器（{size}）",
    "rh.log.cached_rejected": "缓存的安装器被拒绝：{error}",
    "rh.log.downloading": "正在下载 {url}",
    "rh.log.verified_sha": "已校验 sha256 {digest}...",
    "rh.log.manifest_unreadable": "无法读取效果清单（{error}）；改用标准包",
    "rh.log.fetching_effects": "正在从 {host} 获取效果文件",
    "rh.log.effects_fetch_failed": "无法获取 {url}：{error}",
    "rh.log.not_zip": "{url} 不是 zip 压缩包：{error}",
    "rh.log.prefix_ready": "前缀已初始化（{prefix}）",
    "rh.log.prefix_creating": "正在用 {tool} 创建前缀 — 这需要一分钟",
    "rh.log.prefix_created": "前缀已创建（{prefix}）",
    # install() 的顶层进度
    "rh.install.header": "为 {game} 安装 ReShade {version}",
    "rh.install.target": "目标：{target}",
    "rh.install.effects_failed": "效果文件无法安装：{error}",
    # InstallResult.verified
    "rh.verified.written": "{name} 已写入（{size}）",
    # InstallResult.notes
    "rh.note.installed_by": "由 ReShade_Setup_{version}.exe --headless --api dxgi 安装",
    "rh.note.prefix": "前缀：{prefix}",
    "rh.note.created": "新建：{names}",
    "rh.note.replaced": "替换：{names}",
    "rh.note.prefix_created": "前缀由本次运行创建",
    "rh.note.effects": "效果文件：{directory} 内 {count} 个",
    "rh.note.effects_none": "效果文件：未安装任何文件 — ReShade 会报告效果列表为空",
    "rh.note.manifest": "清单：{manifest}",
    # install() 的拒绝信息
    "rh.refuse.blocked": "ReShade 无法安装在这里 — {blockers}",
    "rh.refuse.no_yes": "没有 --yes 就拒绝写入",
    "rh.refuse.no_proton": "没有可用的 Proton 构建",
    "rh.refuse.no_directory": "无法确定游戏从哪个目录运行",
    # 安装过程中抛出的错误
    "rh.error.installer_size": (
        "安装器为 {actual}，预期为 {expected} — 下载到的很可能是错误页面，"
        "或版本已经变更"
    ),
    "rh.error.installer_digest": (
        "安装器摘要为 {actual}...，预期为 {expected}... — 拒绝运行不是已审核构建的"
        "二进制文件"
    ),
    "rh.error.not_executable": "安装器看起来不是 Windows 可执行文件",
    "rh.error.download_empty": "{url} 没有返回任何内容",
    "rh.error.prefix_create_failed": "无法创建 Proton 前缀：{detail}",
    "rh.error.prefix_exit": "退出码 {code}",
    "rh.error.no_dll": "安装器运行了，但没有生成 {dll} — 什么都没有安装",
    "rh.error.limited_addon": (
        "已安装的 {dll} 是仅提供有限 add-on 功能的构建，因此会跳过 "
        "dlss5-bridge.addon64。本工具获取的是 {asset}；不能使用标准的 "
        "ReShade_Setup*.exe。"
    ),
}
