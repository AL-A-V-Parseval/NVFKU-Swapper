# NVFKU-Swapper

[English](README.md) · **简体中文**

一个面向 Linux 原生的 DLSS 5 社区路线安装器。设计思路上参考
[DLSS5-Swapper](https://github.com/rakanki911/DLSS5-Swapper)，但围绕一个那个工具
不必面对的事实重新构建：

> **Wine 的 Vulkan loader 从不枚举第三方 layer。**
> `winevulkan` 的 `vkEnumerateInstanceLayerProperties` 返回零个 layer，而它的 loader
> 只认 `HKLM\Software\Khronos\Vulkan\Drivers`（也就是 ICD 注册表键）。
> 任何工具都无法为 Proton 游戏注册 Vulkan layer，因为游戏的 `vkCreateInstance`
> 会以 `VK_ERROR_LAYER_NOT_PRESENT` 失败。

这里每一个设计决策都源自这一点，外加另外四条实测得出的约束：

| 约束 | 后果 |
| --- | --- |
| 由驱动分发的 NGX feature 18 在 Proton 下失败（`FAIL_OutOfDate`） | 神经渲染的消费方必须直接从 DLL 驱动该 feature |
| 驱动 32.0.16.1664 / 1686 会把 feature 18 引到一段会崩的代码里 | 钉定版本并如实报告，比"最新"更重要 |
| 在 Linux 上 ReShade 的代理描述符必须保持原生（`unwrap=0`），与 Windows 的默认值相反 | 桥接的配置就是天真移植会崩溃的地方 |
| 双系统机器上的游戏目录里常常已经有那个私有模型 | 先发现并按摘要分类，只有在找不到可用副本时才下载 |

## 目录结构

```
engine/                 纯 Python，只用标准库，不依赖 GUI
  nvfku/
    paths.py            文件系统层；原子写入，正确处理符号链接
    pe.py               手写的 PE 读取器（位数、导入表、字符串）
    steam.py            Steam 库发现，API/位数/DLSS 检测
    journal.py          事务式文件日志，可精确回滚
    providers.py        上游 release 解析 + 哈希钉定
    model.py            定位 nvngx_dlssnr.dll 并按摘要分类
    anticheat.py        基于证据的反作弊检测
    plan.py             RoutePlan/Action/Check 词汇表（dry-run 就是安装器的前半段）
    route/
      a1_bridge.py      ReShade + dlss5-bridge + addon-dlssnr-linux
      a2_optiscaler.py  OptiScaler DLSS-NR（DLL 代理）
    __main__.py         命令行
  tests/                232 项测试，标准库 unittest
app/                    Flutter 界面（只用 Flutter SDK，无第三方包）
tools/env.sh            隔离：项目 venv + 钉定的 SDK + 本地 pub 缓存
tools/install_desktop.py  为源码目录创建菜单入口，写入用户级 XDG 目录
```

## 隔离

不往系统 Python 里装任何东西，不污染 `~/.pub-cache`，也不需要 root：

```sh
source tools/env.sh        # 项目 .venv、钉定的 Flutter SDK、本地 pub 缓存、本地 CMake
nvfku scan                 # 引擎命令行
flutter build linux        # 界面
```

一切都放在三处之一，全都在仓库目录之外：

| 什么 | 在哪 | 为什么放那 |
| --- | --- | --- |
| Python venv | `<项目>/.venv` | 系统 Python 保持不变 |
| Flutter SDK 3.47.5 | `~/.local/opt/flutter` | 不装系统包，版本钉定 |
| pub 缓存 | `<项目>/.pub-cache` | `~/.pub-cache` 保持干净 |
| CMake 4.2.0 | `~/.local/opt/cmake` | Flutter 的 Linux 构建需要 CMake，而 CachyOS 基础安装没有，否则就得 `sudo pacman -S cmake` |
| 引擎状态 | `~/.local/share/nvfku` | 日志、备份、组件缓存 |

系统里没有 CMake 时，`tools/env.sh` 会自动启用本地那份。

想把应用加进桌面菜单、但不想往系统里装任何东西：

```sh
python3 tools/install_desktop.py            # 只写入 ~/.local/share
python3 tools/install_desktop.py --check    # 只报告，不改动
python3 tools/install_desktop.py --uninstall
```

`.deb` 自带菜单入口，但那个指向 `/usr/bin/nvfku-swapper`；源码目录需要自己的，
这个脚本会把入口和图标写进**用户级** XDG 目录，所以不需要 root，`--uninstall`
即可撤销。**移动目录后要重跑**——`Exec` 行里是绝对路径，路径失效后菜单项会
静默地什么都不做。

## 用法

```sh
python -m nvfku scan                        # 装了什么，每个游戏支持什么
python -m nvfku scan --routable             # 只列有路线能服务的游戏
python -m nvfku show 1091500                # 单个游戏，含每条路线的可用性
python -m nvfku plan 1091500 a1             # dry-run：精确列出会改动什么
python -m nvfku install 1091500 a1 --yes    # 实际执行（先写日志）
python -m nvfku providers --resolve         # 组件版本与哈希
python -m nvfku backups                     # 所有写过的日志
python -m nvfku rollback <journal-id>       # 精确撤销其中一条

python -m nvfku model --list                # 所有已知的模型 build 及其摘要
python -m nvfku model --verify <path>       # 本机上某个 DLL 到底是什么
python -m nvfku model --fetch               # 下载实测稳定版，校验摘要
python -m nvfku model --mirror-sync         # 在项目内保留一份已校验的副本

python -m nvfku launch-options 1091500                      # 看 Steam 当前的值
python -m nvfku launch-options 1091500 --route a1 --dry-run  # A1 会写入什么
python -m nvfku launch-options 1091500 --route a1            # 写入（有防护）
python -m nvfku launch-options 1091500 --clear               # 移除该键
```

Flutter 界面以子进程方式驱动同一个引擎，所以界面上显示的 plan 就是命令行会打印的
那个 plan。

### `--json` 契约

`--json` 是界面使用的机器接口，它的约定是严格的：**stdout 只承载一个 JSON 文档，
别无其他。** 失败路径也不例外——而那正是天真实现会漏的地方：

| 情况 | 文档 |
| --- | --- |
| 安装成功 | `{"ok": true, "plan": ..., "result": ...}` |
| 路线受阻 | `{"ok": false, "refused": ..., "blockers": [...], "plan": ...}` |
| 未确认 | `{"ok": false, "needs_confirmation": true, "plan": ...}` |
| 运行时被拒 | `{"ok": false, "refused": ..., "plan": ...}` |
| 找不到游戏 | `{"ok": false, "error": ...}` |

基于同样的理由，`--json` 下引擎自己的分步日志会被重定向到 stderr。这一条是有来历
的：界面初稿曾用正则从人类可读的输出里抠出日志 id，而那正是会静默失效的解析方式。

## 网络

传输层的形态由两条实测事实决定：

- 直连 GitHub 会间歇性超时（`Errno 110`），几秒后又能成功，所以带退避的重试不是
  可选项。
- GitHub 的 release 下载会重定向到 `release-assets.githubusercontent.com`，而在这台
  机器上这个域名**直连不可达**，尽管 `raw.githubusercontent.com` 和 `api.github.com`
  都正常。本地代理能到达它。

所以 `http_get` 会重试，然后**从直连回退到代理**，并在全部失败时报告它试过的每一条
路径。顺序可配置：

```sh
DLSS5_HTTP_PROXY=direct                      # 默认：先直连，代理作回退
DLSS5_HTTP_PROXY=http://127.0.0.1:7897       # 先代理，直连作回退
```

只有传输层面的失败才会重试。从 opener 抛出的 `ValueError` 是代码 bug，会立刻暴露，
而不是被重试成一个缓慢而误导的超时。

## 路线

一共**两条**。它们以"做什么"命名，而不是内部代号——那些代号一度泄漏到界面上，
让一个二选一的决定看起来像三选一。

| | 路线 | 以什么方式挂载 | 需要 | 会写入 |
| --- | --- | --- | --- | --- |
| **ReShade 叠层** | ReShade + dlss5-bridge + addon-dlssnr-linux | 本地 `dxgi.dll` 与 ReShade add-on | D3D11/D3D12、64 位、Proton、NR 模型，**以及它的 ReShade 前置项** | 是（有日志） |
| **OptiScaler 直连** | OptiScaler DLSS-NR | 本地代理 DLL（`dxgi.dll`） | D3D11/D3D12、64 位，游戏本身必须已使用 DLSS | 是（有日志） |

ReShade **不是**第三条路线。它是叠层路线所需的一个组件，因此被规划为该路线的
**嵌套前置项**，它保留自己的安装动作（以及独立的 `nvfku reshade` 命令），但不会
作为同级项出现在路线列表里。把它并列展示，会让一个有两条路线的方案读起来像三个
选项。

Vulkan layer 路线是刻意缺席的；见开头的约束。这里也没有 OpenDLSS-NR 探针：它只会
报告一个原生移植需要什么，而一份无法改变任何事的可行性报告不值得占用那点屏幕。

## 状态

**232 项测试，全部通过。** 已在开发机的真实 Steam 库上验证可用（20 个游戏，
9 个运行时条目被过滤掉）：

- 跨多个库的 Steam 发现，Proton 前缀与工具解析（能区分
  `CachyOS-10.1000-200` 与 `11.0-100`，启动项也随之不同：自定义构建用
  `PROTON_FORCE_NVAPI`，Valve 的用 `PROTON_ENABLE_NVAPI`）
- API/位数检测，包括会让天真分类器出错的情形：Cyberpunk 2077 只导入
  `sl.interposer.dll` 而没有 `d3d12.dll`；霍格沃兹之遗在
  `Phoenix/Binaries/Win64/` 下同时有 0.3 MB 的启动器和 429 MB 的渲染器；ACC 的
  渲染器在 `AC2/Binaries/Win64/` 下
- DLSS NR 模型的发现，并按摘要与实测 build 对照分类
- **A1 与 A2 真实安装**，有日志，回滚在测试中逐字节验证（含符号链接保真与多级
  `mkdir` 链）
- 组件获取带指数退避、钉定大小，以及可选的、对照发布方 `SHA256SUMS` 的校验

安装安全性是**被测试**而不是被声称的：

| 性质 | 测试 |
| --- | --- |
| 路线被拒时不写入任何东西 | `test_nothing_is_written_when_refused` |
| 回滚精确还原目录 | `test_install_then_rollback_restores_the_directory`（A1 与 A2） |
| 重装复用自己记录过的代理位置，而不是装第二个代理 | `test_reinstall_reuses_the_recorded_proxy_name` |
| 已就位的模型不会被复制，也不产生日志条目 | `test_model_already_beside_the_executable_is_not_copied` |
| 用户自己的 `OptiScaler.ini` 键在合并中得以保留 | `test_existing_keys_are_updated_and_others_preserved` |
| Vulkan 游戏被拒绝，并给出名字 | `test_vulkan_game_is_refused` |
| Steam 运行时阻止启动项写入，且文件原封不动 | `test_write_is_refused_while_steam_runs` |
| 启动项值里的转义引号能正确往返 | `test_quotes_and_backslashes_are_escaped` |
| 插入的键使用文件自身的缩进，而非 appid 那一行的 | `test_inserted_key_uses_the_file_s_own_indentation` |
| 损坏的配置文件在**任何备份产生之前**就被拒绝 | `test_a_damaged_file_is_refused_before_any_backup` |

**有防护的 Steam 启动项写入器**（`nvfku launch-options`）。有一个实验
（[docs/experiment-localconfig.md](docs/experiment-localconfig.md)）实测了 Steam 对
`localconfig.vdf` 做了什么，而这个写入器的前置条件就是那些测量结果，而不是防御性的
风格选择：

| 实测结论 | 转化为 |
| --- | --- |
| Steam 会**合并**；它保留了未知的键及其精确缩进 | 文件通过单行手术式编辑修改，绝不重新生成 |
| Steam **关闭**时写入的改动能挺过完整重启 | 该状态下允许写入 |
| Steam **运行**时写入的改动会**被回滚** | 客户端在运行时，写入直接拒绝 |
| 这个文件里还有好友、头像、云同步状态和打包字段 | 只动一行，改动后重新检查大括号配平 |

它会先备份（并校验备份的摘要）、原子写入、重新读取该键，两项检查任一失败就还原备份。
当一台机器有多个账号时，它拒绝猜测该编辑哪一个。

尚未实现：

- 让启动项的改动经过 **Steam Cloud** 往返。云同步是否会在之后的启动中把它回滚，
  尚未测试（见实验文档中列出的局限）。

## 界面

`app/` 是一个 Flutter 桌面应用。它没有第三方依赖：引擎是界面通过 JSON 驱动的子进程，
所以没有 FFI，也没有需要跟某个包版本保持同步的东西。

```
app/lib/
  main.dart              入口
  src/design.dart        字号体系、颜色、动效常量
  src/models.dart        引擎的 JSON 契约，映射为值类型
  src/engine.dart        子进程边界（scan/plan/install/rollback）
  src/l10n.dart          英文与中文，各一张表，并排维护
  src/app.dart           外壳：侧栏、状态栏、视图切换
  src/games_view.dart    海报卡片式的游戏库，带右键菜单
  src/game_sheet.dart    点击卡片打开的模态面板
  src/game_detail.dart   事实、路线、规划、安装、撤销
  src/home_view.dart     拖入文件夹、最近游戏、活动日志
  src/addons_view.dart   组件版本与哈希
  src/history_view.dart  所有日志，可精确回滚
  src/settings_view.dart 持久化设置
  src/about_view.dart    它是什么，以及它不会做什么
  src/launch_options.dart  有防护的 Steam 启动项面板
  src/cover.dart         Steam 封面，带首字母占位
  src/widgets.dart       HoldButton、Disclosure、Notice、StatusPill、FieldRow
docs/ui-design.md        这些设计决策，写在控件之前
```

设计遵循 `docs/ui-design.md`，它应用了 Emil Kowalski 的 `apple-design` 技能
（把 WWDC 的 *Designing Fluid Interfaces* 翻译到 UI 工具包的语境）。其中真正改变了
代码、而不只是装饰的部分：

- **按下即反馈**，而不是松开时才反馈——安装很慢，一个要等进程的按钮读起来像是坏了。
- **操作过程中持续反馈**——安装是逐步流式输出的，而不是结束时才汇报。
- **最多一层半透明**——Flutter 没有 `backdrop-filter`，而该技能警告堆叠半透明表面
  会瓦解可读性，所以状态栏用色调而不是伪玻璃。
- **字距与行高随字号变化**——不存在一个 `letterSpacing` 套用到所有文本。
- **降低动效时给的是更轻的等价物，而不是什么都没有**——时长通过
  `MediaQuery.disableAnimations` 收敛，而状态照常更新。
- **刻意没有动量投影与橡皮筋**——这里没有可甩动、有边界的表面，加一个只会是装饰。

界面从不说"DLSS 5 已安装并正常工作"。它说的是：写入了哪些文件、校验了哪个摘要、
用了哪个 build 的模型，以及还有哪些需要你手动完成。

## 许可

本项目自身的代码以 **WTFPL** 发布。见 [LICENSE](LICENSE)。

**这只覆盖本项目自己的代码。** 发布包里携带的文件中有一个属于 NVIDIA，另有若干组件
是在安装时从各自的发布页获取、遵循各自的许可。
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 完整列出了它们，简述如下：

| | 如何到达你这里 | 它的许可 |
|---|---|---|
| 本项目的引擎与界面 | 源码中 | WTFPL |
| `nvngx_dlssnr.dll`（DLSS NR 模型） | **在发布包里**，已校验摘要 | NVIDIA 私有 |
| `dlss5-bridge` | 安装时从发布方获取 | MIT |
| `addon-dlssnr-linux`、`OptiScaler` | 安装时从发布方获取 | GPL-3.0 |
| ReShade 6.8.0 | 安装时从 reshade.me 获取 | BSD 3-Clause |
| Flutter 运行时 | 在发布包里 | BSD 3-Clause |

**模型是本项目唯一一个没有许可却仍在分发的文件。** 它没有官方下载：DLSS SDK 只提供
头文件和导入库，而 Linux 驱动根本不带 NR 模型。所以发布包会把它打进去，而不是让每个
用户自己去手找 158 MiB——摘要记录在 `RELEASE.json` 中，并由 `tools/package.py` 在
打包前校验。完整的推理与替代方案见 [docs/weights.md](docs/weights.md)。

GPL-3.0 组件是**独立的程序**，从各自的发布页获取，作为数据文件放到游戏旁边。这里没有
任何东西链接它们，也没有任何 GPL 源码被编译进或导入本项目，所以它们的 copyleft 不延伸
到本项目的代码。**如果这一点改变**——如果它们的源码被并入而不只是被调用——本项目的
许可就必须改为 GPL-3.0。

## 打包

```bash
flutter build linux --release      # 在 app/ 下，执行一次
python3 tools/package.py           # 三种格式一起产出到 dist/
```

| 格式 | 体积 | 含模型？ |
|---|---|---|
| `.tar.gz` | 9.5 MiB | 否 |
| `.deb` | 9.5 MiB | **从不** |
| `.AppImage` | 9.6 MiB | 否 |

三种格式，旁边还有一份 `SHA256SUMS`。

**三种都不含 `nvngx_dlssnr.dll`。** 它 158 MiB，属于 NVIDIA，且没有任何许可允许再
分发——所以携带它的包会是 119 MiB，而且不可分发。每种格式都在首次使用时获取并校验它：

```bash
nvfku model --mirror-sync
```

工具会在真正要紧的时刻说明这一点（`RELEASE.json` 记录了它，plan 也把这次获取作为
一个动作列出），而不是在之后用一个"文件缺失"的错误失败。

`--with-model` 用于私有构建时把它打进去。它**拒绝与 `--format deb` 组合**，因为那正是
会造成真正麻烦的组合：一个携带 NVIDIA 私有二进制的 `.deb` 会被任何 Debian 仓库拒绝。

`.deb` 由 `tools/package.py` 直接组装——本机装不了 `dpkg-deb`。一个 `.deb` 就是一个
包含 `debian-binary`、`control.tar.gz` 和 `data.tar.gz` 的 `ar` 归档，而这三种格式
Python 本来就会写。

### 每种包里有什么

```
/usr/lib/nvfku/            载荷（引擎、界面 bundle、文档）
/usr/bin/nvfku-swapper     图形界面
/usr/bin/nvfku             命令行
/usr/share/applications/   桌面入口
/usr/share/icons/          图标
/usr/share/doc/nvfku-swapper/
```

AppImage 把同样的载荷放在其 AppDir 内的 `usr/lib/nvfku` 下，tar 包则放在其根部；
三者使用同一个启动脚本，它会解析自身所在目录，所以整个目录树可以放在任何位置。

`.deb` 的 `RELEASE.json` 里同样带有 `model_source_url` 和 `model_source_note`，
所以一个解开的包仍然会说明模型来自哪里、那个来源是什么。
