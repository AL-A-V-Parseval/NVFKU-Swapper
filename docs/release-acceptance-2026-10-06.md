# NVFKU-Swapper 发布前验收

> 本文是修复前验收快照。B1/B2 后续修复与最新测试/候选包结果见[修复复验记录](</run/media/jackyji/Documents/DLSS5-swapper-linux/docs/rollback-fix-verification-2026-10-06.md>)。下列旧包保留用于追溯，不包含后续修复；旧缺陷复现脚本断言修复前行为，不应作为当前安全通过标准。

## 原始验收结论（修复前）：NO-GO（暂不正式发布）

当前工作区可以通过已有自动化测试、静态检查、Linux release 构建与三种打包检查，但安全验收复现了两项回滚缺陷。必须修复并增加回归测试后重新验收。测试全绿不代表这些未覆盖场景安全。

- 验收日期：2026-10-06（UTC）。
- 基线 HEAD：`cacfe77c223ba43059932bbb932c2c5aeb526428`；验收对象包含现有未提交和未跟踪源文件，不是该提交的干净构建。
- 工具链：项目 Python 3.14.7；固定 Flutter SDK 3.47.5；Linux x86_64 本机。
- 未提交、推送、打标签、上传发布、安装系统软件或操作真实游戏。
- 本轮没有修改应用/引擎源代码；只构建验收产物、编写隔离检查脚本和本报告。

## 已通过

| 验收项 | 结果与边界 |
| --- | --- |
| Python 完整测试 | 260 项通过；使用项目虚拟环境 |
| Flutter 完整测试 | 95 项通过；包含中英文、明暗主题、窄布局、放大文字、减弱动画、键盘卡片和状态刷新 |
| Flutter 静态分析 | No issues found |
| Python compileall | 引擎与工具脚本通过 |
| git diff --check | 通过 |
| Linux release 构建 | 成功产生新构建，而非仅检查旧 bundle |
| tar.gz / deb / AppImage | 三种无模型包均构建成功 |
| 产物 SHA256 | 三项均与校验清单一致 |
| 包内源代码 | 包内全部引擎 Python 源文件与当前工作区逐字节一致，包含新事务模块 |
| 打包卫生 | 必要引擎、GUI、启动器、授权和第三方声明齐全；未携带模型 DLL 或 Python 字节码缓存 |
| 启动器 CLI 冒烟 | 三种包分别临时解包，从无关工作目录运行；隔离 HOME/XDG；version、JSON settings、空 backups、缺失 journal 的失败 JSON 均符合预期 |
| desktop entry | deb 和 AppImage 的 desktop-file-validate 通过 |
| 本机动态依赖 | GUI 与 bundle 内两项共享库 ldd 均可解析，无 not found |

测试有一条 `HTTPError 404` 对象清理的 ResourceWarning，不影响退出码；不能将其理解为已验证外网下载稳定性。

## 发布阻断项

### B1：部分回滚后，新安装仍能通过事务检查（高优先级）

