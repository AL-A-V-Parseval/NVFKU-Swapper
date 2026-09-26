"""User-facing text owned by route A1: A1 — ReShade + dlss5-bridge + addon-dlssnr-linux (Proton)

Keys are namespaced ``a1.`` so they cannot collide with another route's.
``EN`` and ``ZH`` must hold exactly the same keys: a missing entry falls back to
English and produces a half-translated plan, which the test suite checks for.

Identifiers stay verbatim across both languages — route names, digests,
environment variables, ``%command%``, file names, and API names. A user compares
this text against Steam's properties dialog and against ReShade.log.
"""

from __future__ import annotations

EN: dict[str, str] = {
    # Route title and summary
    "a1.title": "ReShade overlay",
    "a1.summary": (
        "The full route: ReShade's overlay with live controls, and a debug view to "
        "see what the model changed. Needs its ReShade prerequisite installed first."
    ),
    "a1.detail": (
        "Installs ReShade as a local dxgi.dll, adds dlss5-bridge and NapXDD's "
        "feature-18 add-on beside the executable, and points the game at the DLSS "
        "NR model it already has. The overlay carries NR intensity, Style and "
        "colour strength, and F10 A/Bs the pass against the game's own output."
    ),
    # Words reused by several entries
    "a1.unknown": "unknown",
    "a1.proton.unknown": "unknown Proton",
    # Separators between machine-readable items, which Chinese punctuates its own way
    "a1.sep.comma": ", ",
    "a1.sep.semicolon": "; ",
    # Check names
    "a1.check.api": "rendering API",
    "a1.check.bitness": "bitness",
    "a1.check.prefix": "proton prefix",
    "a1.check.ngx": "prefix NGX",
    "a1.check.reshade": "ReShade",
    "a1.check.native_dlss": "native DLSS",
    "a1.check.nr_model": "DLSS NR model",
    "a1.check.nr_model_alternatives": "DLSS NR model (alternatives)",
    "a1.check.nr_model_multiple": "DLSS NR model (multiple)",
    "a1.check.anticheat": "anti-cheat",
    # rendering API
    "a1.check.api.ok_detail": "{api} - ReShade loads as a local {dll}",
    "a1.check.api.vulkan_detail": "Vulkan game",
    "a1.check.api.unknown_detail": "could not be determined ({evidence})",
    "a1.check.api.no_evidence": "no evidence",
    "a1.check.api.fix": (
        "verify by launching the game with ReShade and reading which device "
        "ReShade reports in ReShade.log"
    ),
    # bitness
    "a1.check.bitness.ok_detail": "{bits}-bit - the add-on and forwarder are 64-bit",
    "a1.check.bitness.block_detail": "32-bit game",
    "a1.check.bitness.block_fix": "the addon-dlssnr-linux add-on is 64-bit only",
    "a1.check.bitness.fix": "check the executable with `file`",
    # Proton prefix
    "a1.check.prefix.ok_detail": "{prefix} (tool: {tool})",
    "a1.check.ngx.ok_detail": "nvngx.dll present in the prefix ({size})",
    "a1.check.ngx.warn_detail": "no nvngx.dll in the prefix",
    "a1.check.ngx.fix": (
        'run the game once with PROTON_FORCE_NVAPI=1 WINEDLLOVERRIDES="dxgi=n,b" '
        "so DXVK-NVAPI populates it, then re-plan"
    ),
    "a1.check.prefix.warn_detail": "no Proton prefix found for this appid",
    "a1.check.prefix.fix": (
        "launch the game once under Proton so Steam creates compatdata/<appid>/pfx"
    ),
    # ReShade
    "a1.check.reshade.ok_detail": "already installed beside {exe}",
    "a1.check.reshade.warn_detail": "not installed beside the executable",
    "a1.check.reshade.fix": (
        "ReShade's own installer must be run inside this game's Proton prefix; "
        "this tool plans it but does not bundle a ReShade build"
    ),
    # Actions
    "a1.action.reshade_install": (
        "run ReShade's installer (dxgi variant, add-on support enabled) inside "
        "the game's Proton prefix"
    ),
    "a1.action.reshade_not_redistributed": (
        "ReShade is downloaded from its publisher and run by the tool; it is never "
        "redistributed here"
    ),
    "a1.action.state_present": "present",
    "a1.action.state_to_install": "to install",
    "a1.action.reason_bridge": (
        "mirrors the game's DLSS contract onto a private D3D12 session"
    ),
    "a1.action.reason_addon": (
        "drives NGX feature 18 directly (bypasses driver dispatch)"
    ),
    "a1.action.reason_forwarder": (
        "forwarder whose name satisfies the snippet's caller gate"
    ),
    "a1.action.write_cfg_reason": (
        "unwrap=0 and vk_mirror/synth per the Linux reports; written on first install"
    ),
    "a1.action.leave_synth": "leave synth=0",
    "a1.action.native_dlss_reason": (
        "the game provides its own DLSS, so the bridge mirrors it instead of "
        "substituting"
    ),
    # Native DLSS / substitute decision
    "a1.check.native_dlss.ok_detail": (
        "{count} DLSS runtime(s) in the game folder - native mirror path"
    ),
    "a1.check.native_dlss.warn_detail": "game ships no DLSS",
    "a1.check.native_dlss.fix": (
        "the substitute path needs nvngx_dlss.dll >= 3.1.13 copied in by hand and "
        "synth=1; the driver does not supply that file inside a game folder"
    ),
    "a1.missing.substitute.what": "nvngx_dlss.dll (version 3.1.13 or newer)",
    "a1.missing.substitute.why": (
        "the substitute contract builds a synthetic DLAA session from it"
    ),
    "a1.missing.substitute.how": (
        "copy it from any game that ships DLSS (one is listed in `nvfku scan`)"
    ),
    # The DLSS NR model
    "a1.check.nr_model.ok_detail": "tested build found: {path}",
    "a1.action.model_reason_tested": "the model NapXDD measured as stable on Linux",
    "a1.check.nr_model.warn_detail": (
        "no tested build on this machine. {count} distinct same-size build(s) "
        "found, using {path} (sha256 {sha}...)"
    ),
    "a1.check.nr_model.fix": (
        "NapXDD's measured-stable build is {sha}...; a mismatched model can report "
        "Success on every evaluate and then crash the game minutes into play. Watch "
        "ReShade.log for the 'nr-fwd: model nvngx_dlssnr.dll ...' line after launching"
    ),
    "a1.check.nr_model.alt_detail": "{sha}... at {path}",
    "a1.check.nr_model.alt_fix": "try another build if the first one crashes",
    "a1.action.model_reason_untested": (
        "same size as the tested build, digest differs - verify from ReShade.log"
    ),
    "a1.check.nr_model.block_detail": "{name} not found on this machine",
    "a1.check.nr_model.block_fix": (
        "it is NVIDIA's and is not on this machine. Run 'nvfku model --fetch' to get "
        "the tested build (digest-checked), or put a copy where the game can see it"
    ),
    "a1.missing.model.what": "{name} ({size}, sha256 {sha}...)",
    "a1.missing.model.why": (
        "DLSS 5 neural rendering is this DLL; nothing else can substitute for it"
    ),
    "a1.missing.model.how": (
        "it ships inside Magpie's full package and beside DLSS-5-enabled games; on "
        "this machine DLSS5-Swapper/Magpie put it under the Windows DOCUMENTS volume"
    ),
    "a1.check.nr_model.multiple_detail": "{count} distinct builds found",
    "a1.check.nr_model.multiple_fix": (
        "the tested build is used first; the others are listed by `nvfku show`"
    ),
    # Anti-cheat
    "a1.check.anticheat.detail": "detected: {list}",
    "a1.check.anticheat.fix": (
        "ReShade add-ons and anti-cheat do not coexist; a ban would be on your account"
    ),
    # Why A1 is the DXGI proxy path and not a Vulkan layer
    "a1.vulkan_note": (
        "ReShade's Vulkan installation method is a Vulkan layer, and Wine's "
        "winevulkan never enumerates third-party layers, so this route only "
        "supports D3D11/D3D12 games."
    ),
    # Manual steps
    "a1.manual.install_reshade": (
        "Install the ReShade prerequisite first — it is listed under this route as "
        "Needs, and has its own button. Nothing else here loads without it."
    ),
    "a1.manual.launch": "Launch the game with DLSS Super Resolution enabled.",
    "a1.manual.overlay": (
        "Open the ReShade overlay (Home) -> Add-ons -> check that 'DLSS 5 Bridge' "
        "and 'DLSSNR Linux' are both listed."
    ),
    "a1.manual.f10": "Press F10 to A/B the neural pass.",
    "a1.manual.check_log": (
        "Confirm in ReShade.log: 'nr-fwd: model nvngx_dlssnr.dll ...' and no "
        "FAIL_OutOfDate."
    ),
    # Launch options note (the options string itself is an identifier)
    "a1.launch.note.custom": (
        "{tool}: custom Proton build, so PROTON_FORCE_NVAPI is the variable that exists"
    ),
    "a1.launch.note.valve": (
        "{tool}: Valve Proton, so PROTON_ENABLE_NVAPI is the variable that exists"
    ),
    # is_viable reasons, shown by `nvfku show` and by a scan
    "a1.reason.api_unknown": "rendering API could not be determined",
    "a1.reason.32bit": "32-bit game: the add-on is 64-bit only",
    "a1.reason.ok": "D3D11/D3D12, 64-bit, ReShade-as-dxgi is loadable",
    "a1.check.launch_options": "Steam launch options",
    "a1.check.launch_options.ok": "Steam is not running, so the launch options can be written",
    "a1.check.launch_options.blocked": (
        "a Steam client is running (pid {pids}). Steam keeps this value in memory "
        "and writes its copy back, so a write now would be silently reverted."
    ),
    "a1.check.launch_options.fix_running": (
        "Exit Steam completely — including the tray icon — then retry. The install "
        "is held until it is closed, because the proxy is not loaded without these "
        "options."
    ),
    "a1.check.launch_options.fix_error": (
        "The launch options cannot be read, so they cannot be written either. The "
        "rest of the install can still proceed."
    ),
    "a1.action.launch_option_reason": (
        "loads the local dxgi.dll and enables NGX inside the prefix"
    ),
    "a1.action.model_fetch_reason": (
        "the tested build {sha} is not on this machine; this is the pinned copy of "
        "NVIDIA's signed runtime, digest-checked on arrival"
    ),
}

