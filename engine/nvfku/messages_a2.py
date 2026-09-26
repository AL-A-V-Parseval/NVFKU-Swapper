"""User-facing text owned by route A2: A2 - OptiScaler DLSS-NR (DLL proxy)

Keys are namespaced ``a2.`` so they cannot collide with another route's.
``EN`` and ``ZH`` must hold exactly the same keys: a missing entry falls back to
English and produces a half-translated plan, which the test suite checks for.

Identifiers stay verbatim across both languages — route names, digests,
environment variables, ``%command%``, file names, and API names. A user compares
this text against Steam's properties dialog and against ReShade.log.

Only prose is keyed: values that are *only* an identifier (an API name, a path,
``nvngx_dlssnr.dll``) are composed in code around :func:`text`, so every key here
has something to translate and no key is identical in both languages.
"""

from __future__ import annotations

EN: dict[str, str] = {
    # Title, summary, launch-option note
    "a2.title": "OptiScaler direct",
    "a2.summary": (
        "One proxy DLL, nothing else to install first. Fewer moving parts, but no "
        "overlay controls."
    ),
    "a2.detail": (
        "Places OptiScaler beside the executable as a proxy DLL and lets it run the "
        "DLSS-NR pass over the game's own DLSS output. No ReShade, no Vulkan layer, "
        "and no prerequisite to install. Its own overlay is reached with Insert."
    ),
    "a2.launch_options_note": (
        "the proxy DLL is only loaded if Wine resolves it before the builtin"
    ),
    # Shared value fallbacks
    "a2.value.unknown": "unknown",
    "a2.value.exe_unknown": "(unknown)",
    "a2.list_separator": ", ",
    # Check names
    "a2.check.bitness": "bitness",
    "a2.check.api": "rendering API",
    "a2.check.native_dlss": "native DLSS",
    "a2.check.proxy_conflict": "existing proxy DLLs",
    "a2.check.proxy_slot": "proxy slot",
    "a2.check.extractor": "extractor",
    "a2.check.upstream": "upstream release",
    "a2.check.nr_model": "DLSS NR model",
    "a2.check.anticheat": "anti-cheat",
    # Check details
    "a2.detail.bitness_ok": "64-bit",
    "a2.detail.bitness_block": "{bits}-bit",
    "a2.detail.api_ok": "{api} - proxy DLL path is available",
    "a2.detail.native_dlss_ok": "present: {names} - OptiScaler replaces its output",
    "a2.detail.native_dlss_missing": "no DLSS runtime in the game folder",
    "a2.detail.proxy_conflict": "{names} present in the executable's folder",
    "a2.detail.proxy_slot": "{name} is free beside {exe}",
    "a2.detail.extractor_ok": "7z at {path}",
    "a2.detail.extractor_missing": "no 7z extractor available",
    "a2.detail.upstream": "{version} ({name}, {size})",
    "a2.detail.upstream_failed": "could not resolve from the GitHub API ({error})",
    "a2.detail.nr_model_tested": "tested build: {path}",
    "a2.detail.nr_model_untested": "no tested build on this machine; using {model}",
    "a2.detail.nr_model_missing": "{name} not found",
    "a2.detail.anticheat": "detected: {names}",
    # Check fixes
    "a2.fix.optiscaler_64bit": "OptiScaler is 64-bit only",
    "a2.fix.api": (
        "OptiScaler's DLSS-NR wiring targets D3D12 (and D3D11 through the same "
        "device), and the DX11/Vulkan path goes through a D3D12 bridge with FSR output"
    ),
    "a2.fix.native_dlss": (
        "OptiScaler replaces an upscaler; enable DLSS in the game or redirect "
        "FSR/XeSS into it first (the game must expose one of them)"
    ),
    "a2.fix.proxy_conflict": (
        "choose a different proxy name, or remove the other tool first; two proxies "
        "cannot share one filename"
    ),
    "a2.fix.extractor": "OptiScaler ships a .7z; install p7zip (Arch: `pacman -S p7zip`)",
    "a2.fix.upstream": (
        "check network access; the engine defaults to a direct connection "
        "(set DLSS5_HTTP_PROXY to use a proxy)"
    ),
    "a2.fix.nr_model_untested": (
        "the measured-stable build is {digest}...; watch the game's log if it "
        "crashes after a few minutes"
    ),
    "a2.fix.nr_model_missing": (
        "NVIDIA's file, and not on this machine. Run 'nvfku model --fetch' for the "
        "tested build (digest-checked), or place a copy beside the executable"
    ),
    "a2.fix.anticheat": "an injected upscaler in an anti-cheat game risks the account",
    # Missing-component guidance (the model is a proprietary NVIDIA file)
    "a2.missing.model.why": "the DLSS-NR pass is this model; OptiScaler only drives it",
    "a2.missing.model.how": (
        "copy from a DLSS-5-enabled game or from the Magpie full package"
    ),
    # Action reasons (kind= is a fixed identifier and is never translated)
    "a2.action.copy_reason": "7z archive is unpacked and its DLLs placed beside the executable",
    "a2.action.optiscaler_source": "{name} {version} (.7z, extracted)",
    "a2.action.model_reason": "the neural pass reads it from beside the executable",
    "a2.action.ini_reason": (
        "adds the [DlssNr] section; WorkingScale is the cost dial "
        "(cost scales with its square)"
    ),
    "a2.action.enable_dlss": "enable DLSS in the game's graphics settings",
    "a2.action.enable_dlss_reason": "OptiScaler runs off the game's own DLSS evaluate call",
    # Manual steps
    "a2.manual.install": (
        "Install (copies OptiScaler beside the executable and writes OptiScaler.ini)."
    ),
    "a2.manual.launch": "Launch with the launch options above and enable DLSS in the game.",
    "a2.manual.overlay": (
        "Open OptiScaler's overlay (Insert by default) and confirm the DLSS-NR "
        "section is active."
    ),
    "a2.manual.tune": (
        "Tune WorkingScale under [DlssNr]: 100 is native, lower is cheaper and softer."
    ),
    # is_viable() reasons
    "a2.viable.not_64bit": "OptiScaler is 64-bit only",
    "a2.viable.api": (
        "rendering API is {api}; OptiScaler's DLSS-NR path wants D3D11/D3D12 "
        "(its DX11/Vulkan path goes through a D3D12 bridge)"
    ),
    "a2.viable.no_dlss": (
        "game ships no DLSS runtime, and OptiScaler replaces an upscaler rather "
        "than creating one"
    ),
    "a2.viable.intended": (
        "64-bit D3D11/D3D12 game with its own DLSS - the intended target"
    ),
}

