# P1 / P2 / P3 整改与复验（2026-10-07）

依据[原复检报告](project-review-2026-10-06.md)完成代码、测试、发布工具和文档整改。原报告保留为历史证据。

## 结论与范围

- 报告列出的 P1/P2/P3 代码与维护改进已实现；新增 **41 项 Python、111 项 Flutter** 回归场景。
- 主线程在最终稳定代码快照上执行：Python 3.14.7 **305/305**、隔离 Python 3.9.25 **305/305**、Flutter **217/217**，全部通过。
- Flutter analyze 无问题，Linux release 构建成功；新 tar/deb/AppImage 三格式候选构建及维护版产物验证全部通过。
- 保留此前未提交修改；未 commit、push、tag、发布或操作真实游戏。新增 CI 只写入配置并本地解析 YAML，未运行远端 Actions。
- 自动化与结构性能证据不能替代干净发行版、桌面 GUI、屏幕阅读器、真实游戏与 GPU 帧时验收；也不构成正式发布批准。

## 逐项对应

| 报告项目 | 实现与验证 |
| --- | --- |
| P1 普通游戏备份损坏仍成功恢复 | [Journal](../engine/nvfku/journal.py) 在替换目标前验证普通 pre-image 大小/SHA256；新链接记录 pre-image 指纹并验证备份/marker 一致性，保留链接目标空格。损坏、截断、缺失时停止恢复，不报告成功，修复备份后可重试。 |
| P1 短写组件缓存被复用 | [providers](../engine/nvfku/providers.py) 使用唯一暂存文件、落盘大小/摘要检查后原子发布；缓存命中与 offline 走同等完整性校验；版本/URL 身份进入缓存键；无 pinned 摘要时使用本地 receipt。 |
| P1 `all --with-model` 绕过 Debian 规则 | [packager](../tools/package.py) 在任何构建前展开格式集合，含 deb 即拒绝模型；直接 Debian 构建入口也拒绝。覆盖完整允许/拒绝组合矩阵，不使用真实模型。 |
| P1 Python 启动/JSON 契约错误逃逸 | [Engine](../app/lib/src/engine.dart) 统一封装 ProcessException，JSON 转换只封装 TypeError/FormatException；嵌套列表即时验证；install malformed 结果转 failed 并关闭流，不使任务永久 running。完整 Shell 启动失败显示可用重试，而非永久 spinner。 |
| P2 设置并发丢更新 | [CLI](../engine/nvfku/__main__.py) 通过 [update_settings](../engine/nvfku/settings.py) 将锁覆盖读→修改→写；[Settings](../app/lib/src/settings_view.dart) 按同一 Engine 串行 UI 意图、普通 Save 和偏好写入，离开页面后仍保存，返回先等队列；提供 pending/success/error，失败保留表单并可重试。 |
| P2 主导航无键盘操作 | [Shell](../app/lib/src/app.dart) 导航使用可聚焦 InkWell、焦点边框、selected/enabled 语义与侧栏焦点顺序；Tab/Enter/Space 实际激活测试通过。 |
| P2 合法 ZIP 内错误模型导致永久重试失败 | [weights](../engine/nvfku/weights.py) 在缺 member、摘要或大小错误时失效坏 ZIP，后续显式重试真正重新获取；模型摘要校验不被绕过。修正大小错误后的诊断，避免删除文件后再 stat。 |
| P2/P3 冷扫描反复遍历 | [Steam](../engine/nvfku/steam.py) 改为单次剪枝 inventory，提供目录/条目/协作时间预算；[model](../engine/nvfku/model.py) 复用 inventory，不再 list(rglob) 全树后取四项；partial 不长期缓存，不把预算耗尽当作确定无模型。 |
| P2 整窗响应式覆盖缺口 | 小于 900 宽使用 Drawer，低高度侧栏可滚动；Games header 与 lazy SliverGrid 同 viewport；长按钮/标题适配。96 组完整 Shell 矩阵无异常且控件可达，不仅测试孤立 GamesView。 |
| P3 封面同步磁盘检查/原图解码 | [Cover](../app/lib/src/cover.dart) build 不再同步 existsSync；errorBuilder 降级；按有限布局×DPR 设置 decode 尺寸，每轴上限 1024，fit 保持比例。保留原无限尺寸约束修复。 |
| P2 发布依赖/追溯/校验清单 | Debian 声明 Python >=3.9 和实测 GLIBC/C++ 最低版本；manifest 记录 build ID、source revision、dirty/content 指纹、runtime。独立产物名拒绝静默覆盖；输出目录锁保护并发部分构建的校验清单合并，旧/坏清单先验证再构建。 |
| P3 冗余 Debian payload 路径 | 去除未参与最终打包的 data_entries 全量读入路径；只构建实际 data_root；Installed-Size 从实际载荷 stat 计算，公开产物回归与三格式验包覆盖布局。未宣称测得打包提速比例。 |
| P3 CI 与文档漂移 | 新增 [CI](../.github/workflows/ci.yml)、[维护版 verifier](../tools/verify_release.py) 和[发布流程](release-workflow.md)。中英 README 不再手写漂移测试计数，修正隔离位置与模型“在发布包里”的过时矛盾；对应文档契约测试同步维护。 |

