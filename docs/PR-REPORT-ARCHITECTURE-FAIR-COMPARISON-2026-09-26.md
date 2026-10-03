# PR 报告：新旧架构公平性能对照（基础比较完成 / 最终候选发布验收未完成）

## 当前结论摘要（2026-09-26 收口；≤25 行）

1. **建议保留新架构作为后续主线**；但**不是**"任意场景绝对丝滑 / 无泄漏 / 三平台可发布"的证明。
2. **24 轮最新动作机制**（move1/move3/switch1/flight1/coll3 × B N N B）与历史同路径 idle 证据齐备：机制门通过、逐帧截尾达标。
3. **最终候选累计全量已验并全绿**：`exports/fair-movefix-20260926-a` 一次全量 pytest **rc=0 / 3638 passed / 11 skipped / 269 warnings / 380.10 s**（0 FAILED、0 ERROR）；**ruff 亦绿**（`All checks passed!`）。
4. **真人手动一次**（新侧 1 轮、180 样本 / 89.5 s）：**未主观发现明显碰撞故障**；但用户报告**点开 agent 内容时短暂降帧后自行恢复**，且**停手时刻未采、采样分段不精确** ⇒ 不能归因、不能证明无问题。
5. **两侧各有一次约 601 s 描述性运行**（旧 `soak-base-3p-20260926-l`、新 `soak-new-3p-20260926-m`）：**均 `rc=2`，原因是工具层误报，非产品失败**；两者**不构成有效 ABBA、不给胜负排名**。
6. **长稳仍非通过**：旧侧末段仍有帧续播记录；新侧**记录到 max 交付 gap 240–250 ms**；两侧 **Recorder 逐相位累计保留帧列表 ⇒ 内存与取证结构混杂**，**既不能称"无泄漏"，也不能称"产品已泄漏"**。
7. **未验**：GPU / present、Linux/macOS 行为、极限压力、最终候选高帧接入；**高帧只有历史侧结果**（在旧新侧谱系上跑过），**不默认换高帧或低清**。
8. **插件化**：用户已把范围收为**只判断新旧谁更适合**——已答**新统一宿主更适合**，高风险能力走 **worker 风险隔离**；**无完整方案任务**。

> 本文按"追加"方式演进，下文各节一律**保留其撰写时的状态**；口径冲突以本摘要与本报告末尾章节为准（各历史节内已有指向末尾的指针）。
> **证据索引**：`.scratch/arch-ab/closeout-20260926-a/EVIDENCE-INDEX.md`（逐轮副表与单一原始引用入口）、`.scratch/arch-ab/closeout-20260926-a/MATERIAL-ATTRIBUTION.md`（素材归因）；本节只给指针，不复制 scratch 内容。

> **基线**：`ebf971ecf4df571701c8ad62294a44bf66df4362`（工作树 HEAD；19 项 WIP 未提交，见第二节）
> **分支**：`feature/single-overlay-window`（`git branch --show-current` 实测）；**未创建 PR**；本轮无 git mutation
> **日期**：2026-09-26　**证据截至**：2026-09-26 18:13（后续只在文末**追加**验收段，不覆盖本文结论）
> **范围**：**产品代码 0 行改动**。本文是性能对照的汇总报告，不是功能 PR。
> **关联**：[`PR-REPORT-SINGLE-OVERLAY-WINDOW-2026-09-24.md`](PR-REPORT-SINGLE-OVERLAY-WINDOW-2026-09-24.md)（新架构产品化总报告）、
> [`PR-REPORT-PHASE4-4-RETIRE-MULTIPROCESS-2026-09-23.md`](PR-REPORT-PHASE4-4-RETIRE-MULTIPROCESS-2026-09-23.md)（多进程层退役）、
> 原始证据索引与逐轮副表见 `.scratch/arch-ab/closeout-20260926-a/EVIDENCE-INDEX.md` 与 `MATERIAL-ATTRIBUTION.md`。

## 零、一句话大白话

**新版值得保留**——三宠 idle 的资源降低和切换就绪度，是这次拿到的最强、最一致的两组证据；
但它**不是**"全面高帧、极限压力、可发布"的证明：单宠 idle 整树 CPU 基本持平、内存只是略有出入，
高帧与极限压力都没验成；最终候选的累计回归在两次环境安全门受阻后**已于 §十 补跑通过（3638 passed / 11 skipped / 0 failed）**，长稳仍有缺口。

---

## 一、核心特性

把「旧真多进程架构」与「新单窗口 overlay 架构」放在同一台机器、同一套夹具下逐场景对照，
给出**可追溯、可复跑、明确划界**的性能结论，并明确**哪些还没验**。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 冻结可比双方 | 旧 = `exports/base-2786c15`（commit `2786c15`，真多进程）；新 = `exports/fair-movefix-20260926-a`（`pet_tree_sha256=b17a5c3bc90e7851ff50d329308dc322608cf1ecaa44455cfda933da04397b57`，新侧显式 `--frameseq on`） |
| 2 | 逐场景对照 | idle 单/三宠、MOVE 单/三宠、switch 单/三宠、flight、collision，均 B N N B 反序配对 |
| 3 | 三个行为修复有机器证据 | IDLE 截尾（圈末解码器重启）、MOVE 截尾（末帧 238/239/240 交付）、音效 warm。**证据范围各自受限**，见第三、四节 |
| 4 | 明确的未验清单 | present / GPU / 极限压力 / 最终候选累计回归 / 有界长稳，逐条标注，不包装 |

**红线 / 不变量**：本文不改任何产品语义；两个导出包、既有 `results/`、旧标签、冻结台账**只读**，无删样、无覆盖、无 git mutation。

