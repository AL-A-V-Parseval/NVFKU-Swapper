/// Localisation: English and Chinese, with no code generation.
///
/// Deliberately a plain map rather than `flutter gen-l10n`. The app has one
/// language pair and about seventy strings; an ARB pipeline would add a build
/// step, a generated file and a dependency to maintain in exchange for nothing
/// that `t('key')` does not already do.
///
/// Two translation choices worth stating:
///
/// * **Engine vocabulary stays English inside sentences.** Route names, digests,
///   `%command%`, and API names like `DirectX 12` are identifiers a user will see
///   in Steam's properties dialog and in the tool's own logs. Translating them
///   would break the correspondence between what the UI says and what the log
///   says — which is the one thing this tool must not do.
/// * **The language is stored, not inferred every launch**, so a user who wants
///   English on a Chinese system keeps it.
library;

import 'package:flutter/material.dart';

/// Supported languages, in the order the picker shows them.
enum AppLanguage { system, english, chinese }

extension AppLanguageX on AppLanguage {
  String get code => switch (this) {
        AppLanguage.system => 'system',
        AppLanguage.english => 'en',
        AppLanguage.chinese => 'zh',
      };

  String get label => switch (this) {
        AppLanguage.system => '跟随系统 / System',
        AppLanguage.english => 'English',
        AppLanguage.chinese => '简体中文',
      };

  static AppLanguage fromCode(String? code) => switch (code) {
        'en' => AppLanguage.english,
        'zh' => AppLanguage.chinese,
        _ => AppLanguage.system,
      };
}

/// The current language. A notifier so a change repaints without a restart.
final ValueNotifier<AppLanguage> appLanguage =
    ValueNotifier<AppLanguage>(AppLanguage.system);

/// Resolves the effective language against the platform's preferred locales.
Locale effectiveLocale(AppLanguage preference, Locale? platform) {
  switch (preference) {
    case AppLanguage.english:
      return const Locale('en');
    case AppLanguage.chinese:
      return const Locale('zh');
    case AppLanguage.system:
      final code = platform?.languageCode ?? 'en';
      return Locale(code == 'zh' ? 'zh' : 'en');
  }
}