## 新增测试与 red → green

用户确认的公开 seams：CLI/Journal rollback、组件 fetch、模型 download、CLI settings、Steam scan/model discovery、打包入口/产物、Flutter Engine/Settings/完整 Shell/Cover。所有写入与故障注入仅在临时目录、临时游戏 fixture 或测试 adapter 中执行。

### Python：新增 41 项

- [完整性恢复](../engine/tests/test_integrity_recovery.py)：17 项，覆盖损坏/缺失备份、链接 seal、cache/receipt/版本身份、短写、offline、模型 ZIP 重试，以及 legacy/并发兼容。
- [有预算发现](../engine/tests/test_bounded_discovery.py)：10 项，覆盖单 walk、剪枝、deep Plugins、目录/条目/时间预算、模型复用、partial 重试、ReShade 唯一证据。
- [设置并发](../engine/tests/test_settings_concurrency.py)：1 项真实多进程 CLI，控制读阶段重叠，最终同时保留两个字段。
- [打包](../engine/tests/test_packaging.py)：10 项，覆盖 guard、组合矩阵、拒绝覆盖、来源/ABI、部分重建及并发 SHA256SUMS、坏旧产物/坏清单拒绝。
- [验包 CLI](../engine/tests/test_release_verification.py)：3 项，覆盖 checksum mismatch、合法 checksum 下 archive traversal、required-format gate。

关键缺陷先观察失败，再逐项实现与复跑；并发/legacy 控制组、迁移后的验包安全规则也补验证。Deb 冗余路径清理由已有公开产物回归及真实三格式验包保护，不把它伪称为独立性能基准。

### Flutter：新增 111 项

- [Engine failure](../app/test/engine_failure_test.dart)：4 项，含真实不可启动解释器、malformed JSON/list/install stream。
- [Settings sequence](../app/test/settings_sequence_test.dart)：3 项，覆盖多意图顺序、离开返回等待 pending、失败保留字段与重试。
- [完整 Shell](../app/test/shell_accessibility_test.dart)：101 项，其中 96 项为 `2尺寸 × 2语言 × 2主题 × 2字号 × 6页面`；另覆盖 partial warning、键盘、启动重试、compact Settings 可达。
- [Cover performance](../app/test/cover_performance_test.dart)：3 项，覆盖 build 无同步 stat、有限 decode 参数与真实高分辨率 codec 解码。

矩阵尺寸为 480×700 / 700×400，语言 en/zh，明暗主题，字号 1.3/2；六页面为 Home/Games/Addons/History/Settings/About。早期新增测试中的非唯一 Scrollable finder 已修正，主线程最终单次完整 **217 PASS**，不是把分批结果拼成完整通过。

## 性能证据与边界

- 30 个 Content 子树临时 fixture：冷 scan 的 os.scandir 总访问从 **323 → 3**；Content 内访问从 **305 → 0**。已扫描 Game 的 model.discover 追加游戏树遍历为 0。
- 默认 inventory 预算为 4096 目录、100000 entries、2 秒协作检查。系统 I/O/scandir 不能被这些检查抢占；不是硬超时。策略剪枝目录本身不搜索，外部挂载 fallback 原有预算未扩大。
- partial 会记录 detection_complete/warnings，并在 Games/Card/Detail 明示不完整；NR 缺失但 partial 显示 unknown，不当作确定未找到。
- 实际 Flutter codec fixture：2048×3072 → **200×300**，解码 RGBA 预算 **240000 bytes**。主线程最终 debug probe 约 **12.7 ms**；这不是桌面帧时、GPU profile 或慢挂载大图库体验数据，不报告实机提速百分比。

## 最终执行证据