## 二、修改文件说明

**本轮为整理工作、未提交，对产品代码零改动**——没有改 `pet/**`、没有改测试、没有改配置。
工作树现存 19 项 WIP 是**既有**未提交改动（本轮只读它们、按 19 项逐文件清单核对身份），逐文件短列如下（`git diff --numstat`）：

| 文件 | 增删 | 本轮角色 |
|---|---|---|
| `pet/sprite_behavior.py` | +471 / −17 | **IDLE / MOVE / ACTS 三处时序截尾修复的载体**（音效 warm 不在此文件）；包内 sha = 工作树 `9e292407…044ab` |
| `pet/frameseq_provision.py` | +1005 / −72 | 帧序列供给；本轮只读 |
| `pet/library.py` | +205 / −31 | movie 库/映射；本轮只读 |
| `pet/overlay_shell.py` | +51 / −0 | overlay 拓扑 + **音效 warm（启动期预热 winmm 句柄）修复的载体**；本轮只读 |
| `pet/island_bridge.py` | +41 / −6 | 岛几何桥；本轮只读 |
| `pet/slot_manager.py` | +17 / −5 | 槽位；本轮只读 |
| `pet/app.py` | +9 / −0 | 应用层；本轮只读 |
| `tools/convert_frameseq.py` | +8 / −4 | 帧序列转换器；本轮只读 |
| `tests/test_frameseq_provision.py` | +1726 / −87 | 既有测试 |
| `tests/test_island_bridge_velocity.py` | +305 / −12 | 既有测试 |
| `tests/test_overlay_shell.py` | +136 / −2 | 既有测试 |
| `tests/test_frameseq_clip.py` | +41 / −3 | 既有测试 |
| `tests/test_overlay_instance_gate.py` | +45 / −4 | 既有测试 |
| `tests/test_session_end_ffmpeg_guard.py` | +52 / −2 | 既有测试 |
| `tests/test_overlay_peripherals.py` | +11 / −19 | 既有测试 |
| `tests/test_convert_frameseq.py` | +9 / −5 | 既有测试 |
| `tests/test_sprite_acts_tail.py`（**新增**） | 未跟踪 | ACTS 截尾用例 |
| `tests/test_sprite_idle_tail.py`（**新增**，`8c4a926e…b87d`） | 未跟踪 | IDLE 截尾用例 |
| `tests/test_sprite_move_tail.py`（**新增**，`c7b40862…21c6`） | 未跟踪 | MOVE 截尾用例 |

合计 16 个跟踪文件 +4132 / −269，3 个新增未跟踪测试。**本轮未 add / commit / stash / checkout。**

### 未改动（明确声明）
`runner.py`、`scenario.py`、`source_probe.py`、`flight_scenario.py`、`collision_scenario.py`、`mem_probe.py` 全部**零字节改动**；
两个导出包与既有 `results/**`、`appdata/**`、冻结台账**零写入**。

## 三、实现要点

1. **身份链，不偷换**：`fair-new-20260926-b` →（覆 `pet/sprite_behavior.py` + 加 IDLE 测试）→ `fair-idlefix-20260926-a` →（覆 `pet/sprite_behavior.py` + 加 MOVE 测试）→ `fair-movefix-20260926-a`。
   - **idle 历史轮的 new 侧是 `fair-idlefix-20260926-a`，身份必须保留**：后续 MOVE 修复只改 MOVE 路径（`loops=1` 走登记分支，`move_clip_finished`），**不触及 idle 圈末语义**，因此 idle 结论可复用；但**包身份不能替换**——引用 idle 数字时必须写 `fair-idlefix`，不能写成 `fair-movefix`。
2. **三个修复及其机器证据范围**：
   | 修复 | 机器证据 | 范围边界 |
   |---|---|---|
   | IDLE 截尾（圈末解码器重启） | 单轮真跑 3/3 圈：`natural_end_pending=True`、`park` True、`_rearm_loop_reader` True、**同 PID 同 generation**、`_hard_stop` 0 次、238/239/240 每圈交付。未修 b 包同判据四条全 false（对应现象为每圈硬停换代 + 尾巴三帧从未交付） | 单宠 idle、`--frameseq off`、n=1；**present 未测**；冷启动曾出现 19 次绑定风暴（已判定非本刀引入，但 n=1 不能统计排除被放大） |
   | MOVE 截尾 | 2 次 side run（1 宠/3 宠）move 圈 `0..240` **完整 241 帧**、去重 `gaps=[]`、末帧之后才交付 idle、`final_vs_target=[0,0]`、零回滚/隐藏。修前对照：新侧 `fab-w-mv1on-*-2n` 缺 **240**、`fab-w-mv3on-*-2n` 三鱼各缺 **239/240** | 仅 new 侧、`--frameseq on`；**`--frameseq off`（WebMClip）路径未测**；无 base 侧对照、无 ABBA；**不含性能结论** |
   | 音效 warm | 启动期 `sound_winmm.pool.warm` 345.81 ms 真开出 4 个句柄；碰撞那一次发声 5.8884 ms（对照 167.7439 ms）；相位内 `WinmmApi.open` 0 次 | **只覆盖音效层**；n=2；同轮另有 104.327 ms 非音效空窗**未归因**、一处 72.472 ms **未定位**——**不许推给音效或架构** |
3. **主比较的材质与归因**：主比较（idle/MOVE）**两侧素材逐字节相同**——idle `待机呼吸休闲.webm` 441437 B `deb965d0…60395`、MOVE `左转奔跑.webm` 614526 B `79882aed…18d52`，**同为 640×360 / 24fps / 241 帧**。⇒ **既无插帧、也无降清晰度**。差异来自**整套播放管线 + 渲染拓扑**（帧序列无损 WebP 直投 vs VP9 解码 + ffmpeg 子进程；三进程 vs 单进程 overlay），**不是单变量架构收益**。