/// The English table, exposed so a test can prove the two agree.
const Map<String, String> englishStrings = <String, String>{
  // Shell
  'app.title': 'NVFKU-Swapper',
  'app.subtitle': 'DLSS 5 Swapper for Linux',
  'app.windowTitle': 'NVFKU-Swapper',
  'nav.home': 'Home',
  'home.dropTitle': 'Drop a game folder here',
  'home.dropHint': 'or browse for one. It is registered for this tool only',
  'home.browse': 'Browse for a folder',
  'home.recentTitle': 'Recent',
  'home.recentSubtitle': 'The games this tool has changed, newest first.',
  'home.refresh': 'Refresh',
  'home.nothingTitle': 'Nothing installed yet',
  'home.nothingBody':
      'Install into a game and it appears here. Every entry is a recorded '
      'operation you can undo.',
  'home.activityTitle': 'Activity',
  'home.activitySubtitle': 'The journal, newest first. Each line is reversible.',
  'home.logError': 'Could not read the journal',
  'home.stateLive': 'live',
  'home.stateRolledBack': 'undone',
  'home.more': 'and {n} older entries — see History',
  'home.justNow': 'just now',
  'home.minAgo': '{n} min ago',
  'home.hourAgo': '{n} h ago',
  'home.dayAgo': '{n} d ago',
  'nav.games': 'Games',
  'nav.addons': 'Add-ons',
  'nav.history': 'History',
  'nav.about': 'About',
  'about.tagline':
      'Puts DLSS 5 neural rendering into your Linux games, and takes it back out '
      'again whenever you want.',
  'about.whyTwoRoutes':
      'Both routes use a local DLL proxy, because a Vulkan layer cannot be loaded '
      'under Proton at all.',
  'about.standsOnTitle': 'Built on',
  'about.byOptiscaler': 'the OptiScaler project',
  'about.undoNote':
      'Every change is journalled before it is applied, so History can undo one '
      'exactly: replaced files are restored byte for byte and created files are '
      'removed.',
  'nav.settings': 'Settings',
  'status.starting': 'Starting the engine…',
  'status.scanning': 'Scanning your Steam libraries…',
  'status.summary': '{version} · {games} games · {dlss} ship DLSS',
  'status.summaryModel': '{version} · {games} games · {dlss} ship DLSS · {model} carry a DLSS NR model',
  'engine.failedTitle': 'The engine could not start',
  'common.tryAgain': 'Try again',
  'common.cancel': 'Cancel',
  'common.refresh': 'Refresh',
  'common.reload': 'Reload',
  'common.save': 'Save',
  'common.rescan': 'Rescan',
  'common.dismiss': 'Dismiss',
  'common.close': 'Close',
  'common.installed': 'Installed',
  'common.installing': 'Installing…',
  'common.working': 'working…',
  'common.lastRun': 'last run finished',
  'common.blocked': 'blocked',
  'common.ready': 'ready',
  'common.viable': 'viable',
  'common.probe': 'probe',
  'common.journal': 'journal',
  'common.stillOnYou': 'Still on you',
  'common.notWritten': 'Not written',

  // Games
  'games.title': 'Games',
  'games.filter': 'Filter by name or appid',
  'games.addFolder': 'Add folder',
  'games.addFolderTip': 'Register a game folder Steam does not manage, or drop one onto the window',
  'games.dropHere': 'Drop a game folder here',
  'games.emptyTitle': 'No games found',
  'games.emptyBody':
      'The engine walks your Steam libraries and their Proton prefixes. If you expected games here, check that Steam has created steamapps/libraryfolders.vdf, or add a folder by hand.',
  'games.nothingMatches': 'Nothing matches',
  'games.nothingMatchesBody': 'No game name or appid contains "{filter}".',
  'games.summary': '{games} games',
  'games.summaryDlss': '{n} ship DLSS',
  'games.summaryModel': '{n} carry a DLSS NR model',
  'games.summaryFolders': '{n} added by hand',
  'games.dropFailedTitle': 'That folder was not added',
  'games.addTitle': 'Add a game folder',
  'games.addBody':
      'Point this at the folder holding the game executable. It is registered for this tool only; nothing is installed until you ask.',
  'games.addHint': '/games/Some Game',
  'games.add': 'Add',
  'games.noPrefix': 'no prefix',
  'games.noSteamPrefix': 'no Steam prefix',
  'games.unknownApi': 'unknown API',
  'games.addedByHand': 'added',
  'games.nrNone': 'not found on this machine',
  'games.nrPresent': 'present ({n} builds)',
  'games.install': 'Install',
  'games.hidePlan': 'Hide plan',
  'games.installTip': 'Show what installing would change, then confirm',
  'games.hidePlanTip': 'Hide the plan',
  'menu.details': 'Open details',
  'menu.install': 'Install…',
  'menu.rescan': 'Rescan this game',
  'menu.openFolder': 'Open game folder',
  'menu.copyPath': 'Copy folder path',
  'menu.copied': 'Folder path copied',
  'menu.restore': 'Restore originals',
  'menu.restoreTitle': 'Restore the original files for this game?',
  'menu.restoreBody':
      'The most recent install is undone: the files it replaced are put back '
      'exactly as they were, and the files it created are removed. Nothing is '
      'touched beyond that install.',
  'menu.restoreConfirm': 'Restore originals',

  // Routes and plan
  'plan.technicalDetail': 'How it works',
  'plan.blockedNoReason': 'A required piece is missing — see the checks below.',
  'plan.developerDetail': 'Checks and actions',
  'plan.developerDetailHint': 'what the engine inspected and would change',
  'plan.installLog': 'Install log',
  'plan.installLogHint': 'every line the engine printed',
  'plan.prerequisite': 'Needs',
  'plan.installComponent': 'Install',
  'plan.ready': 'ready',
  'plan.blocked': 'blocked',
  'plan.probe': 'probe',
  'plan.steamTitle': 'Close Steam to continue',
  'plan.steamBody':
      'Steam keeps each game\'s launch options in memory and writes its own copy '
      'back, so a change made while it runs is silently reverted. This route needs '
      'those options to load. Exit Steam completely — including the tray icon — and '
      'this button unlocks on its own.',
  'plan.steamWait': 'Wait for Steam to close',
  'plan.steamRecheck': 'Check again',
  'plan.steamBlocked': 'Waiting for Steam to close',
  'plan.steamBlockedTip':
      'A1 needs launch options that Steam would revert while it is running',
  'plan.launchOptionsCurrent': 'launch options now',
  'plan.confirm': 'Confirm and install',
  'plan.cannotInstall': 'Cannot install',
  'plan.nothingToInstall': 'Nothing to install',
  'plan.confirmTip': 'Writes exactly the plan above, after backing up every file it replaces',
  'plan.resolveFirst': 'Resolve the blockers first',
  'plan.probeTip': 'This route only reports; it has nothing to install',
  'plan.details': 'Routes, plan details and launch options',
  'plan.refusedTitle': 'Refused — nothing was written',
  'plan.couldNotPlan': 'Could not plan this game',
  'plan.noRoute': 'No route applies to this game',
  'plan.noRouteBody':
      'Usually that means the rendering API is neither D3D11 nor D3D12, or the game is 32-bit.',
  'plan.wouldChangeOne': 'Would change {n} file:',
  'plan.wouldChangeMany': 'Would change {n} files:',
  'plan.andMore': '…and {n} more',
  'plan.thisGame': 'This game',
  'plan.routesTitle': 'Routes',
  'plan.routesSubtitle':
      'One route installs one set of components. Viability is checked against this game, not in general.',
  'plan.planTitle': 'Plan',
  'plan.planSubtitle': 'Everything below is checked before anything is written.',
  'plan.planReadOnly': 'This route only reports; it writes nothing.',
  'plan.whatWouldChange': 'What would change',
  'plan.filesYouSupply': 'Files you must supply',
  'plan.launchNeeded': 'Steam launch options this route needs',
  'plan.neuralResolution': 'Neural pass resolution',
  'plan.neuralCost': 'Cost scales with the square of this; 100 is native and sharpest.',
  'plan.backToGames': 'Back to Games',
  'plan.appid': 'appid',
  'plan.renderingApi': 'rendering API',
  'plan.bitness': 'bitness',
  'plan.launchExe': 'launch exe',
  'plan.protonTool': 'proton tool',
  'plan.noPrefix': 'no Proton prefix found',
  'plan.nativeDlss': 'native DLSS',
  'plan.none': 'none',
  'plan.nrModel': 'DLSS NR model',
  'plan.reshade': 'ReShade',
  'plan.reshadeInstalled': 'installed beside the executable',
  'plan.reshadeNot': 'not installed',
  'plan.apiEvidence': 'How the API was decided',
  'plan.kind.copy': 'copy',
  'plan.kind.write': 'write',
  'plan.kind.delete': 'delete',
  'plan.kind.mkdir': 'mkdir',
  'plan.kind.launch': 'launch',
  'plan.kind.note': 'note',
  'plan.optional': '(optional)',

  // Launch options
  'lo.title': 'Steam launch options',
  'lo.reading': 'Reading the Steam configuration…',
  'lo.blockedHint': 'Writing is blocked while a Steam client is running.',
  'lo.readyHint': 'Steam is not running, so a write will be kept.',
  'lo.blocked': 'blocked',
  'lo.ready': 'ready',
  'lo.current': 'current',
  'lo.noneSet': '(none set)',
  'lo.config': 'config',
  'lo.exitSteamTitle': 'Exit Steam to enable writing',
  'lo.exitSteamBody':
      'Steam keeps this value in memory and would write its copy back over ours, so the write is refused rather than silently lost. Exit Steam completely — including the tray icon — then refresh.',
  'lo.wouldWrite': '{route} would write',
  'lo.update': 'Update in Steam config',
  'lo.write': 'Write to Steam config',
  'lo.writeTip': 'Edits one line in localconfig.vdf, after backing the file up',
  'lo.clear': 'Clear',
  'lo.addedTitle': 'Added the key to the Steam config',
  'lo.updatedTitle': 'Updated the key in the Steam config',
  'lo.backup': 'backup',
  'lo.was': 'was: {value}',
  'lo.noSteamTitle': 'No Steam launch options for this game',
  'lo.noSteamBody':
      'It was added by hand, so Steam has no appid to attach options to. Set the environment variables in whatever launches it.',

  // Add-ons
  'addons.title': 'Add-ons',
  'addons.subtitle': 'What the routes install, and the exact bytes they expect.',
  'addons.pinned': 'Pinned',
  'addons.pinnedNote':
      'These bytes are verified. A mismatch is refused before anything reaches a game directory.',
  'addons.rolling': 'Rolling',
  'addons.rollingNote':
      'Resolved from the publisher at install time, so the version shown is what would be fetched now.',
  'addons.pinnedPill': 'pinned',
  'addons.rollingPill': 'rolling',
  'addons.readError': 'Could not read the component list',
  'addons.neverTitle': 'What is never downloaded',
  'addons.neverBody':
      "NVIDIA's nvngx_dlssnr.dll and nvngx_dlss.dll are proprietary. This tool locates copies you already have and classifies each by digest. For the NR model only, it can fetch the one measured build from a pinned community mirror, saying that it is a mirror and verifying the digest before use. DLSS Super Resolution and frame generation are never downloaded.",
  'addons.artworkTitle': 'Cover artwork',
  'addons.artworkBody':
      "Steam's own cover images are cached next to the engine's other state, one download per game. Localised covers are preferred when Steam publishes them.",
  'addons.artworkFetch': 'Fetch missing artwork',
  'addons.artworkDone': '{found} of {total} games now have a cover.',

  // History
  'history.title': 'History',
  'history.subtitle':
      'Every change this tool has made, newest first. Undoing one restores the files it replaced.',
  'history.readError': 'Could not read the journals',
  'history.emptyTitle': 'Nothing installed yet',
  'history.emptyBody':
      'Journals appear here after an install. Each one records the files it replaced, so it can be undone exactly.',
  'history.rollBack': 'Roll back',
  'history.undoAgain': 'Undo again',
  'history.rollBackTip': 'Replays the journal backwards and restores every file',
  'history.rolledBack': 'rolled back',
  'history.complete': 'complete',
  'history.incomplete': 'incomplete',
  'history.operations': '{n} operations',
  'history.rolledBackTitle': 'Rolled back',
  'history.undoHint': 'Undo it from History, or with:',
  'history.note':
      "Backups live under the engine state directory, not inside the game folder, so a game can be verified against its store without the tool's own files confusing the check.",

  // Settings
  'settings.title': 'Settings',
  'settings.subtitle':
      'Stored as plain JSON under the engine state directory, so you can read or edit it directly.',
  'settings.readError': 'Could not read the settings',
  'settings.python': 'Python interpreter',
  'settings.pythonHint': 'empty uses the project venv, else python3',
  'settings.pythonHelp':
      'The engine is a Python process. Set this if it should run under a different interpreter.',
  'settings.steamRoot': 'Steam root',
  'settings.steamRootHint': 'empty uses discovery',
  'settings.steamRootHelp':
      'The install holding steamapps/libraryfolders.vdf. Set this for a Flatpak Steam or a Steam on another drive.',
  'settings.cache': 'Component cache',
  'settings.cacheHint': 'empty uses the state directory',
  'settings.cacheHelp': 'Where downloaded add-ons are kept between installs.',
  'settings.verify': 'Verify components against the publisher',
  'settings.verifyHelp':
      'Compare each downloaded add-on with the digest its release page publishes. Pinned components are checked either way.',
  'settings.language': 'Language',
  'settings.languageHelp':
      'Applies to this interface. Route names, digests and API names stay in English because they are identifiers you will also see in Steam and in the logs.',
  'settings.saved': 'Saved. Rescanning the library with the new settings.',
  'settings.file': 'settings file',
  'settings.fileNote': 'shown by the CLI with `nvfku settings`',
};