- [transaction.py:72–73](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/route/transaction.py#L72-L73>) 只阻断 `finished=False && rolled_back=False` 的日志。
- 已完成的安装回滚中途失败，仍保留 `finished=True && rolled_back=False`；已逆向完成的操作不会自动恢复回滚前状态。
- 临时目录复现：先写代理文件，再记录并封存路由状态；结束安装；模拟用户修改代理；回滚先删除路由状态，再因代理 post-image 不匹配停止。
- 实测：`rollback_ok=false`，`finished=true`，`rolled_back=false`，`rollback_done=[false,true]`，路由状态已不存在，用户修改仍保留；同游戏的 `@locked_install` 哨兵仍返回 `ALLOWED`。
- 风险：新安装可覆盖尚未解决的半回滚状态，增加恢复难度。不是旧式未封存日志的既有风险。
- 复验门槛：部分回滚必须显式标记为待恢复；新安装拒绝进入；成功回滚/明确恢复后才解锁。

### B2：可选 index 写入失败破坏已完成 undo 的检查点（高优先级）

- [journal.py:206–211](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/journal.py#L206-L211>) 先写 manifest，再更新 index。
- [journal.py:529–535](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/journal.py#L529-L535>) 将 undo 和保存检查点放在同一异常处理内；保存 index 失败时把已经成功恢复的操作重新标为 `rollback_done=False`。
- 临时目录复现：将 ORIGINAL 替换为 INSTALLED；第一次回滚检查点保存时，仅注入一次 index 更新 OSError。
- 实测：文件已恢复 ORIGINAL，第一次报告失败，最终 manifest 的检查点却是 false；再次回滚因恢复后的 ORIGINAL 不匹配 INSTALLED post-image，再次失败。
- 风险：暂时性缓存写入错误可让本应可重试的回滚无法正常完成。不是断电窗口假设，而是同步异常的确定复现。
- 复验门槛：持久化成功的 undo 检查点不能被可选 index 失败抹掉；注入失败后重试必须完成且保持 ORIGINAL 字节。

## 相关状态一致性问题（代码审查证据，待补回归）

[Engine.rollback:296–307](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/engine.dart#L296-L307>) 在失败报告时直接抛错，仅成功时清理安装回执和通知 revision。B1 场景下部分文件/状态已经变化，UI 却不会从该路径刷新，保留的安装成功回执也可能继续显示。修复 B1/B2 时应同步验证失败后的重新读取和“不再保证完整安装”的呈现，而非只测试成功回滚。

## 兼容性与尚未执行的人工验收

- ELF 实测 GUI 需要的最高 GLIBC 符号为 **2.34**；Flutter GTK 库为 2.18。不能把此包宣称为兼容所有 Linux，尤其不能承诺 glibc 2.31 系统直接运行。
- 包使用宿主 `python3`，没有自带 Python。代码至少使用 Python 3.9 API/语法；deb 的 Depends 仍只写 `python3`，没有最低版本约束。应声明支持的发行版/Python版本并在对应干净系统复验。
- 本机动态链接通过不代表目标发行版安装验收通过；未在 Debian/Ubuntu 干净环境安装 deb，也未验证 AppImage FUSE 挂载启动。
- CLI 冒烟验证了 AppImage 提取后内容，不等同于 AppImage 原生挂载运行验证。
- 未做新 release GUI 的人工视觉检查、真实 Steam 开关门控、文件夹选择器、拖放、窗口缩放、真实游戏渲染或驱动兼容性验收。
- 未执行真实游戏下载/安装/回滚；后续应由用户在可恢复的测试游戏副本上检查 A1/ReShade/A2 行为。
- 旧式未封存 journal 操作和 ReShade 外部程序写入仍不具备本轮新 post-image 保护的同等保障；需要明确发布说明，不得宣称所有外部改动都有安全回滚保护。
- Steam 或状态目录经符号链接的真实布局未人工复验；新外部配置保护会拒绝符号链接路径。

## 本地验收产物（不可作为已批准发布包）

目录：[验收产物目录](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-1130/>)。

| 文件 | SHA256 |
| --- | --- |
| [tar.gz](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-1130/nvfku-swapper-0.1.0-20261006.tar.gz>) | `f36f954f020cdf44849638cfa8a35c9ab0e66d3cbda33b7ef455adcdac3ecdcb` |
| [deb](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-1130/nvfku-swapper_0.1.0_20261006_amd64.deb>) | `b995102410a5b4ff8f689c23705cd193b7223556d7e2cdc5294d9e438c8ac7b5` |
| [AppImage](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-1130/nvfku-swapper-0.1.0-20261006-x86_64.AppImage>) | `fec66154feeb32092d6bffd9089b2edefd185cdfbfd0c564b9c7e60a4a29989b` |

- [校验清单](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-1130/SHA256SUMS>)。
- [产物验收脚本](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-1130/verify_acceptance.py>)：运行输出通过。
- [缺陷复现脚本](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-1130/reproduce_rollback_risks.py>)：断言的是当前缺陷确实存在，退出 0 **不代表安全通过**。全部操作限于 TemporaryDirectory。

## 复验命令

```bash
source tools/env.sh
python -m unittest discover -s engine/tests -q
python -m compileall -q engine/nvfku tools
python dist/acceptance-20261006-1130/verify_acceptance.py
python dist/acceptance-20261006-1130/reproduce_rollback_risks.py
# 在 app/ 工作目录执行（不发布）：
flutter test --no-pub --reporter expanded
flutter analyze --no-pub
flutter build linux --release --no-pub
```

下一步：优先修复 B1/B2 与失败后的 UI 状态刷新，加入公共 CLI/Engine 回归测试，然后重新构建验收包；确定支持环境、完成上述人工门槛后再批准正式发布。