## 四、性能分析

**方法**：`cd D:/dsh-pet-src/.scratch/arch-ab && python -B runner.py run --label <新label> --side <base|new> --pets <1|3> --scenario <idle|move|switch|flight|collision> …`（新侧加 `--frameseq on`），逐轮只读机验脚本见 `closeout-*/out/*.json`。
**环境**：Windows / CPython 3.13.7 / PySide6 6.11.2 / H27T22S 170 Hz / DPR 1.0 / 2560×1440 / AC 100% / `scale=0.85` / `playback_speed=1.0` / `idle_low_fps_enabled=false` / 两侧同禁 predict+prewarm。
**采样与口径**：CPU = 同 `(pid, create_time)` 窗内首末 `cpu_seconds` 增量（**下界**：窗内新生实例的首读累计不计入）；内存 = **同一采样行内进程树求和**后取均值/峰值（不是各进程峰值相加）；资源采样 0.5 s，相位窗首末行内缩会造成覆盖率缺口，**缺口轮如实标注、不当通过**。

| 指标（新 vs 旧） | 实测 | 归属 |
|---|---|---|
| 单宠 idle 整树 CPU | 6.0078 s → 6.1094 s（+1.7%，**≈持平**） | 稳态 |
| 单宠 idle 树 RSS 均 / Private 均 | 182.94 → **191.475 MB**（略高）；150.67 → **133.315 MB**（稍低） | 稳态 |
| 单宠 idle 窗内 ffmpeg CPU | 1.7420 s → **0** | 新增路径取代既有 |
| 三宠 idle 根 CPU 和 | 13.7422 → 15.2578 s（+11.0%） | 稳态 |
| 三宠 idle **整树 CPU** | 18.4375 → **15.2578 s（−17.2%）** | 稳态 |
| 三宠 idle 树 RSS 均 / Private 均 | 537.25 → **216.10 MB（−59.8%）**；451.47 → **158.47 MB（−64.9%）** | 稳态 |
| 三宠 idle 进程数 / ffmpeg | 6 → **1**；(3 个, 4.6953 s) → **0** | 拓扑 |
| switch 绘制就绪（绘制出口口径） | 旧 88.2–91.4 ms → 新 **8.4–15.9 ms** | **不是 present**，见下 |
| 缓存磁盘 | 单角色 11 段净增 **+154,957,202 B（≈+155 MB）**；`frameseq` 154.96 → 309.92 MB | 新增常驻 |

**结论（逐条）**：
1. **单宠 idle：整树 CPU 近持平（+1.7%，n=2，不称差异）**。RSS 略高、Private 稍低，均在轮间自差量级附近。
2. **三宠 idle：资源明显降低**——整树 CPU −17.2%、RSS −59.8%、Private −64.9%、进程 6→1、ffmpeg 归零。**这是本轮最强的一组证据**。**但仍是整套实现差**（overlay + 单进程三 sprite + IDLE 修复 + 11 段世代缓存 + frameseq on 一起变），不可归因于纯架构。
3. **MOVE 单/三宠**：逐帧修复**达标**（`0..240` 完整 241 帧，1/1 + 3/3；修前新侧缺 240 / 缺 239+240）。资源上部分轮**有效窗覆盖 <95%**（短相位 + 0.5 s 资源采样造成首末内缩，非场景失败）⇒ **只示方向，不给精确百分比**。
4. **switch 单/三宠**：绘制就绪（draw_ready / callback_ready）明显更快（本口径 6–10×）——**这是"绘制出口返回且帧签名匹配"，不是屏幕 present**，也没有像素读回；且新侧 `frameseq on`、旧侧无帧序列概念，**只作本口径观测差，不作架构归因**。
5. **flight / collision**：**不能把总 CPU 比成"谁赢"**——两侧物理常量与落定时长本就不同（恢复系数 **旧 0.7702/0.7552 vs 新 0.6688/0.6737**；落定 rel 旧 9.100/9.139 s vs 新 6.600/6.561 s；collision 旧 ~9.7 s vs 新 ~7.3 s）。故只给每秒率并注明状态工作量不同。
6. **20 动作轮（move1/move3/switch1/flight1/coll3 × 4 轮）是"机制通过"**：20/20 `smoke.valid=true`、runner/mem rc 全 0、零 invalid、零停批；**但不是"所有资源窗通过"**（多轮覆盖率 <95%，已标注 `coverage_ok=false`）。
7. **历史 WebM off 对照（不藏）**：单宠 idle 的 on/off 参考轮中，**off 侧更耗内存**（树 RSS 均 247.97 / Private 均 202.38 MB vs on 191.47 / 133.32），而 **on 侧根 CPU 更高**（6.1094 vs 5.5391 s，+10.3%）。这个 off 轮是**解释性实验**（不同组、非同一批消融）**不是主比较**，但它**必须留在报告里**。
8. **内存/CPU 的正确说法**：已证的是"窗内 **0 个 ffmpeg 子进程**、无解码线程"；**不宣称 CPU 零开销、不宣称 mmap 零内存**（单宠 RSS 191 MB 就是反例）。**帧序列多世代与旧无戳目录并存**，而进程内是否有界/是否有 LRU 硬限，**本报告无证据、不宣称**。
9. **旧 mask 归因**：旧侧 mask 优化**已实测但收益不充分，明确止损、不再强优化**（算式纠偏见 `.scratch/arch-ab/mask-opt-65/APPENDIX-OLDSIDE-MASK-CORRECTION.md`：正确式为 `rebuild.mask − rebuild.scale`）。**不再研究。**
10. **素材维度的残余**：48fps 在**历史**新侧谱系（09-25 `2x2-*-fs-38/40`，模板 `act-fs24-29`）**已真跑过**（481/481 全交、0 ffmpeg），但**最终候选侧未测**；且同 fps 下 48fps 相对 24fps **root CPU 上升**（320 行配对 +16.9% / +46.9%，48fps 轮间自差 17.5% ⇒ 幅度不牢）。**不再扩研究。**

