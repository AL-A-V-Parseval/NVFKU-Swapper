# 发布阻断项修复与复验记录

## 当前结论

2026-10-06：原验收中的 B1、B2 两项已复现回滚缺陷及相关失败 UI 状态问题已修复，自动化复验通过。**这不是正式发布批准**：目标发行版/宿主 Python 兼容性、人工 GUI/Steam/游戏渲染验收仍待完成。

原始发现保存在[修复前验收报告](</run/media/jackyji/Documents/DLSS5-swapper-linux/docs/release-acceptance-2026-10-06.md>)；其旧产物不是此次修复后的候选包。

## 修复内容

1. **半回滚阻止重装。** [Journal](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/journal.py#L89-L138>) 新增向后兼容的 `rollback_started`，保留 `finished` 的历史含义；[rollback](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/journal.py#L525-L566>) 在任何 undo 前先保存恢复意图，保存失败则不继续修改游戏；[A1/A2 事务门控](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/route/transaction.py#L65-L81>) 在恢复完成前拒绝新安装。旧日志中的逐操作 rollback_done 也用于识别已经开始的回滚。
2. **index 不再破坏检查点。** [manifest 保存](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/nvfku/journal.py#L212-L222>) 仍是权威状态；可选 index 的文件系统或内容故障不再抹掉已保存的恢复事实。操作 undo 和检查点保存分开处理；临时 manifest 保存失败时保留已经成功 undo 的内存检查点，再尝试最终保存，不把成功恢复误标成 undo 失败。
3. **失败回滚也使 UI 状态失效。** [Engine.rollback](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/engine.dart#L291-L324>) 在失败、拒绝、异常报告和进程启动失败后保守刷新 revision；只使对应日志的安装回执失效，保留失败信息，不再显示旧绿色成功。
4. **失败/重试的错误生命周期。** [InstallTask](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/install_task.dart#L10-L76>) 记录被失效回执的日志关联；该日志重试成功后清除旧错误，但不清除无关游戏回执或后续新安装的错误。
5. **恢复中状态与错误提示。** [JournalEntry](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/models.dart>) 将 rollback_started 的记录排除出 live；首页/历史显示未完成而非生效/完成。[History](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/lib/src/history_view.dart#L76-L135>) 将读取错误与回滚错误分离，异步列表刷新不再擦除回滚失败提示，恢复条目仍可见。

## 隔离回归测试

新增 4 项 Python 测试和 11 项 Flutter 测试。主要缺陷经过失败→修复→通过验证；旧格式兼容性作为额外回归检查。所有模拟游戏、配置及 CLI 可执行测试夹具均限定在临时目录。

- [CLI 安装/回滚测试](</run/media/jackyji/Documents/DLSS5-swapper-linux/engine/tests/test_install.py#L587-L725>)：半回滚拒绝重装、恢复成功后解锁；旧格式部分回滚仍被识别；index 路径被目录占用也不影响正常回滚及幂等重试；注入一次文件系统 manifest 替换故障后重试仍能恢复 ORIGINAL 字节。
- [Flutter Engine 测试](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/test/install_task_test.dart>)：使用真实隔离 mock CLI 进程验证部分失败、无操作拒绝、损坏 JSON、错误成功报告、进程启动失败、匹配回执失效、重试清错及新安装错误保护。
- [Widget 测试](</run/media/jackyji/Documents/DLSS5-swapper-linux/app/test/ui_render_test.dart>)：恢复中日志不再显示为 complete/live；异步 backups 响应不擦除 History 失败信息。

## 完整复验结果

| 项目 | 结果 |
| --- | --- |
| Python 完整测试 | **264 项通过** |
| Flutter 完整测试 | **106 项通过** |
| Flutter analyze | No issues found |
| Python compileall / git diff --check | 通过 |
| Linux release 新构建 | 通过 |
| tar.gz、deb、AppImage 重新打包 | 三种均通过，不含专有模型 |
| 新包 SHA256、引擎源文件逐字节对照 | 全部通过 |
| 解包后隔离 CLI 冒烟、可执行权限、desktop entry | 全部通过 |
| 本机动态链接 | 无缺失依赖；GUI 最高 GLIBC 符号仍为 2.34 |

新候选目录：[修复后本地验收产物](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-rollback-fix/>)。

- [校验清单](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-rollback-fix/SHA256SUMS>)。
- [产物检查脚本](</run/media/jackyji/Documents/DLSS5-swapper-linux/dist/acceptance-20261006-rollback-fix/verify_acceptance.py>)。
- tar.gz SHA256：`e6196d7a0f196e00991469eddca2531f5565b8fdf9a86cbd5157ebaa673f1a06`。
- deb SHA256：`adee16aa085b5ae4ca0063a74c7ce7058bb66e7dfb952403c683a2a88b5306c2`。
- AppImage SHA256：`94f6b2b245cdee9ba39680e32eaea41fa48da6751ecb18d15962d2b41713f036`。

## 明确保留的边界

- 若 undo 已发生后，逐操作检查点和最终 manifest 保存**均持续失败**，或进程在 undo 与保存之间被终止，重新加载时仍可能因 post-image 不匹配而需要人工恢复。已保存的恢复意图会阻止 A1/A2 重装，不能据此宣称自动恢复所有故障。
- 文件写入使用原子替换但没有文件/目录 fsync；**不保证断电持久性，不宣称 crash-proof**。
- 旧式未封存操作与 ReShade 外部程序写入/事务保护仍是独立残余风险，本轮没有扩展这部分保障。
- 宿主 Python 最低版本约束、GLIBC 2.34 目标环境、AppImage 原生挂载启动与干净 Debian/Ubuntu 安装尚未完成正式兼容性验收。
- 人工 GUI、真实 Steam 门控与测试游戏副本渲染验收仍待用户确认；未操作真实游戏，也没有发布。

本轮保留全部已有改动；未提交、推送、打标签或上传候选包。