/// The Chinese table.
const Map<String, String> chineseStrings = <String, String>{
  // Shell
  'app.title': 'NVFKU-Swapper',
  'app.subtitle': 'Linux 下的 DLSS5 替换器',
  'app.windowTitle': 'NVFKU-Swapper',
  'nav.home': '首页',
  'home.dropTitle': '把游戏文件夹拖到这里',
  'home.dropHint': '或点下面的按钮选择。它只在本工具内登记',
  'home.browse': '选择文件夹',
  'home.recentTitle': '最近',
  'home.recentSubtitle': '本工具改动过的游戏，最新的在前。',
  'home.refresh': '刷新',
  'home.nothingTitle': '还没有安装记录',
  'home.nothingBody': '安装后这里会出现。每一条都是可撤销的已记录操作。',
  'home.activityTitle': '活动',
  'home.activitySubtitle': '日志记录，最新的在前。每一行都可以撤销。',
  'home.logError': '无法读取日志',
  'home.stateLive': '生效中',
  'home.stateRolledBack': '已撤销',
  'home.more': '另有 {n} 条较早记录 — 见「历史」',
  'home.justNow': '刚刚',
  'home.minAgo': '{n} 分钟前',
  'home.hourAgo': '{n} 小时前',
  'home.dayAgo': '{n} 天前',
  'nav.games': '游戏',
  'nav.addons': '组件',
  'nav.history': '历史',
  'nav.about': '关于',
  'about.tagline': '把 DLSS 5 神经渲染装进你的 Linux 游戏，也随时能干净地拿回来。',
  'about.whyTwoRoutes':
      '两条路线都用本地 DLL 代理，因为在 Proton 下 Vulkan layer 根本无法加载。',
  'about.standsOnTitle': '基于以下项目',
  'about.byOptiscaler': 'OptiScaler 项目',
  'about.undoNote':
      '每次改动在写入前都会记账，所以「历史」可以精确撤销：被替换的文件逐字节还原，新建的文件被删除。',
  'nav.settings': '设置',
  'status.starting': '正在启动引擎…',
  'status.scanning': '正在扫描你的 Steam 库…',
  'status.summary': '{version} · {games} 个游戏 · {dlss} 个自带 DLSS',
  'status.summaryModel': '{version} · {games} 个游戏 · {dlss} 个自带 DLSS · {model} 个带 DLSS NR 模型',
  'engine.failedTitle': '引擎无法启动',
  'common.tryAgain': '重试',
  'common.cancel': '取消',
  'common.refresh': '刷新',
  'common.reload': '重新读取',
  'common.save': '保存',
  'common.rescan': '重新扫描',
  'common.dismiss': '关闭',
  'common.close': '关闭',
  'common.installed': '已安装',
  'common.installing': '正在安装…',
  'common.working': '处理中…',
  'common.lastRun': '上次运行已结束',
  'common.blocked': '受阻',
  'common.ready': '就绪',
  'common.viable': '可用',
  'common.probe': '探测',
  'common.journal': '日志编号',
  'common.stillOnYou': '仍需你做',
  'common.notWritten': '未写入',

  // Games
  'games.title': '游戏',
  'games.filter': '按名称或 appid 筛选',
  'games.addFolder': '添加文件夹',
  'games.addFolderTip': '登记一个 Steam 未管理的游戏目录，也可以直接把文件夹拖进窗口',
  'games.dropHere': '把游戏文件夹拖到这里',
  'games.emptyTitle': '没有找到游戏',
  'games.emptyBody':
      '引擎会遍历你的 Steam 库及其 Proton 前缀。如果你预期这里有游戏，请确认 Steam 已经生成 steamapps/libraryfolders.vdf，或手动添加文件夹。',
  'games.nothingMatches': '没有匹配项',
  'games.nothingMatchesBody': '没有游戏名或 appid 包含“{filter}”。',
  'games.summary': '{games} 个游戏',
  'games.summaryDlss': '{n} 个自带 DLSS',
  'games.summaryModel': '{n} 个带 DLSS NR 模型',
  'games.summaryFolders': '{n} 个手动添加',
  'games.dropFailedTitle': '该文件夹未被添加',
  'games.addTitle': '添加游戏文件夹',
  'games.addBody': '指向存放游戏可执行文件的目录。它只在本工具内登记，未经你确认不会安装任何东西。',
  'games.addHint': '/games/某个游戏',
  'games.add': '添加',
  'games.noPrefix': '无前缀',
  'games.noSteamPrefix': '无 Steam 前缀',
  'games.unknownApi': '未知 API',
  'games.addedByHand': '手动添加',
  'games.nrNone': '本机未找到',
  'games.nrPresent': '已有（{n} 个 build）',
  'games.install': '安装',
  'games.hidePlan': '收起方案',
  'games.installTip': '先展开安装会影响什么，再确认',
  'games.hidePlanTip': '收起方案',
  'menu.details': '打开详情',
  'menu.install': '安装…',
  'menu.rescan': '重新扫描此游戏',
  'menu.openFolder': '打开游戏目录',
  'menu.copyPath': '复制目录路径',
  'menu.copied': '已复制目录路径',
  'menu.restore': '恢复原始文件',
  'menu.restoreTitle': '要恢复该游戏的原始文件吗？',
  'menu.restoreBody':
      '将撤销最近一次安装：它替换过的文件会逐字节还原，它新建的文件会被删除。'
      '这次安装之外的内容不会被改动。',
  'menu.restoreConfirm': '恢复原始文件',

  // Routes and plan
  'plan.technicalDetail': '它是怎么工作的',
  'plan.blockedNoReason': '缺少必需的文件——见下方检查项。',
  'plan.developerDetail': '检查项与将执行的动作',
  'plan.developerDetailHint': '引擎检查了什么、会改什么',
  'plan.installLog': '安装日志',
  'plan.installLogHint': '引擎打印的每一行',
  'plan.prerequisite': '前置',
  'plan.installComponent': '安装',
  'plan.ready': '就绪',
  'plan.blocked': '受阻',
  'plan.probe': '探测',
  'plan.steamTitle': '请关闭 Steam 后继续',
  'plan.steamBody':
      'Steam 会把每个游戏的启动项保存在内存里并把它的副本写回，所以它在运行时做的修改会被静默回滚。'
      '这条路线需要那些启动项才能加载。请完全退出 Steam（包括托盘图标），这个按钮会自己解锁。',
  'plan.steamWait': '等待 Steam 关闭',
  'plan.steamRecheck': '重新检查',
  'plan.steamBlocked': '等待 Steam 关闭',
  'plan.steamBlockedTip': 'A1 需要的启动项在 Steam 运行期间会被回滚',
  'plan.launchOptionsCurrent': '当前启动项',
  'plan.confirm': '确认并安装',
  'plan.cannotInstall': '无法安装',
  'plan.nothingToInstall': '无需安装',
  'plan.confirmTip': '严格按上面的方案写入，替换每个文件前都会先备份',
  'plan.resolveFirst': '请先解决上面的阻塞项',
  'plan.probeTip': '这条路线只做探测，没有可安装的内容',
  'plan.details': '路线、方案详情与启动项',
  'plan.refusedTitle': '已拒绝 — 未写入任何内容',
  'plan.couldNotPlan': '无法为该游戏生成方案',
  'plan.noRoute': '没有适用于该游戏的路线',
  'plan.noRouteBody': '通常意味着渲染 API 既不是 D3D11 也不是 D3D12，或者游戏是 32 位。',
  'plan.wouldChangeOne': '将改动 {n} 个文件：',
  'plan.wouldChangeMany': '将改动 {n} 个文件：',
  'plan.andMore': '…另有 {n} 个',
  'plan.thisGame': '该游戏',
  'plan.routesTitle': '路线',
  'plan.routesSubtitle': '每条路线安装一套组件。可用性是针对这个游戏判定的，不是通用结论。',
  'plan.planTitle': '方案',
  'plan.planSubtitle': '写入之前，下面每一项都已检查。',
  'plan.planReadOnly': '这条路线只做探测，不写入任何内容。',
  'plan.whatWouldChange': '会改动什么',
  'plan.filesYouSupply': '需要你提供的文件',
  'plan.launchNeeded': '这条路线需要的 Steam 启动项',
  'plan.neuralResolution': '神经通道分辨率',
  'plan.neuralCost': '开销随该值的平方增长；100 为原生、最清晰。',
  'plan.backToGames': '返回游戏列表',
  'plan.appid': 'appid',
  'plan.renderingApi': '渲染 API',
  'plan.bitness': '位数',
  'plan.launchExe': '启动程序',
  'plan.protonTool': 'Proton 版本',
  'plan.noPrefix': '未找到 Proton 前缀',
  'plan.nativeDlss': '自带 DLSS',
  'plan.none': '无',
  'plan.nrModel': 'DLSS NR 模型',
  'plan.reshade': 'ReShade',
  'plan.reshadeInstalled': '已装在可执行文件旁',
  'plan.reshadeNot': '未安装',
  'plan.apiEvidence': 'API 是如何判定的',
  'plan.kind.copy': '复制',
  'plan.kind.write': '写入',
  'plan.kind.delete': '删除',
  'plan.kind.mkdir': '建目录',
  'plan.kind.launch': '启动项',
  'plan.kind.note': '说明',
  'plan.optional': '（可选）',

  // Launch options
  'lo.title': 'Steam 启动项',
  'lo.reading': '正在读取 Steam 配置…',
  'lo.blockedHint': 'Steam 客户端运行期间不允许写入。',
  'lo.readyHint': 'Steam 未运行，写入会被保留。',
  'lo.blocked': '已阻止',
  'lo.ready': '可写入',
  'lo.current': '当前值',
  'lo.noneSet': '（未设置）',
  'lo.config': '配置文件',
  'lo.exitSteamTitle': '退出 Steam 后才能写入',
  'lo.exitSteamBody':
      'Steam 会把这个值保存在内存里，并把它的副本写回、覆盖我们的修改。所以这里直接拒绝写入，而不是让它静默丢失。请完全退出 Steam（包括托盘图标），然后刷新。',
  'lo.wouldWrite': '{route} 将写入',
  'lo.update': '更新 Steam 配置',
  'lo.write': '写入 Steam 配置',
  'lo.writeTip': '在备份之后，只修改 localconfig.vdf 中的一行',
  'lo.clear': '清除',
  'lo.addedTitle': '已在 Steam 配置中新增该键',
  'lo.updatedTitle': '已在 Steam 配置中更新该键',
  'lo.backup': '备份',
  'lo.was': '原值：{value}',
  'lo.noSteamTitle': '该游戏没有 Steam 启动项',
  'lo.noSteamBody':
      '它是手动添加的，Steam 没有对应 appid 可挂载启动项。请在你实际启动它的地方自行设置环境变量。',

  // Add-ons
  'addons.title': '组件',
  'addons.subtitle': '各条路线会安装什么，以及它们期望的确切字节。',
  'addons.pinned': '已钉定',
  'addons.pinnedNote': '这些字节会被校验。不一致会在任何文件进入游戏目录之前被拒绝。',
  'addons.rolling': '滚动版本',
  'addons.rollingNote': '在安装时从发布方解析，所以显示的版本就是当前会拉取的版本。',
  'addons.pinnedPill': '已钉定',
  'addons.rollingPill': '滚动',
  'addons.readError': '无法读取组件列表',
  'addons.neverTitle': '哪些东西永远不会被下载',
  'addons.neverBody':
      'NVIDIA 的 nvngx_dlssnr.dll 与 nvngx_dlss.dll 是私有的。本工具会找到你已有的副本并按摘要分类。'
      '仅对 NR 模型，它可以从钉版的社区镜像获取那个实测稳定的 build——会说明它是镜像，并在使用前校验摘要。'
      'DLSS 超分辨率与帧生成永不下载。',
  'addons.artworkTitle': '封面图',
  'addons.artworkBody':
      'Steam 自己的封面图会缓存在引擎状态目录旁，每个游戏只下载一次。若 Steam 提供本地化封面，则优先使用。',
  'addons.artworkFetch': '补齐缺失的封面',
  'addons.artworkDone': '{total} 个游戏中有 {found} 个已有封面。',

  // History
  'history.title': '历史',
  'history.subtitle': '本工具做过的所有改动，最新的在前。回滚其中一条会还原它替换过的文件。',
  'history.readError': '无法读取日志',
  'history.emptyTitle': '还没有安装记录',
  'history.emptyBody': '安装后这里会出现日志。每条都记录了它替换过的文件，所以可以精确撤销。',
  'history.rollBack': '回滚',
  'history.undoAgain': '再次撤销',
  'history.rollBackTip': '反向回放日志并还原每个文件',
  'history.rolledBack': '已回滚',
  'history.complete': '已完成',
  'history.incomplete': '未完成',
  'history.operations': '{n} 次操作',
  'history.rolledBackTitle': '已回滚',
  'history.undoHint': '可在“历史”里撤销，或使用：',
  'history.note':
      '备份保存在引擎状态目录下，而不是游戏目录里，这样用商店校验游戏文件时不会被本工具自己的文件干扰。',

  // Settings
  'settings.title': '设置',
  'settings.subtitle': '以纯 JSON 保存在引擎状态目录下，你可以直接查看或编辑。',
  'settings.readError': '无法读取设置',
  'settings.python': 'Python 解释器',
  'settings.pythonHint': '留空则使用项目 venv，否则用 python3',
  'settings.pythonHelp': '引擎是一个 Python 进程。需要用别的解释器运行时在这里指定。',
  'settings.steamRoot': 'Steam 根目录',
  'settings.steamRootHint': '留空则自动发现',
  'settings.steamRootHelp':
      '即存放 steamapps/libraryfolders.vdf 的安装目录。Flatpak 版 Steam 或装在别的盘上时在这里指定。',
  'settings.cache': '组件缓存',
  'settings.cacheHint': '留空则使用状态目录',
  'settings.cacheHelp': '下载的组件在两次安装之间保存在哪里。',
  'settings.verify': '对照发布方校验组件',
  'settings.verifyHelp':
      '把每个下载的组件与它 release 页公布的摘要比对。已钉定的组件无论如何都会校验。',
  'settings.language': '语言',
  'settings.languageHelp':
      '只影响本界面。路线名、摘要和 API 名称保持英文——它们是标识符，你在 Steam 和日志里看到的也是这些。',
  'settings.saved': '已保存。正在用新设置重新扫描游戏库。',
  'settings.file': '设置文件',
  'settings.fileNote': '可用命令行 `nvfku settings` 查看',
};

Map<String, String> stringsFor(Locale locale) =>
    locale.languageCode == 'zh' ? chineseStrings : englishStrings;

/// Looks up a key and substitutes `{name}` placeholders.
///
/// An unknown key returns the key itself rather than throwing: a missing
/// translation should render as an obvious placeholder, not take the window down.
String translate(Locale locale, String key, [Map<String, Object?>? values]) {
  final table = stringsFor(locale);
  var text = table[key] ?? englishStrings[key] ?? key;
  if (values != null) {
    for (final entry in values.entries) {
      text = text.replaceAll('{${entry.key}}', '${entry.value}');
    }
  }
  return text;
}

/// `context.t('plan.confirm')`, with the locale resolved from the widget tree.
extension Translation on BuildContext {
  String t(String key, [Map<String, Object?>? values]) =>
      translate(Localizations.localeOf(this), key, values);
}