ZH: dict[str, str] = {
    # 路线标题与摘要
    "a1.title": "ReShade 叠层",
    "a1.summary": "功能最全的一条：ReShade 叠层带实时调节，还有调试视图可以看模型改了什么。需要先装它的前置 ReShade。",
    "a1.detail": (
        "把 ReShade 作为本地 dxgi.dll 安装，在可执行文件旁加入 dlss5-bridge 与 NapXDD 的 "
        "feature 18 add-on，并让游戏指向它已有的 DLSS NR 模型。叠层里有 NR 强度、Style 与色彩强度，"
        "F10 可以把神经渲染与游戏原生输出做 A/B 对比。"
    ),
    # 多处复用的词
    "a1.unknown": "未知",
    "a1.proton.unknown": "未知 Proton",
    # 机器可读条目之间的分隔符，中文用全角标点
    "a1.sep.comma": "、",
    "a1.sep.semicolon": "；",
    # 检查项名称
    "a1.check.api": "渲染 API",
    "a1.check.bitness": "位数",
    "a1.check.prefix": "Proton 前缀",
    "a1.check.ngx": "前缀 NGX",
    "a1.check.reshade": "ReShade 安装",
    "a1.check.native_dlss": "自带 DLSS",
    "a1.check.nr_model": "DLSS NR 模型",
    "a1.check.nr_model_alternatives": "DLSS NR 模型（其他候选）",
    "a1.check.nr_model_multiple": "DLSS NR 模型（多个）",
    "a1.check.anticheat": "反作弊",
    # 渲染 API
    "a1.check.api.ok_detail": "{api} - ReShade 以本地 {dll} 加载",
    "a1.check.api.vulkan_detail": "Vulkan 游戏",
    "a1.check.api.unknown_detail": "无法确定（{evidence}）",
    "a1.check.api.no_evidence": "无证据",
    "a1.check.api.fix": "用 ReShade 启动游戏，查看 ReShade.log 中 ReShade 报告的是哪个设备",
    # 位数
    "a1.check.bitness.ok_detail": "{bits} 位 - add-on 与 forwarder 都是 64 位",
    "a1.check.bitness.block_detail": "32 位游戏",
    "a1.check.bitness.block_fix": "addon-dlssnr-linux add-on 只提供 64 位版本",
    "a1.check.bitness.fix": "用 `file` 检查该可执行文件",
    # Proton 前缀
    "a1.check.prefix.ok_detail": "{prefix}（工具：{tool}）",
    "a1.check.ngx.ok_detail": "前缀内存在 nvngx.dll（{size}）",
    "a1.check.ngx.warn_detail": "前缀内没有 nvngx.dll",
    "a1.check.ngx.fix": (
        '用 PROTON_FORCE_NVAPI=1 WINEDLLOVERRIDES="dxgi=n,b" 启动一次游戏，'
        "让 DXVK-NVAPI 写入该文件，然后重新规划"
    ),
    "a1.check.prefix.warn_detail": "未找到该 appid 的 Proton 前缀",
    "a1.check.prefix.fix": (
        "在 Proton 下启动一次游戏，让 Steam 创建 compatdata/<appid>/pfx"
    ),
    # ReShade
    "a1.check.reshade.ok_detail": "已安装在 {exe} 旁",
    "a1.check.reshade.warn_detail": "未安装在可执行文件旁",
    "a1.check.reshade.fix": (
        "ReShade 自带的安装器必须在游戏的 Proton 前缀内运行；本工具只做规划，"
        "不捆绑 ReShade 构建"
    ),
    # 操作
    "a1.action.reshade_install": (
        "在游戏的 Proton 前缀内运行 ReShade 安装器（dxgi 版本，启用 add-on 支持）"
    ),
    "a1.action.reshade_not_redistributed": (
        "ReShade 从发布方下载并由本工具代跑，这里不再分发它"
    ),
    "a1.action.state_present": "已存在",
    "a1.action.state_to_install": "待安装",
    "a1.action.reason_bridge": "把游戏的 DLSS 约定镜像到一个私有 D3D12 会话上",
    "a1.action.reason_addon": "直接驱动 NGX feature 18（绕过驱动分发）",
    "a1.action.reason_forwarder": "该 forwarder 的名字满足 snippet 的调用方校验",
    "a1.action.write_cfg_reason": (
        "按 Linux 相关报告设置 unwrap=0 与 vk_mirror/synth；首次安装时写入"
    ),
    "a1.action.leave_synth": "保持 synth=0",
    "a1.action.native_dlss_reason": (
        "游戏自带 DLSS，因此 bridge 对它做镜像，而不是替换"
    ),
    # 自带 DLSS / 替换路径
    "a1.check.native_dlss.ok_detail": "游戏目录中有 {count} 个 DLSS 运行时 - 原生镜像路径",
    "a1.check.native_dlss.warn_detail": "游戏未自带 DLSS",
    "a1.check.native_dlss.fix": (
        "替换路径需要手动复制 nvngx_dlss.dll >= 3.1.13 并设置 synth=1；"
        "驱动不会在游戏目录内提供该文件"
    ),
    "a1.missing.substitute.what": "nvngx_dlss.dll（3.1.13 或更高版本）",
    "a1.missing.substitute.why": "替换约定依赖它构建一个合成的 DLAA 会话",
    "a1.missing.substitute.how": "从任何自带 DLSS 的游戏中复制（`nvfku scan` 会列出其中一个）",
    # DLSS NR 模型
    "a1.check.nr_model.ok_detail": "找到经过测试的 build：{path}",
    "a1.action.model_reason_tested": "NapXDD 在 Linux 上实测为稳定的模型",
    "a1.check.nr_model.warn_detail": (
        "本机没有经过测试的 build。找到 {count} 个大小相同但不同的 build，"
        "使用 {path}（sha256 {sha}...）"
    ),
    "a1.check.nr_model.fix": (
        "NapXDD 实测稳定的 build 是 {sha}...；模型不匹配时，每次 evaluate 都可能"
        "返回 Success，然后在游戏运行几分钟后崩溃。启动后请在 ReShade.log 中查看 "
        "'nr-fwd: model nvngx_dlssnr.dll ...' 这一行"
    ),
    "a1.check.nr_model.alt_detail": "{sha}...（位于 {path}）",
    "a1.check.nr_model.alt_fix": "如果第一个 build 崩溃，可以换另一个试试",
    "a1.action.model_reason_untested": (
        "与经过测试的 build 大小相同，摘要不同 - 请从 ReShade.log 核实"
    ),
    "a1.check.nr_model.block_detail": "本机未找到 {name}",
    "a1.check.nr_model.block_fix": (
        "它属于 NVIDIA，但本机上没有。运行 nvfku model --fetch 可获取实测稳定版"
        "（会校验摘要），或自行把副本放到游戏能看到的位置"
    ),
    "a1.missing.model.what": "{name}（{size}，sha256 {sha}...）",
    "a1.missing.model.why": "DLSS 5 神经渲染就是这个 DLL；没有其他东西能替代它",
    "a1.missing.model.how": (
        "它随 Magpie 完整包分发，也出现在启用 DLSS 5 的游戏旁；在本机上 "
        "DLSS5-Swapper/Magpie 把它放在 Windows DOCUMENTS 卷下"
    ),
    "a1.check.nr_model.multiple_detail": "找到 {count} 个不同的 build",
    "a1.check.nr_model.multiple_fix": (
        "优先使用经过测试的 build；其余由 `nvfku show` 列出"
    ),
    # 反作弊
    "a1.check.anticheat.detail": "检测到：{list}",
    "a1.check.anticheat.fix": "ReShade add-on 与反作弊无法共存；封禁会落在你的账号上",
    # 为什么 A1 走 DXGI 代理而不是 Vulkan layer
    "a1.vulkan_note": (
        "ReShade 的 Vulkan 安装方式是一个 Vulkan layer，而 Wine 的 winevulkan "
        "从不枚举第三方 layer，因此这条路线只支持 D3D11/D3D12 游戏。"
    ),
    # 手动步骤
    "a1.manual.install_reshade": (
        "先安装前置的 ReShade——它列在本路线下方的「前置」里，有自己的安装按钮。"
        "没有它，这里其他东西都不会加载。"
    ),
    "a1.manual.launch": "启用 DLSS Super Resolution 后启动游戏。",
    "a1.manual.overlay": (
        "打开 ReShade 覆盖层（Home）-> Add-ons -> 确认列表中同时有 "
        "'DLSS 5 Bridge' 和 'DLSSNR Linux'。"
    ),
    "a1.manual.f10": "按 F10 对神经渲染通道做 A/B 对比。",
    "a1.manual.check_log": (
        "在 ReShade.log 中确认：'nr-fwd: model nvngx_dlssnr.dll ...'，"
        "且没有 FAIL_OutOfDate。"
    ),
    # 启动选项说明（选项字符串本身是标识符）
    "a1.launch.note.custom": "{tool}：自定义 Proton 构建，因此存在的变量是 PROTON_FORCE_NVAPI",
    "a1.launch.note.valve": "{tool}：Valve Proton，因此存在的变量是 PROTON_ENABLE_NVAPI",
    # is_viable 的理由，显示在 `nvfku show` 与扫描结果中
    "a1.reason.api_unknown": "无法确定渲染 API",
    "a1.reason.32bit": "32 位游戏：add-on 只提供 64 位版本",
    "a1.reason.ok": "D3D11/D3D12、64 位，ReShade 以 dxgi 方式可加载",
    "a1.check.launch_options": "Steam 启动项",
    "a1.check.launch_options.ok": "Steam 未运行，可以写入启动项",
    "a1.check.launch_options.blocked": (
        "Steam 客户端正在运行（pid {pids}）。Steam 会把这个值保存在内存里并把它的副本写回，"
        "所以现在写入会被静默回滚。"
    ),
    "a1.check.launch_options.fix_running": (
        "请完全退出 Steam（包括托盘图标）后重试。安装会一直等你关闭它——"
        "没有这些启动项，代理 DLL 不会被加载。"
    ),
    "a1.check.launch_options.fix_error": "无法读取启动项，因此也无法写入。安装的其余部分仍可继续。",
    "a1.action.launch_option_reason": "加载本地 dxgi.dll 并在前缀内启用 NGX",
    "a1.action.model_fetch_reason": (
        "本机没有实测稳定的 {sha} 版本；这是 NVIDIA 签名运行时的钉版副本，下载后会校验摘要"
    ),
}