## 五、实机运行记录

- **现场复现**：全部结论来自本机真进程 + 真屏参数（不是 CI、不是 mock）。逐轮原始物：`results/<label>/{base,new}/{probe-slot-*.json, summary.json, samples.jsonl}`、`closeout-*/out/*.json`、`closeout-*/logs/*.log`。
- **用户可见行为的确认**：本轮**无**用户人工观感确认；所有"快了/省了"都止于**产品绘制出口**与**进程计数器**，**present（屏幕实际呈现）未测**。
- **边界与失败路径**：
  - 起手安全门**确实拦住了**两次：`closeout-regression-20260926-{e,f}` 的 `mem_probe --mode sustained --seconds 185 --require-sustain 180 --percent-max 85 --min-available-mb 2048` 两次均 `ok=false`（e：`longest_ok_s=54.02`、越界 80/185、available min 1388 MiB；f：`longest_ok_s=129.04`、越界 54/185、available min 1581 MiB）⇒ **ruff / pytest 均未启动**。
  - 压力子项 12 轮**零执行**：环境门 `longest_ok_s=75.02 < 180` **且**工具适配未过验收（4 项已确认缺陷 + 3 项未核疑点）⇒ **按"一次最小适配仍不可靠即止损"停止**。**不提供该入口的假复跑命令**，也不把工具缺陷算作产品失败（详见 `.scratch/arch-ab/closeout-stress-20260926-d/ACCEPTANCE-REJECTION.md`）。
- **无法自动验证的能力及其排查证据**：present / GPU 无法在现有探针架构内自动验证——有 PDH 探测，但 **pet 侧无可归属实例 ⇒ 不能证明为 0**；屏幕呈现无 DWM/像素回读路径。**Qt 输入注入不经过 OS 命中/穿透判定**（`injected_not_real_mouse` 已落盘），故**不做跨平台结论**：**只在 Windows 上验过，不冒称 Linux/macOS 行为**。
- **资源安全阈值的性质**：`内存 ≤85% 且 available ≥2048 MiB 连续 180 s` 是**本项目的实验管理阈值，不是用户硬要求**；超线只作协变量记录，不改变结论口径。（"CPU 空闲 ≥85%" 是曾经的一处脚本误设，**已修**，不作为现行判据。）

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查（最终候选） | `ruff check --no-cache .`（cwd=被测包） | **未运行**（安全门未过；e/f 两次均止步；**已于 §十 补测通过：ruff All checks passed**） |
| 全量 pytest（最终候选） | `pytest -q -p no:cacheprovider --basetemp <切片>/tmp` | **未运行**（同上；**已于 §十.1 补测通过：3638 passed / 11 skipped / 0 failed**） |
| 全量 pytest（**历史 b 包**，非本候选） | 同上口径 | `3605 passed / 11 skipped / 0 failed / 0 error`（431.56 s，rc=0），ruff 全绿 —— 见 `.scratch/arch-ab/fair-ab-prep-20260925/verification-b-20260926-0223/REPORT.md` |
| 逐轮机制判门 | `closeout-*/out/*-accept-<label>.json`、`closeout-*/out/rc-<label>-{runner,memrun}.txt` | 20/20 + 4/4 机制门通过；rc 原件在盘 |
| 缓存正确性 | `frameseq-postmigration-20260926-0007` 审计 | `ALL_OK=True`：11/11 段、**2651 帧三方 sha 全等**、帧聚合指纹与旧目录**逐字节等价**、产品采纳 11/11、fallback 归零、白名单外零写入（14,922 文件）；独立 `sha256sum` 交叉 11/11 `SAME-ALL`；负例 10/10 如期报红 |
| 架构红线 | `tests/test_architecture.py` | 本轮**未跑**（安全门未过） |

## 七、已知限制与后续

**状态口径：基础比较已完成；最终候选的发布验收未完成。** 后续只在文末**追加验收段**，不覆盖上述结论。**本节 1–2 条已被下文取代**（累计全量见 §十.1、长稳见 §十.2 与 §十三）；本节其余各条仍是当前未验项。

**已完成的（基础比较）**：单/三宠 idle 对照、MOVE 单/三宠、switch 单/三宠、flight、collision 共 24 轮有效 + 20 动作轮机制通过 + 缓存正确性审计 + 三个修复的机制验收。

**未完成的（发布验收）**：
1. ~~最终候选累计回归未验~~（**已于 §十.1 补测通过：ruff 绿 + 3638 passed / 11 skipped / 0 failed**）。
2. **最新有界长稳未运行**：**不拿 30 分钟老数据替代**（那是 2026-09-24 的单窗口长稳，对象与身份都不同）。
3. **极限压力**：12 轮零实际执行，适配已否决止损；需要**新的适配授权 + 修复 + 子进程真实验证**才能恢复。
4. **present / GPU / 用户可见帧率 / 屏幕命中与点击穿透 / 头槌错误复入**：一律未验。
5. **MOVE 的 `--frameseq off`（WebMClip）路径**未测；**最终候选的高帧接入**未测。
6. **插件化评估不写、不做**——性能最终尚待项未收口前，不进入插件化方案。