#: Chinese text. Technical identifiers stay as they are, matching EN.
ZH: dict[str, str] = {
    "a2.title": "OptiScaler 直连",
    "a2.summary": "只需要一个代理 DLL，没有要预先安装的东西。环节更少，但没有叠层调节。",
    "a2.detail": (
        "把 OptiScaler 作为代理 DLL 放在可执行文件旁，让它在游戏自身的 DLSS 输出上运行 "
        "DLSS-NR pass。不使用 ReShade，也不使用 Vulkan layer，无需任何前置。它自带叠层，按 Insert 打开。"
    ),
    "a2.launch_options_note": "只有当 Wine 先解析到代理 DLL（而不是内置实现）时，它才会被加载",
    "a2.value.unknown": "未知",
    "a2.value.exe_unknown": "（未知）",
    "a2.list_separator": "、",
    "a2.check.bitness": "位数",
    "a2.check.api": "渲染 API",
    "a2.check.native_dlss": "自带 DLSS",
    "a2.check.proxy_conflict": "已存在的代理 DLL",
    "a2.check.proxy_slot": "代理 DLL 位置",
    "a2.check.extractor": "解压工具",
    "a2.check.upstream": "上游版本",
    "a2.check.nr_model": "DLSS NR 模型",
    "a2.check.anticheat": "反作弊",
    "a2.detail.bitness_ok": "64 位",
    "a2.detail.bitness_block": "{bits} 位",
    "a2.detail.api_ok": "{api}：可以使用代理 DLL 路径",
    "a2.detail.native_dlss_ok": "已存在：{names}——OptiScaler 会替换它的输出",
    "a2.detail.native_dlss_missing": "游戏目录中没有 DLSS 运行时",
    "a2.detail.proxy_conflict": "可执行文件所在目录中已存在 {names}",
    "a2.detail.proxy_slot": "{exe} 旁的 {name} 未被占用",
    "a2.detail.extractor_ok": "7z 位于 {path}",
    "a2.detail.extractor_missing": "没有可用的 7z 解压工具",
    "a2.detail.upstream": "{version}（{name}，{size}）",
    "a2.detail.upstream_failed": "无法从 GitHub API 解析（{error}）",
    "a2.detail.nr_model_tested": "已测试的 build：{path}",
    "a2.detail.nr_model_untested": "本机没有已测试的 build；改用 {model}",
    "a2.detail.nr_model_missing": "未找到 {name}",
    "a2.detail.anticheat": "检测到：{names}",
    "a2.fix.optiscaler_64bit": "OptiScaler 仅支持 64 位",
    "a2.fix.api": (
        "OptiScaler 的 DLSS-NR 接入面向 D3D12（D3D11 也走同一设备），"
        "DX11/Vulkan 路径则要经过带 FSR 输出的 D3D12 桥接"
    ),
    "a2.fix.native_dlss": (
        "OptiScaler 是替换现有的超分器，而不是新建一个；请先在游戏中启用 DLSS，"
        "或先把 FSR/XeSS 重定向到 DLSS（游戏必须暴露其中之一）"
    ),
    "a2.fix.proxy_conflict": "请换一个代理 DLL 名称，或先移除另一个工具；两个代理不能共用同一个文件名",
    "a2.fix.extractor": "OptiScaler 以 .7z 分发；请安装 p7zip（Arch：`pacman -S p7zip`）",
    "a2.fix.upstream": "请检查网络连接；引擎默认直连（如需代理，请设置 DLSS5_HTTP_PROXY）",
    "a2.fix.nr_model_untested": (
        "实测稳定的 build 是 {digest}...；如果游戏运行几分钟后崩溃，请查看游戏日志"
    ),
    "a2.fix.nr_model_missing": (
        "这是 NVIDIA 的文件，但本机上没有。运行 nvfku model --fetch 可获取实测稳定版"
        "（会校验摘要），或自行放一份到可执行文件旁"
    ),
    "a2.fix.anticheat": "在反作弊游戏中使用注入式超分器有封号风险",
    "a2.missing.model.why": "DLSS-NR pass 用的就是这个模型；OptiScaler 只负责驱动它",
    "a2.missing.model.how": "从启用了 DLSS 5 的游戏复制，或从 Magpie 完整包中复制",
    "a2.action.copy_reason": "解压 7z 压缩包，并将其中的 DLL 放到可执行文件旁",
    "a2.action.optiscaler_source": "{name} {version}（.7z，已解压）",
    "a2.action.model_reason": "神经网络 pass 会从可执行文件旁读取它",
    "a2.action.ini_reason": "写入 [DlssNr] 段；WorkingScale 是开销调节项（开销随其平方增长）",
    "a2.action.enable_dlss": "在游戏的图形设置中启用 DLSS",
    "a2.action.enable_dlss_reason": "OptiScaler 依赖游戏自身的 DLSS evaluate 调用运行",
    "a2.manual.install": "执行安装（把 OptiScaler 复制到可执行文件旁，并写入 OptiScaler.ini）。",
    "a2.manual.launch": "使用上面的启动选项启动游戏，并在游戏中启用 DLSS。",
    "a2.manual.overlay": "打开 OptiScaler 覆盖层（默认按键 Insert），确认 DLSS-NR 段已生效。",
    "a2.manual.tune": "在 [DlssNr] 下调整 WorkingScale：100 为原生，数值越低开销越小、画面越软。",
    "a2.viable.not_64bit": "OptiScaler 仅支持 64 位",
    "a2.viable.api": (
        "渲染 API 是 {api}；OptiScaler 的 DLSS-NR 路径需要 D3D11/D3D12"
        "（它的 DX11/Vulkan 路径要经过 D3D12 桥接）"
    ),
    "a2.viable.no_dlss": "游戏没有自带 DLSS 运行时，而 OptiScaler 是替换超分器，不是新建一个",
    "a2.viable.intended": "自带 DLSS 的 64 位 D3D11/D3D12 游戏——正是目标场景",
}