```bash
# Python 3.14.7，项目 venv
source tools/env.sh
python -m unittest discover -s engine/tests -q
python -m compileall -q engine/nvfku tools
git diff --check

# 隔离 Python 3.9.25，未改系统 Python
PYTHONPATH="$PWD/engine" PYTHONDONTWRITEBYTECODE=1 \
  /home/jackyji/.cache/nvfku-python-checks/runtimes/cpython-3.9.25-linux-x86_64-gnu/bin/python3.9 \
  -m unittest discover -s engine/tests -q

# app 目录，Flutter 3.47.5 / Dart 3.13.4
source ../tools/env.sh
flutter test --no-pub --reporter expanded
flutter analyze --no-pub
flutter build linux --release --no-pub
```

Python 两个运行时分别 **305 PASS**，Python 3.9 compileall 也通过；Flutter 单次 **217 PASS**、analyze clean、release build 成功。新增包 ABI 断言在两个 Python 运行时又定向通过。Python 3.14 suite 仍出现既有 HTTPError 404 清理 ResourceWarning，退出码 0；未把它隐藏或解释成真实网络稳定性证明。

## 新候选与产物验收

新候选位于 [review-fixes-20261007](../dist/review-fixes-20261007/)，build ID 为 `20261007-155545-5972a8a0`。未覆盖或“升级”为已修的历史验收产物，版本仍为 0.1.0，来自未提交工作树而非 clean HEAD。

| 产物 | SHA256 |
| --- | --- |
| [tar.gz](../dist/review-fixes-20261007/nvfku-swapper-0.1.0-20261007-155545-5972a8a0.tar.gz) | `47d9176ce9a5941db9171e852f2909c91dfb1253a3322464402f55b799980ead` |
| [deb](../dist/review-fixes-20261007/nvfku-swapper_0.1.0_20261007-155545-5972a8a0_amd64.deb) | `3a1439597d18c75e76a851d6f21309da271594431e02230488092da3c5f09ca7` |
| [AppImage](../dist/review-fixes-20261007/nvfku-swapper-0.1.0-20261007-155545-5972a8a0-x86_64.AppImage) | `219eac0c7ff69d5700068dad99384c59297368d472cf003246c2d11ddf9c37b2` |

校验清单：[SHA256SUMS](../dist/review-fixes-20261007/SHA256SUMS)。

```bash
python tools/package.py --format all --out dist/review-fixes-20261007
python tools/verify_release.py --out dist/review-fixes-20261007 \
  --require-format tar --require-format deb --require-format appimage
```

全部通过：三格式 checksum、临时提取、所需载荷/无模型/无 pycache、来源字段和同 build ID 一致性、engine 源文件字节、执行权限、隔离 CLI smoke、desktop-file-validate、当前宿主机 ldd。

实测候选 Debian Depends：Python >=3.9、libc6 >=2.34、libstdc++6 >=4.1.1，以及 GTK/blkid/epoxy/glib/libgcc。这不是跨发行版全兼容声明。

source 指纹记录的是打包时的 git-listed worktree 内容（含非忽略 untracked source），不是签名、reproducible build 或当前 clean commit 证明；本报告是打包后生成的验收记录，不属于该候选载荷。验包对当前 engine 源字节做了独立比对。

## CI 与剩余门槛

CI 配置：Python 3.9/3.14 后端回归；Ubuntu 22.04 + Flutter 3.47.5 的测试、analysis、release build；model-free tar/deb 与维护版 verifier smoke。YAML 已本地解析，但未提交、触发或宣称远端 CI 通过。AppImage 外部工具及 native/FUSE 启动仍是独立 local/manual gate；本轮只验证其提取与载荷，不启动 GUI。

剩余限制：

1. 干净目标发行版 GUI、标题栏、屏幕阅读器、chooser/drag-and-drop、native/FUSE AppImage、真实游戏/Steam/渲染兼容，未在本轮执行。
2. 旧组件缓存无 version/URL 身份或无 receipt 时不默默迁移；先重新获取组件，才能可靠 offline。Local receipt 仅证明本地完整性，不认证发布者。
3. Legacy 普通 pre-image 缺 SHA/size 时保留兼容，不能提供同等损坏证明；旧链接没有原始指纹时，相互一致的 backup/marker 不足以检测二者同时被改。
4. receipt/target 为两步原子替换，无 fsync；journal 持续写失败、undo/save 间退出、legacy unsealed 与外部 ReShade 写入仍可能需要人工恢复。没有断电持久性保证。
5. 模型 ZIP 的并发 stream 未扩展成全新的并发下载模块；当前整改保证坏 ZIP 失效与显式重试，不扩大既有并发契约。

正式发布仍须完成授权范围内的人工验收；推荐使用受维护的 Python 版本，3.9 是已验证的兼容性下限，不是安全维护承诺。