**保留的两处事故引用（无删样）**：① 三宠 switch 早期 R3 一轮 invalid，**用户已亲口确认系不小心拖动所致，原因调查停止**（独立附录由 `closeout-switch3-20260926-b`/`closeout-20260926-a/SWITCH3-CORRECTION.md` 承载）；② MOVE 早期一轮 `out/rc-*.txt` / `out/round-*.json` 因 `TAG` 重名**被后一格覆盖**，单宠格 rc 记为 `unknown`、**不重建数值冒充原件**（见 `.scratch/arch-ab/idlefix2-moveon-abba-20260926-1510/out/{SCAFFOLD-TAG-COLLISION,CORRECTION-rc-frame-cpu}.md`）。

**复跑（用全新 label，绝不覆盖原输出）——基础单场景命令（有效入口）**：
```bash
cd D:/dsh-pet-src/.scratch/arch-ab
PYTHONDONTWRITEBYTECODE=1 D:/dsh-pet-src/.venv/Scripts/python.exe -B \
  fair-ab-prep-20260925/plan/scripts/mem_probe.py --mode sustained \
  --seconds 185 --require-sustain 180 --percent-max 85 --min-available-mb 2048 \
  --out <新切片>/out/mem-window-gate-<新标签>.json          # 先过门；不过即返回
$PY -B runner.py prep --label <新label> --pets <1|3> \
  --base-export-dir exports/base-2786c15 --new-export-dir exports/fair-movefix-20260926-a \
  --protect-pid 10620 --protect-pid 24060
$PY -B runner.py run --label <新label> --side <base|new> --pets <1|3> \
  --scenario <idle|move|switch|flight|collision> <该场景参数> [--frameseq on]
```
最终候选累计回归（门过之后才串行启动，cwd = `exports/fair-movefix-20260926-a`）：
`ruff check --no-cache .` → `pytest -q -p no:cacheprovider --basetemp <切片>/tmp/pytest-basetemp`。

> **⚠️ 长稳（逗号多相位）不是上面这条命令能跑的——不要当可通过门命令用。**
> 原 `source_probe.py` **不支持** `--scenario a,b,c`（`source_probe.py:425` 把整串当成一个场景名 ⇒ 0.11 s 退出、`rc=2`）。
> 逗号多相位**唯一已验证入口**是 k 切片的局部副本：`closeout-soak-cli-20260926-k/run_soak_cli.py`（它只把 `runner.PROBE` 指到 `source_probe_local.py`，**原工具零改动**），两侧长稳脚本 `closeout-soak-20260926-l/run_soak_l.sh`、`closeout-soak-new-20260926-m/run_soak_m.sh` 均走该入口。
> 且即使走该入口，本轮长稳也**只是描述性观测**：runner 仍**返回 `rc=2`**（工具误报，见第十三节），**`rc=2` 未追绿、不得当作"长稳已通过"**。

## 八、风险与回滚

- **影响面**：本文不改代码、不改配置、不新增配置键。19 项 WIP 与两个导出包保持原状。
- **回滚**：无需要回滚的改动。若要退回旧架构，**必须靠替换发布产物**：**禁止宣称"运行时一键切回旧多进程"**——多进程层已在 Phase 4.4b 退役，产品内不存在该开关。
- **建议**：**保留旧版可回退安装包**（`base-2786c15` 对应的构建产物）与**用户数据备份**，并在切换前做一次**兼容检查**（配置键、素材目录、`frameseq` 世代缓存）。新包带**+155 MB 量级的帧序列缓存**，且多世代与旧目录在一段时间内**并存**，安装/升级前需确认磁盘余量。
- **不以"压力验收通过"作为默认发布依据**（本次未通过）；**不以 b 包 3605/11 的全量结果代替最终候选的累计回归**。

## 九、追加验收：最终候选静态检查（2026-09-26）

最终候选 `fair-movefix-20260926-a` 已实际执行 `python -m ruff check --no-cache .`，退出码 0，输出 `All checks passed!`。原件：`../.scratch/arch-ab/closeout-static-20260926-g/logs/ruff-regression-fair-movefix-20260926-g.log`。这是低负载静态检查，不依赖桌宠性能实验的起跑内存窗；正文先前“ruff 未启动”描述仅代表 e/f 两次尝试时的状态。最终候选全量 pytest 在**该时点**尚未运行（此状态已被第十节取代——全量已于 18:48–18:54 一次跑通、全绿）。

现有工具可执行三宠 idle 600 秒加 10 秒预热并保留全段资源样本，但 `scenario.py:1231–1238` 只落盘前 8000 条帧／绘制事件。长稳的末段逐帧证据会截断；全窗聚合不能替代末段原始证据。当前未执行该长稳，也未据此声称全程动画无冻结。可执行范围与限制见 `../.scratch/arch-ab/closeout-static-20260926-g/REPORT.md`。

## 十、最新验收：最终候选累计全量 + 长稳受阻 + 人工观测准备（2026-09-26 追加，**权威于本报告全部上文**）

**证据截至：2026-09-26 19:0x。以下为追加段，不覆盖上文任何历史结论。**

### 10.1 最终候选累计全量：**已验，全绿**
被测（只读）`exports/fair-movefix-20260926-a`；`QT_QPA_PLATFORM=offscreen`、`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`、单次无重试。

