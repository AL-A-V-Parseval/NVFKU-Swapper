# 项目复检与优化建议（2026-10-06）

> 历史复检记录：本报告列出的 P1/P2/P3 已进行后续整改与自动化复验，当前实现、测试结果、新候选及残余限制见[整改复验记录](project-review-fixes-2026-10-07.md)。保留下文原始发现，不将其当作当前未修状态。

## 范围与结论

检查当前工作树（含此前未提交修改），覆盖 Python 后端、Flutter 前端、发布工具及测试覆盖。本轮仅审查与临时目录隔离验证，未修改功能、提交、发布或操作真实游戏。没有重新构建安装包，也没有进行桌面 GUI 人工验收。

现有回滚意图、防半回滚重装、index 容错、失败回执失效、异步刷新 generation guard、游戏卡片键盘操作及窄工具栏修复仍在；不将这些已修问题再次计为发现。测试全部通过不代表下面这些未覆盖场景安全。

### 本轮自动化结果

- Python unittest：264 项通过。
- Flutter test：106 项通过。
- Flutter analyze：无问题。
- Python compileall 与 git diff --check：通过。
- Python suite 仍有 HTTPError 404 清理的 ResourceWarning，退出码为 0；不把它解释为网络稳定性验证。

## 优先修复项

优先级：P1 应优先修复；P2 正常迭代；P3 性能与维护优化。以下不是对恶意修改本地状态文件的完整安全审计。

### 1. P1：普通游戏文件的备份损坏后，回滚仍报告成功