| 项 | 实测 |
|---|---|
| 命令 | `python -m pytest -q -p no:cacheprovider --basetemp <切片>/tmp/pytest`（cwd = 被测包） |
| 时刻 / 耗时 | 18:48:08 → 18:54:31 / **380.10 s** |
| **rc** | **0** |
| 结果 | **3638 passed / 11 skipped / 269 warnings**；**FAILED 0 / ERROR 0** |
| 原始日志 | `../.scratch/arch-ab/closeout-reboot-20260926-i/logs/pytest-regression-fair-movefix-20260926-i.log`（含 cwd/命令/env/起止/rc 行） |
| rc 原件 | `../.scratch/arch-ab/closeout-reboot-20260926-i/out/rc-regression-fair-movefix-20260926-i-pytest.txt`（`0`） |
| 静态检查 | **ruff 亦绿**：`ruff check --no-cache .` rc=0、`All checks passed!`（`closeout-static-20260926-g`） |
| 与 b 包基线对照 | b 轮 3605 passed / 11 skipped → **+33**（= 新增 `tests/test_sprite_idle_tail.py` 17 + `tests/test_sprite_move_tail.py` 16），skip 数不变 |
| 身份与命令出处 | `../.scratch/arch-ab/closeout-reboot-20260926-i/REPORT.md`（含起手门 `longest_ok_s=184.06 ≥ 180`、部署宠 PID 25624 经 WM_CLOSE 0.26 s 正常退出） |

⇒ **第七节"最终候选累计回归未验"、§九"全量 pytest 尚未运行"至此已被取代。**

### 10.2 有界长稳：**仍未验**——本轮被**夹具 CLI 缺口**挡住，**不是产品失败，也不是内存门失败**
- 本轮起手门**是通过的**（`ok=true`、`longest_ok_s=184.06 ≥ 180`）；因此**不得把这次称为"内存门失败"**。
- base 侧只跑了 **0.11 s** 即结束：`runner rc=2`、`smoke.valid=false`、`phases=1`、`ok_phases=0/1`、`phase.reason="未知场景 idle,idle,…(×60)"`。new 侧按链内 `STOP_SOAK` **未启动**。
- 代码级原因：`source_probe.py:425` = `scenarios = list(SCENARIOS) if args.probe_scenario == "all" else [args.probe_scenario]` ⇒ `--scenario a,b,c` 整串被当成**一个**场景名；`runner.py:2287` **只在算预算时**切分逗号，`scenario.py:1789` / `:1705` 用整串 ⇒ 该 CLI 路径**不支持逗号多相位**。
- **纠正此前 g/h 的结论**：`closeout-soak-20260926-h/REPORT.md` §1 据 `source_probe.py:259` 预算式与 `scenario.py:1131-1140` 逐相位 cap **判定"逗号多相位确实可执行"**——该判定是**工具分析错误**（把预算公式当成支持证据），**不是产品失败**，也**不是**本轮 i 的内存门问题。原报告与其 `APPENDIX-g-CORRECTION.md` **保留原样**，以本条为准。
- 处置：按"多相位不可行有具体代码证据即止步"**止步，不造框架、不打补丁、不重跑**。**长稳仍是未验项**（与此前 e/f/h 一致）。

### 10.3 人工观测准备（现状，**尚未开始**）
- 候选以**普通产品入口**运行：`python -m pet --slot 0`，PID **30304**、create_time **1790420447.973614**、cwd = `exports/fair-movefix-20260926-a`；隔离 `appdata/manual-final-3p-20260926-j/new`；**无** Session/Recorder/冻结/摆位/输入注入/产品补丁。
- **宠数 3**（产品日志"按活跃清单复活 2 只子肥鱼" + 同刻截图 3 只可见）；配置 sha 与历史轮同（`6c66b91bb619257501…196cdc`）。
- **用户尚未明确说"开始"** ⇒ **不计为观测轮已跑**，本轮**不产生任何压力结论**。监测只读口径与"能测/不能测"清单见 `closeout-manual-20260926-j/READY.json`。
- **如实记录一次启动失误**：首次以隔离路径启动时**多写了一层 APPDATA、只起了 1 宠**；该次已停并**保留**在 `closeout-manual-20260926-j/_mistake-1/`（未删除、未覆盖），随后按正确路径重起 3 宠。
- **手动轮的证据边界**：只有**资源 / 日志 / 用户症状**；**不支持**精确碰撞计数，也**不支持 present**。

### 10.4 本节之后
本节之后只继续**追加**新章节；上文（含 §九）一律作为历史快照保留，不重写。

## 十一、追加：真人手动轮结果与用户反馈（2026-09-26，**仅新侧 1 轮自然手动，非压力、非 ABBA**）

**样本与口径**：`manual-live-20260926-190700`，**180 样本 / 跨度 89.4954 s**（`elapsed 0.001697 → 89.500316`），间隔 p50 0.5 s（0.4905–0.5121）；根 **PID 30304 / create_time 1790420447.973614**，最终候选 `exports/fair-movefix-20260926-a`、普通入口 `python -m pet --slot 0`、3 宠、隔离 `appdata/manual-final-3p-20260926-j/new`；**输入是真人且未被仪器化**。全部数字引自 `../.scratch/arch-ab/closeout-manual-20260926-j/manual-live-20260926-190700-analysis.json`（未改原始数据）。

| 项 | 实测（同刻树求和；树 = 根单进程） |
|---|---|
| CPU（单核口径，逐 pid 同 create_time 首末累计差 ÷ 覆盖秒） | 全程 **113.23 %**；pressure 段 **109.14 %**、recovery 段 **121.08 %** |
| 内存均/峰 | pressure sum RSS **232.57 / 240.18 MiB**、Private **176.55 / 181.61 MiB**；recovery **230.52 / 239.24**、**172.59 / 180.63** |
| 恢复末 10 s 相较压力峰 | RSS **−8.87 MB**、Private **−8.55 MB**；线程末 21 vs 峰 25（−4） |
| 完整性 | `root_alive` 180/180 true；`errors` 空；身份集**恰 1 个**；全程**未见子进程**（≠ 无短命） |
| 系统内存 | 69.2 % → 66.3 %（66.3–71.2）；available 最低 4512.3 MiB |

**用户反馈原文（逐字）**：『没感觉有什么问题，就是我拖拽中途点开字agent想看看内容的时候有降帧，过一会就好了』。

**据此能说与不能说**：能说——本次真人操作**未主观发现明显碰撞故障**，并**存在"打开 agent 内容时短暂降帧后恢复"的主观现象**（保留记录，**不当作外部干扰剔除、不判 invalid**）。不能说——**未采**打开精确时刻、**present**、**其它进程（含 agent 应用本身）CPU** ⇒ **既不能归因环境/外部应用，也不能证明桌宠本体无问题**。另：只读产品日志显示 **19:08:22 / 19:08:24 / 19:08:30 仍有灵动岛拖拽落点** ⇒ 后 30 s 的"recovery"标签段**不是干净的恢复段**，**CPU 121.08 % 不能用来下"恢复异常"结论**（也不能反向用它说恢复良好）。

**与第 10.2 / 第七节压力的关系（不得混称）**：本节是**仅新侧 1 轮自然手动观测**，**不是**压力子项的 12 轮，**不是** ABBA（无旧侧对照、无第二遍、无配对）⇒ **不假装"原自动压力已通过"**，极限压力仍属未验项（12 轮零执行、适配已否决止损）。

**本节之后的纪律**：仍只追加；原始资源数据（`manual-live-20260926-190700-{samples.jsonl,meta.json}`）保持只读未动。

**停手时点补充与表述纠正（同轮追加，用户事后确认）**：用户原话「停手是在我看到你的消息后就没动了」⇒ 用户系**见到停止提示后**停手；该提示实际显示／被读到的时刻**未采**，原始鼠标输入**亦未采**，故提示时间与日志时间**不能精确对齐**。

据此，上文「19:08:22 / 19:08:24 / 19:08:30 仍有拖拽落点 ⇒ 后 30 s 不是干净的恢复段」应限定为「**预定 recovery 标签区间内仍有拖拽落点记录**」：**不能**认定用户见到提示后仍在操作，**也不能**断言日志延迟是确定原因。

后 30 s 是采集器按启动时间划定的**预定区间**，不保证与真实停手后的 30 s 重合 ⇒ **CPU 121.08 % 既不判"恢复异常"、也不判"恢复良好"**；**保留全部原始数据，不因时间同步缺口要求用户重做整轮**。

## 十二、追加：插件化判断的范围变更（2026-09-26，**只判"新旧谁更适合"，不设计方案**）

**范围变更（用户明确）**：插件化**只要判断新旧架构谁更适合**，**不再要完整方案**。故本节**不设计插件化方案**——不给接口、清单、迁移步骤。第二节第 6 条「插件化评估不写、不做」在**"不写方案"**这一点上仍然有效，该行原样保留不改；本节只追加判断结论。

**判断：新 overlay 统一宿主更适合作为插件宿主底座**——①**服务唯一归属**：新侧共享子系统**常开化、每进程单实例**（`exports/fair-movefix-20260926-a/pet/app.py:1142-1144`），拓扑分支再把进程级 `agent_link` / `proactive` 注入**唯一**的 `OverlayShell` 壳（同文件 `:1741-1745`），扇出目标由 `presentation_targets` 单点决定（新侧 `pet/multi_window_shared.py:43`）。②**多宠协调 / 按需启停**：同一壳已同时是 PetWindow 两处服务的宿主（音乐歌词控制器、看看屏幕 worker，新侧 `pet/overlay_shell.py:539-547`）⇒ "谁启、何时停"有确定落点。旧侧 `SharedSubsystems` **仅 flag 开时实例化、各窗经 `PetWindow` 构造参数各自引用，flag 关则每窗自建**（旧侧 `exports/base-2786c15/pet/multi_window_shared.py:425-429`），且退出回调按窗级分支注入（旧侧 `pet/app.py:492`）⇒ **服务归属分散在窗上**。

**粒度只到这里**：轻可信功能**进程内**即可，**重耗时或需隔离的才落 worker**；这**不代表"所有插件各自独立进程"**，也**不代表放到进程外就自动安全**（IPC、状态同步、生命周期各要各自解决）。

**两边都没证到的**：新侧 GUI 阻塞**波及全宠**（单窗单壳，无按宠隔离）；旧侧是**按宠隔离**（真多进程），但**按宠隔离 ≠ 插件隔离**。故**两边都没有据此证明"完整插件系统已具备"**。本节是**架构适配性判断，不是插件性能实测**——未做插件化实现、未测插件粒度开销。核证据仅上述只读行，未全库检索、未联网、未运行程序。

## 十三、追加：两侧描述性长稳对照（2026-09-26，**不是胜负统计**）

**性质**：以下两次运行**各自独立、均为描述性观测**，**不构成有效 ABBA**（旧侧判定 invalid 未被改绿、两侧拓扑不同、无配对）；**不给新旧胜负排名**。工具、产品、门、旧原件**一律未改**。