**已隔离复现。** [journal.py:663–685](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/journal.py#L663-L685>) 恢复普通备份时，仅在 `op.external` 为真时检查 pre-image SHA256；普通游戏文件虽记录 SHA256，却不验证它。符号链接恢复分支也需要独立审视备份/marker 一致性。

临时 fixture：原文件 `ORIGINAL` → 安装 `INSTALLED` → 将备份改为 `CORRUPTED` → 调用公开 `rollback_journal`。实测目标内容成为 `CORRUPTED`，`report.ok=True` 且 manifest 的 `rolled_back=True`。未改任何真实游戏。

**建议：** 恢复前统一验证所有普通 pre-image 的摘要和大小，验证通过后才替换目标；链接使用明确的链接指纹，不套用普通文件摘要。失败时保留当前目标与待恢复状态，不显示成功。

**新增测试：** 普通备份截断、内容变更、丢失、符号链接 marker 不一致；从公开 rollback seam 验证拒绝、文件不被破坏、重试状态正确。

### 2. P1：组件缓存短写后，被当作有效文件复用

**已隔离复现，路线传播经代码核实。** [providers.py:313–338](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/providers.py#L313-L338>) 对无 pinned SHA256 的缓存无条件返回，跳过新下载时的 size 检查；保存采用直接 `write_bytes`，故磁盘满或进程中断可留下短文件。[PINNED 定义](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/providers.py#L65-L105>) 中三个实际 A1 二进制均没有 pinned SHA256。

隔离故障注入：写入 1 字节后抛 ENOSPC，再次 `fetch` 接受该 1 字节 addon（预期 242176），不调用下载。A1 在上游 SHA256SUMS 不可用时继续执行并称“sizes still checked”，但缓存路径并未检查大小，见 [A1 获取与校验逻辑](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/route/a1_bridge.py#L537-L558>)。实际游戏安装未执行。

**建议：** 临时文件下载、校验后原子替换；缓存命中同样验 size/digest；缓存键包含版本或 URL 身份。无上游摘要时准确显示验证等级，不把“未提供摘要”当作已验证。

**新增测试：** 短写后重试、同名版本变化、摘要缺失/不可用、并发下载，覆盖 `--skip-download` 的同等完整性规则。

### 3. P1：`--format all --with-model` 绕过 `.deb` 模型禁打包规则

**已用 mock 构建器隔离复现，没有使用或打包真实模型。** [package.py:589–616](</run/media/jackyji/Documents/DLSS5-swapper-linux/tools/package.py#L589-L616>) 只在 `args.format == 'deb'` 时拒绝，但 `all` 同样包含 deb，并将 `with_model=True` 传入 `build_deb`。[payload_tree](</run/media/jackyji/Documents/DLSS5-swapper-linux/tools/package.py#L196-L199>) 会据此复制模型。

**建议：** 先展开 wanted 格式，若含 deb 且 with-model 则在任何产物生成前拒绝；`build_deb` 自身也守住该不变量。此项判断依据项目自身声明的发行规则，不是额外法律结论。

**新增测试：** `deb/all × with-model` 组合矩阵；拒绝时没有半成品；直接调用 `build_deb` 不能绕过。

### 4. P1：Python 启动失败时，前端无法进入统一错误/重试状态

**公开 Engine 调用已隔离复现；Shell busy 行为是代码控制流推导，未经 GUI 验证。** 临时 Flutter 测试中使用不存在的 pythonOverride，真实 `Engine.scan()` 与 `Engine.version()` 均抛出 ProcessException 而非 EngineException，2/2 项验证通过（独立于现有 106 项测试）。 [engine.dart:166–178](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/engine.dart#L166-L178>) 与 [version:232–238](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/engine.dart#L232-L238>) 直接调用 `Process.run`，不封装 `ProcessException`；[Shell 扫描:300–345](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/app.dart#L300-L345>) 只捕获 `EngineException`。不存在或不可执行的 Python、无效工作目录可能令错误逃逸，busy 无法被该 catch 重置。

**建议：** 将进程启动异常统一转换为 EngineException；JSON 契约的类型/结构错误也应提供可显示的诊断，而非强制 cast 异常。不要笼统捕获并吞掉所有程序错误。长时间查询另行设计超时，不能以取消 UI 的方式杀掉有写操作的安装任务。

**新增测试：** `version/scan/settings/plan` 启动失败；Shell 能显示错误并重试；malformed document shape 不制造永久 spinner。现有 rollback 启动失败测试不能替代这些场景。

### 5. P2：快速切换偏好与普通保存会丢更新

**后端机制已临时目录定序复现；真实 GUI 并发发生率未测。** [settings_view.dart:91–104](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/settings_view.dart#L91-L104>)、[两个 picker](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/settings_view.dart#L222-L250>) 每次选择发起独立异步写；[CLI settings](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/__main__.py#L656-L686>) 是 load → 修改 → 全量 save，无跨进程读改写锁。

隔离复现：两个快照先后读取默认值，A 写 Steam root、B 写主题，A/B 依次保存后 Steam root 被旧快照清空；新 light 快照先存、旧 dark 后存，最终 dark。证明 lost-update 机制，不声称每次快速点击都会触发。

**建议：** 前端串行/合并最新偏好意图，并提供待保存、成功、失败反馈；后端将锁覆盖整个读改写过程，以保护多个 GUI/CLI 调用。仅后端加锁不保证旧 UI 意图不会最后执行。

**新增测试：** 人为逆序完成、theme/language 连续更改、普通 Save 与偏好更新并行、失败后重试。

### 6. P2：主导航没有完整键盘交互

**代码证据，未进行桌面屏幕阅读器验收。** [app.dart:651–701](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/app.dart#L651-L701>) 的 `_NavItem` 使用 MouseRegion + GestureDetector，没有可聚焦激活行为；selected 仅改变视觉颜色/字重，没有明确 selected semantics。游戏卡片的键盘修复没有覆盖主导航。

**建议：** 使用 NavigationRail/ListTile/InkWell 等已有控件或完整 Focus/Actions，并补焦点样式与选中语义。确认整条“导航 → 游戏 → 计划 → 确认 → 返回”路径无需鼠标可完成。

**新增测试：** 全 Shell 的 Tab/Enter/Space、禁用项、selected semantics、焦点不被对话框遮挡。

### 7. P2：模型 ZIP 内容错误时，重试持续复用坏 ZIP

**已隔离复现，不是摘要绕过。** [weights.py:229–245](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/weights.py#L229-L245>) 总是复用非空缓存 ZIP；[extract:295–325](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/weights.py#L295-L325>) 对 BadZipFile 删除 ZIP，但 DLL 摘要错误仅删除 DLL，缺 member 也不清 ZIP。

合法 ZIP 内含错误 DLL，连续两次 download 均拒绝，坏 ZIP 留存且 `_stream` 调用为 0。安全校验仍有效，但“重试”无法自愈。

**建议：** 将已确认无效的 ZIP 隔离/失效，并允许一次受控重新拉取；保留失败原因，避免无限重试上游错误文件。

**新增测试：** 首次下载坏但格式合法的 ZIP → 第二次源已修复 → 真正重新下载并验证通过；覆盖缺 member。

## 性能、发布与维护优化

### P2/P3：冷扫描重复遍历整个游戏树

[steam.py:520–544](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/steam.py#L520-L544>) 五次 rglob；[model.py:202–211](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/model.py#L202-L211>) 又执行 `list(rglob(...))[:4]`，先走完整棵树，事后过滤并非剪枝。隔离 30 个 Content 子目录空树中，记录到 steam 检测 305 次 Content 目录枚举，model 又遍历 61 个；尚无真实大库耗时基准，不报告百分比提速。

建议统一一次按名称集合匹配、可剪枝的 walk，并设置访问/时间预算；复用已有扫描证据。先加冷扫描目录访问量基准，而非只测试 warm cache 次数。不要仅换成 islice：无匹配时仍可能全树遍历。

### P2：完整窗口响应式验收不足

真实 Shell 固定侧栏；现有窄工具栏测试主要验证孤立 GamesView，不能证明整窗可用。建议明确最小窗口策略或折叠侧栏，侧栏低高度可滚动；测完整 Shell 在 480×700、700×400、中文/英文、明暗、1.3/2 倍字号下无异常且关键控件可达。此项是覆盖缺口，未声称已经 GUI 复现溢出。

### P3：封面解码与 UI 线程磁盘访问

[cover.dart:45–61](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/cover.dart#L45-L61>) 在 build 中同步 existsSync，Image.file 未限定 decode 尺寸。建议使用 errorBuilder 自然降级，按有限布局约束 × DPR 限制 cacheWidth/cacheHeight；保留此前无限尺寸修复。已有 lazy GridView，不建议改为全量加载。高分辨率封面与慢挂载的实际卡顿需要 profile 验证。

### P2：发布依赖与产物追溯

[package.py:60](</run/media/jackyji/Documents/DLSS5-swapper-linux/tools/package.py#L60>) 的 Debian Depends 未声明 Python 最低版本或当前 glibc 下限。本轮 readelf 再确认当前 runner 需要 GLIBC_2.34；后端使用 Python 3.9 的 removeprefix/is_relative_to。建议明确支持发行版/最低版本，用 ELF 依赖工具生成约束，或在目标最低基线上构建。不能因为开发机可运行而声称兼容全部 Linux。

[SHA256SUMS 写入](</run/media/jackyji/Documents/DLSS5-swapper-linux/tools/package.py#L626-L630>) 仅保留当次 built 清单；隔离 mock 复现证明同目录只重建 tar 会丢掉旧 deb/AppImage 的校验条目。建议一次构建一个独立 release 目录或安全合并仍存在的产物条目。文件名仅版本+日期，同日构建还可能覆盖；增加构建身份与覆盖策略。

[RELEASE 元数据](</run/media/jackyji/Documents/DLSS5-swapper-linux/tools/package.py#L525-L566>) 缺 source revision/dirty 身份；补可追溯信息。Deb 构建中 [data_entries](</run/media/jackyji/Documents/DLSS5-swapper-linux/tools/package.py#L328-L373>) 已读入全部文件，但最终打包另外的 data_root，属于重复 I/O/维护路径；建议删冗余实现，统一 payload 与格式适配测试。暂未测量内存或打包提速。

### P3：持续集成与文档漂移

当前仓库未发现 `.github` 工作流；建议补与实际托管平台匹配的自动检查、干净 Linux 构建及产物 smoke gate。发布验证脚本目前位于某次 dist 目录，建议移入长期维护的工具/测试入口，避免依赖历史验收目录。

[README 状态](</run/media/jackyji/Documents/DLSS5-swapper-linux/README.md#L175-L177>) 仍写 232 tests，与实际 264 不一致；Isolation 也把项目内 `.venv/.pub-cache` 称为仓库树外。建议不在多个位置手写频繁变化的测试数量，或由 CI 更新。

## 建议实施顺序

1. 游戏备份完整性 + 组件缓存原子写/验证，各自先写故障回归。
2. 打包禁模型矩阵 + Engine 错误类型统一。
3. 偏好串行与后端锁 + 主导航键盘/语义 + 完整 Shell 尺寸测试。
4. 坏 ZIP 自愈 + 单次剪枝扫描 + 封面 profile。
5. 发行版基线、持续集成、可追溯构建与文档清理。

保持现有公开调用 seam，不为重构额外堆薄包装层；将完整性、错误语义和并发顺序集中在负责它们的模块内部，避免每个 UI/route 调用者自行补判断。

此前已记录的持续 manifest 写失败、undo/save 间进程退出、缺 fsync、legacy unsealed 操作与外部 ReShade 写入仍是独立限制。本轮不宣称断电可恢复，也不构成正式发布批准。