| 项 | 旧 `soak-base-3p-20260926-l` | 新 `soak-new-3p-20260926-m` |
|---|---|---|
| 有效窗 | **601.125 s**（三 probe 交集，覆盖 99.884%） | **601.233 s**（60 相位，覆盖 99.97%） |
| 真实 rc | runner **2** / mem **0** | runner **2** / mem **0** |
| rc 原因 | 工具误报（门 invalid，**未改绿**） | 工具误报（`runner.gate()` 整串逗号筛相位 + 逐相位 `binds` 累计 vs `frames` 每相位量纲错配，**未追绿**） |
| 树 RSS 均/峰 | 首 60 s **527.93 / 540.8 MB**；末 60 s **607.76 / 617.7 MB** | 首 60 s **213.98 / 218.5 MB**；末 60 s **325.60 / 332.2 MB** |
| 树 Private 均/峰 | 首 **458.11 / 471.2 MB**；末 **542.31 / 552.7 MB** | 首 **161.33 / 166.8 MB**；末 **278.90 / 285.4 MB** |
| CPU（每 pid 首末差 ÷ 覆盖） | 三 root **15.06 / 15.50 / 16.36 %**（全覆盖，非下界） | 单 root **51.56 %**（全覆盖 600 s，非下界） |
| 进程数 | 峰 6（3 python root + 6 ffmpeg 身份） | 峰 1（无 ffmpeg） |
| 记录到的帧推进 / 交付间隔 | 末 60 s 每鱼 advances **236–237**/相位、frames **238–239**、`loop_restarts=1`、`hidden_frames=0`；**末段仍有帧续播记录**（含末段新起 ffmpeg 换代） | 逐鱼 **max 交付 gap 240–250 ms**（p99.9 ≈ 0.05 s）；**60/60 相位无截断**、`hidden=0`、clip 仅 `待机呼吸休闲` |

**结果已交付（能说的）**：① 两侧都**跑完**约 601 s 并**产出了可核的逐轮资源与相位记录**；② 新侧**记录到** 60/60 相位帧与绘制列表未截断、`hidden=0`、无 ffmpeg；③ 旧侧**记录到**末段仍有帧推进。

**证据局限（不能说的）**——与上面的"结果"分开读：
1. **`max_same_frame_static_s = 0` 不足以独立排除静止**：该指标只是记录到的同帧停留上界，**不能单独作为"不存在静止/卡顿"的证明**；主线另行核过原始 max gap，本节只**如实记录"记录到的帧推进与交付间隔"**。
2. 因此**不写"无真实失败"、不写"稳定"** 这类总结论；旧侧 `rc=2`、两侧工具误报**原样保留**。
3. **内存与取证结构混杂**：`source_probe` 的 Recorder **逐相位累计保留 frames / paint_rows 列表**（旧 60 相位 × 3 鱼、新 60 相位 × 3 鱼 × ~238 帧）⇒ 平台期抬升**至少部分来自取证结构本身**，**既不能称"无泄漏"，也不能称"产品已泄漏"**。
4. 相位边界每 10 s 一次 GUI 线程同步汇总 ⇒ **非完全无干预**；**present / GPU 未测**；**Linux/macOS 行为未验**（本文全部实机结论仅限 Windows）。
5. **高帧**：只有**历史新侧谱系**上跑过（`2x2-*-fs-38/40`），**最终候选未测**；**不默认换高帧或低清**（原因见第 0.2/四节）。

**原证与工具 rc 原因**：`closeout-soak-20260926-l/{RESOURCE-POSTHOC.md,REPORT.md,out/rc-soak-base-3p-20260926-l-runner.txt(=2)}`、`closeout-soak-new-20260926-m/{REPORT.md,out/derived-soak-new-3p-20260926-m.json,out/rc-soak-new-3p-20260926-m-{runner=2,memrun=0}.txt}`；逗号相位入口与补丁说明 `closeout-soak-cli-20260926-k/{PATCH.md,run_soak_cli.py,source_probe_local.py}`。**工具误报的 `rc=2` 不被改绿，也不被解释为产品通过。**

**部署与活性口径**：**最终候选未覆盖安装到日常目录**——`D:/dsh-pet/` 下日常运行的是**此前部署版 exe（也是 overlay 路线）**，不是本轮冻结候选，亦不能把它叫作旧多进程基线；实验期间出现过的「恢复 PID 22048」**只是历史记录，不得当作当前活性**（本报告不对任何当前进程状态作断言）。

### 原始帧间隔复核补充

依据 `.scratch/arch-ab/closeout-soak-new-20260926-m/out/frame-gap-rawcheck-soak-new-3p-20260926-m.json`：逐鱼拼接全部60相位后，相邻回调最大间隔分别为250.2、243.5、240.0ms；每鱼前三大间隔都在相位内部，**不能归因于相位边界汇总**，其实际原因未确定。该统计不含首回调前和末回调后的空档，末回调至采样结束约3.2秒属于收尾区间，不能把“相邻回调无超过2秒空档”扩大为“整个采样窗绝无停顿”。这些是帧回调，不是屏幕呈现。

## 十四、交付结论与验收边界

**建议保留新 overlay 作为后续主线，同时保留真正旧多进程版本的可回退产物。** 已有证据支持三宠资源占用与动画切换就绪的收益，不支持“全部场景都更丝滑”的保证。单宠待机CPU近持平、RSS略高；新版十分钟观察仍出现约250ms帧交付间隔；真人轮报告打开agent内容时短暂降帧后恢复。这些不利结果均保留。

本次交付的是**有边界的新旧对照评估，不是发布验收合格证**。静态检查与最终候选3638项测试通过；基础动作对照、素材历史实验、真人单轮以及两侧描述性长稳原件可追溯。正式压力矩阵未完成、长稳工具返回失败、资源记录混入采样器留存、最终候选高帧未验证，以及present/GPU归因/Linux/macOS缺口，均没有被补成“通过”。不据此自动发布或覆盖日常版。

按用户最后缩减的要求，插件部分仅交付适合性判断：**新统一宿主更适合按需插件管理，耗时及需隔离的能力应与GUI核心隔离**；不再将完整插件生命周期与迁移设计作为本轮交付要求。没有实现插件系统，也没有插件收益实测。
