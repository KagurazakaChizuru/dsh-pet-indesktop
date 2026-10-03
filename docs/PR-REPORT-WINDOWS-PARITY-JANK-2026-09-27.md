# Windows 专项报告：旧版功能继承收口 + 卡顿取证（2026-09-27）

> **状态（2026-10-01 最终）**：本报告为持续追加的工作记录。至 §十七，卡顿多条根因已定位并修复
> （拖岛撞鱼空转、飞行期帧交付推迟、碰撞音效耗时 −75%）；全量回归已跑（各轮数字见 §十四–§十七，
> 最终交付门禁见 PR 描述）。早期章节中「根因未找到/未跑全量/未实机」的表述为该时点记录，已被后文取代。
> 不冒用旧「3638 通过」当作当前改动的全量结果。待主线复核后才可宣称可提交。
>
> **2026-09-27 追加（不改上文）**：功能继承（第一轮 §一–§十 + 第二轮 §十一）与新架构优化
> （§十二 O1–O5）均已收口，本地 PR 说明草稿见 §十三；**最终全量已跑**：全量 pytest rc=0：3911 passed / 11 skipped / 0 failed / 0 error（446.42 s），ruff 全绿、git diff --check 通过；证据 `.scratch/windows-parity-20260926-a/full-suite-20260927-e/`（撤回 pinned 之后、本轮全部改动之后）。
> 撤回 pinned 首帧保留之前的全量是 3911 passed / 11 skipped（§十三），不得当最终全量。
>
> **基线**：`ebf971e`（fix(collision): 拖拽成员速度通道——拖鱼撞鱼/撞岛不再只剩平推）
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-27　**拓扑**：仅 `PET_RENDER_TOPOLOGY=overlay`
> **关联**：[架构公平对照报告](PR-REPORT-ARCHITECTURE-FAIR-COMPARISON-2026-09-26.md)、
> `.scratch/windows-parity-20260926-a/FEATURE-MATRIX.md`、`.scratch/windows-jank-20260926-a/`

## 一、本阶段解决什么（逐项）

| # | 项 | 语义（以旧实现 base-2786c15 为准） | 状态 |
|---|---|---|---|
| G1 | 岛碰撞开关（overlay 岛墙门） | 关掉「岛碰撞」→ 不建桥/撤墙；岛本体照常显示 | 已修·未实机 |
| G2 | 同屏几何变化（子宠迁移 + 可见气泡/岛墙全局原点） | 改分辨率/任务栏后子宠按原比例迁到新可用区；原点真变时在显气泡与岛墙跟新原点 | 已修·未实机 |
| G3/G3b | 碰撞音量 + 点击/碰撞门独立 | `on_collision` **直取** `collision_sound_volume`（无旧架构没有的轻/重分档）；两门各自独立、不缓存、排队回调播放前再查；pack 键失效用**浅拷贝快照**（原地改 id 也生效） | 已修·未实机 |
| G4 | 宠物间总碰撞开关（含子宠 per-slot） | 资格位逐 sprite 解析：主宠读本进程 config、子宠读各自 `config-slot-N.json`（缺文件继承、缺键/损坏缺省 true）；只过滤**宠-宠** pair，岛静态接触保留；窄刷新只重算资格位 | 已修·未实机 |
| G5 | ffmpeg 回收阈值接线 | `bind_clip` / `_sync_sprite_settings` 推 `ffmpeg_recycle_minutes`；归一与夹取仍在 `webm_clip.set_recycle_minutes`（未复制） | 已修·有边界（见 §七） |
| J | 卡顿取证工具（scratch，不进产品） | `jank_recorder.py` + `instrumented_entry.py` 只读计时包装（tick/frame/paint/overlay_paint），手工开始、150s 到点幂等独占落盘 | 工具自测过·**未取到真实卡顿证据** |

**红线**：旧语义优先于「看起来等价」的新设计——G3 中途一版按 `标称×音量/0.70` 缩放的实现是**新设计**，已被 review 驳回并改为直取配置值；G3b 先回读旧实现（门判在 `play_sound` 之前）再动手。

## 二、修改文件说明

### 本阶段追加（依据：留存 patch / 红绿记录 / 各切片说明所记的改动范围；**不以 mtime 作归属证明**）

| 文件 | 增删（`git diff --numstat`，相对 HEAD） | 改动意图 |
|---|---|---|
| `pet/sprite_sound.py` | +79 / −31 | G3 直取配置音量 + G3b 两门独立、缓存键 `(pack浅拷贝, data_dir)`、门在延迟回调播放前再查 |
| `pet/sprite_collision.py` | +45 / −2 | G4 资格位过滤宠-宠 pair（复用 `ignored_pairs`）+ 资格位入静止豁免签名 |
| `pet/overlay_spawn_state.py` | +32 / −0 | G4 只读读点 `read_slot_collision_enabled`（缺文件继承/缺键损坏缺省 true，不落盘） |
| `pet/pet_sprite.py` | +10 / −0 | G5 `ffmpeg_recycle_minutes=10` + `bind_clip` 按 `getattr` 推送 |
| `pet/sprite_bubble.py` | +28 / −2 | G2 `set_origin` 原点真变且气泡可见时 `reposition` 一次（不 show、不重启停留倒计时） |
| `tests/test_sprite_sound.py` | +273 / −10 | 旧契约参数化（音量×j）、两门四组合、重开、排队翻门、pack 变化/原地改 |
| `tests/test_sprite_collision.py` | +103 / −0 | 关掉的那只退出宠-宠 pair（纯逻辑） |
| `tests/test_island_shell_wiring.py` | +137 / −0 | G1 真壳 attach 三条（开关来回切、缺键默认、hide/show） |
| `tests/test_overlay_collision_toggle.py` | 新增（492 行，未跟踪） | G4 真 Config + 真壳 + 真 spawn：恢复/提升/per-slot/热切/窄刷新 |
| `tests/test_overlay_geometry_parity.py` | 新增（494 行，未跟踪） | G2 真实 Qt：几何参数化、迁移先于边界、可见气泡随原点、岛墙随原点、无桥不重启 |
| `tests/test_overlay_recycle_settings.py` | 新增（173 行，未跟踪） | G5 bind/热改/多库/无方法不崩/预热未 bind |

### 同文件累计 diff **无法独立归因**（混合改动，本阶段行数不猜）

| 文件 | 累计增删 | 说明 |
|---|---|---|
| `pet/app.py` | +18 / −2 | G1 的 attach 门**与**同一文件里更早的 issue #111 段 WIP 混在一起，逐行归属未拆分 |
| `pet/overlay_shell.py` | +221 / −5 | G2/G4/G5/窄刷新（含更晚的 recycle 改动）与更早 WIP 混在一起，逐行归属未拆分 |

### 此前 19 项 WIP（本阶段未触碰，仅列出以免误判为漏改）

`pet/frameseq_provision.py` +1005/−72、`pet/library.py` +205/−31、`pet/sprite_behavior.py` +471/−17、
`pet/island_bridge.py` +41/−6、`pet/slot_manager.py` +17/−5、`tools/convert_frameseq.py` +8/−4；
测试 `test_frameseq_provision.py` +1726/−87、`test_island_bridge_velocity.py` +305/−12、
`test_frameseq_clip.py` +41/−3、`test_convert_frameseq.py` +9/−5、`test_overlay_instance_gate.py` +45/−4、
`test_overlay_peripherals.py` +11/−19、`test_overlay_shell.py` +136/−2、`test_session_end_ffmpeg_guard.py` +52/−2，
新增 `test_sprite_acts_tail.py`(665)/`test_sprite_idle_tail.py`(768)/`test_sprite_move_tail.py`(444)。

**归因口径**：① `git diff` 是相对 HEAD 的累计 diff，单文件若被两条线都改过则**不能按行数拆分**，也不做逐 hunk 归属；
② 上表「本阶段」一栏的唯一依据 = **留存 patch / 红绿记录 / 各切片说明**所记的改动范围，**不以文件 mtime 作证明**；
③ `docs/INDEX.md` 当前是 `+2 / −0`：**两行累计**——更早加入的架构对照行（1 行）+ 本报告新登记行（1 行），**不称「与本阶段全无关」**（本报告自身就占了其中 1 行）。

### 未改动（故意）

`pet/collision.py`（数学）、`pet/webm_clip.py`（圈末/reader 生命周期，G5 明确零改动）、
`pet/config.py`（未新增键、未新增校验）、`pet/modern_settings_dialog.py`、多进程碰撞残层。

## 三、性能分析

**① 本阶段唯一的实测数字来自 scratch 取证工具（不是产品路径）**
方法：`.scratch/windows-jank-20260926-a/validation-20260926-b/bench_wrapper.py`（10000 call × 3 轮取中位数，不启动 Qt）
环境：Windows / Python 3.13.7 / pytest 9.1.1 / `D:\dsh-pet-src\.venv`；原件 `bench-20260927-004506.log`（rc=0）

| 指标 | 实测 | 归属 |
|---|---|---|
| 裸函数 | 56.8 ns/call（中位） | 基线 |
| wrapper·disabled | 225.7 ns/call | 记账关闭（仍存在的包装） |
| wrapper·enabled（短事件） | **2275.6 ns/call ≈ 2.28 µs** | 新增，仅使用该工具时存在 |
| 每事件包装开销 | 2218.8 ns | 新增 |
| 外推开销/秒 | paint 三宠 170Hz **1.132 ms/s**；frame 三宠 24fps 0.16 ms/s；tick 6ms 0.368 ms/s | 新增 |

**工具自报限制（照抄）**：「微基准不含 Qt 事件循环/解码/GIL 竞争/系统调用；ring 只在 ≥50ms 事件入队；py-spy 的 attach 开销另测，不能用本表代替」——**故 2.28 µs 不能当作真 GUI 结论**。

**② G1–G5 没有计时实测**（诚实登记）：本报告**没有**产品路径的稳态开销数字。可复核的只有结构事实（可 grep）：

- 新增路径触发频率：G1 仅 island 配置同步时一次；G2 仅全局原点**真变**时进入；G4 每目录事件 / 既有 3s 兜底轮询每活跃 slot 一次 `stat`（内容读只在签名变化时）；G5 只在既有推送点（build/切换/刷新/spawn/提升）。
- 新系统调用 / 网络 / 磁盘 / 线程：无新增线程、无网络；G4 有逐 slot `stat`（既有轮询通道内，无子宠时零 I/O）；G3 无。
- 内存与缓存：无新增长寿命缓存；`_slot_signature_cache` 每活跃 slot 一条；G4 热路径未被关 sprite 时 pair 表返回 `None`（不构造）。
- **未回答的**：稳态 CPU/RSS 变化量、`stat` 调用绝对耗时、G2 `reposition` 的帧内成本——均未测。

**③ 卡顿方向**：只有失败与受限的观测（见 §四），没有任何「卡顿来源已定位」的测量结论。

## 四、实机运行记录

- **日常部署版（历史状态，不是当前活性）**：PID 22048 `D:/dsh-pet/dsh-pet-standalone-webm-chat.exe --slot 0`（create 1790423654.27）当时在跑 overlay 部署；2026-09-27 00:49–00:56 期间 `taskkill /PID 22048`（不带 `/F`，rc 0）后 15s 仍存活 → 进程转托盘驻留，overlay 全屏窗已关、岛胶囊窗 129x44 仍在；恢复显示是**主线通过 CU（computer-use）托盘操作**做的，不是用户操作。**该记录只描述当时状态，引用前必须重新探活。**
- **本该失败的路径（实机观察到了）**：候选启动门在内存不合格时拦截——`live-20260927-a/launch-record-2.json`：`memory_gate {percent: 94.6, available_GiB: 0.82, need: ">=2GiB 且 <=85%", verdict: "fail"}` → `launch_attempt.started=false`；`launch_candidate.py --dry-run` 报 `gate_ok=false`（rc=0，真跑返回 3）。同一会话 00:47 的门是 71.7% / 4.32 GiB（pass），**内存中途恶化**。
- **媒体包只读验证（junction + 真 MovieLibrary 探针）**：`candidate-20260927-a/assets` → `mklink /J` 到 `fair-movefix-20260926-a/assets`（rc=0，同卷）；`media-class-probe.json`：`PET_FRAMESEQ=0` 下 `frameseq_mapped_count=11`，`待机呼吸休闲/左转奔跑/被鼠标拖拽悬空反馈` 三类**真实返回 `FrameSeqClip`**、`zero_ffmpeg_spawned=true`、未发生 assets 写入。结论：**`PET_FRAMESEQ=0` 只禁首跑供给（转码/世代发布那条链），不禁已合法 `.g<戳>` 世代的采纳**。
- **候选代码快照身份**：`identity-check.txt` `identical: true`（157 vs 157 个 .py，`pet/app.py` sha 前缀 `2817effdd0a6abf3`）；但该快照（00:49）**早于 00:59 的最新 recycle 改动**，故它**不能**再当「当前最新代码」用——重跑需**另建改名的新候选目录**，不得改旧目录。
- **卡顿正式轮：尚未执行（0轮）**。计划上限为两轮、每轮150秒，不是“已经跑了两轮但零卡顿”。本阶段候选未启动，`launch-record.json` / `launch-record-2.json` 与主线记录一致；不存在需要补造的正式结果。编写本报告时曾把“正式两轮150s零次（执行）”误读为“两轮已执行、卡顿零次”，此处纠正该转述错误。工具短时自测不计入真人复现次数。
- **py-spy 未 attach**：两份 launch record 均记「无候选进程可 attach；不擅自 attach 日常版」——不是「测了没问题」，是**没测**。
- **内存压力与结论边界**：观测点 71.7%（00:47）→ 94.6%/0.82 GiB（00:49 门失败）→ 95.2%/748 MiB（G5 轮，`recycle-settings-evidence/CONCLUSION.md`）；最大占用者 `OneDrive.Sync.Service.exe ~5.5GB`（与本实验无关）。**未强杀任何其它应用**。内存压力确有外部来源，但**这不证明卡顿全是环境问题**。
- **卡顿根因**：**未查到**。因此不写「已优化 / 已丝滑」，也不把工具自测通过当作卡顿已解决。

## 五、测试与验证（逐项真实 rc，不简单相加成唯一总数）

| 项 | 红（修复前） | 绿（修复后） | 相关族 | ruff |
|---|---|---|---|---|
| G1 岛开关 | rc=1，1 failed/8 passed | rc=0，9 passed | 142 / 72 / 125 passed | rc=0 |
| G2 几何首批 | rc=1，5 failed | rc=0，8 passed | 83 / 256 passed | rc=0 |
| G2 增量（气泡+岛墙原点） | rc=1，2 failed/10 passed | rc=0，12 passed | 259 passed | rc=0 |
| G3 中间版（**已被驳回语义**） | rc=1，5 failed/12 passed | rc=0，17 passed | 95 passed/1 skipped | rc=0 |
| G3 终态（直取配置音量） | rc=1，13 failed/10 passed | rc=0，23 passed | 101 passed/1 skipped | rc=0 |
| G3b 两门独立 | rc=1，7 failed/25 passed | rc=0，32 passed | 110 passed/1 skipped | rc=0 |
| G3b 补刀（pack 原地改） | rc=1，1 failed/32 passed | rc=0，33 passed | 111 passed/1 skipped | rc=0 |
| G4 资格位（主配置） | 逻辑 rc=1，1 failed/19 passed；接线 rc=1，2 failed | rc=0，22 passed | 139 / 238 passed | rc=0 |
| G4 连续 tick 热切 | — | rc=0，23 passed | 200 passed | rc=0 |
| G4 per-slot | rc=1，4 failed/3 passed | rc=0，27 passed | 155 / 219 / 164 passed | rc=0 |
| G4 窄刷新契约 | 探针复现「全量覆写」（`playback 1.0` 覆盖原 `2.5`） | rc=0，28 passed | 124 passed | rc=0 |
| G5 回收接线 | rc=1，5 failed/2 passed | rc=0，7 passed | 82 passed | rc=0 |
| jank 工具自测 | rc=1，5 failed/19 passed → 中间 rc=1，1 failed/23 passed | rc=0，**24 passed**（3.44s） | —（工具仅 scratch） | rc=0 |

- **不把它们相加成唯一总数**：红/绿/相关族是**不同命令、不同文件集**，跨项不可合并。
- **本阶段没有跑累计全量**（`python -m pytest -q` 未跑），旧 3638 通过的数字**不迁移**到当前改动。
- **未跑（缺口，需补）**：`test_webm_clip_loop.py` 的 recycle 族、其余 15 个引用 `bind_clip` 的测试文件（内存闸门中断，`webm_clip.py` 零改动但风险未验）；`tests/test_architecture.py` 未跑（本阶段未增删模块，但未验证）。
- 敏感性（有牙齿）证明：G4 热切用 `probe_stale_prev.py` 人为冻结 `_prev_circles` → 复现幽灵位移；G4 窄刷新用 `probe_full_refresh_clobber.py` 换回全量语义 → 复现覆写。两者均为**探针**，不进产品套件。

## 六、本地 PR 说明段草稿（不执行提交/推送/建 PR）

**标题**：`fix(overlay): 继承收口——音效门与音量、互撞资格位、岛开关、同屏几何、ffmpeg 回收`
**范围**：仅 overlay 拓扑；7 个产品文件 + 6 个测试文件（3 个新增）；不动 `webm_clip.py`、`collision.py` 数学与多进程残层。
**测试**：各项红→绿见表 §五（器件级：真 Config / 真壳 / 真 spawn / 真实 Qt offscreen）；**未跑累计全量**，未实机。
**风险**：① 全部改动**未实机**；② per-slot 只接了 `collision_enabled`，其余 per-pet 设置仍取主配置；③ G5 的阈值所有 sprite 推**主设置**；④ 内存/时长类长跑未做。
**未发布**：工作树 WIP，未 commit/push，未创建 PR，未部署。

## 七、已知限制与继承缺口（列清但不扩大）

1. **本阶段验收本身未完成的**：累计全量 pytest；真实功能实机（未起桌宠）；卡顿最多 2 轮正式复测（无落盘结果）。
2. **闲置降帧**：`idle_low_fps_enabled/_threshold` 在新拓扑是**错位消费者**（实际反向关闭预测预热，文案与行为不符），`threshold` 零消费者——本轮未修，仅登记；修法边界见 `FEATURE-MATRIX` G6（只允许动 tick 间隔，**禁止**接 `set_fps`/跳帧来"让开关生效"）。
3. **更多 per-slot 设置未接**：`drag_physics` / `throw_strength` / `playback_speed` / `ffmpeg_recycle_minutes` 等仍取主配置一份值 → **不得**声称「完全继承」。
4. **duck 包音源语义**：旧碰撞在 duck 包下用 press 音，本播放器用 `candidates[0]`——属音源选择，未修，另案。
5. **气泡**：G2 只覆盖「原点变化时在显气泡随新原点」，用户报的**原症状（跟手延迟、隐藏恢复、迁移中显示态）未完整复现**，不声称全修。
6. **G7/G8 只读核查结论（短边界，不外推）**：
   - **G7（`stop()` 不释放子宠库）**：`stop()` 目前**没有已发现的正常生产调用**；换角色 / 主宠提升 / 子宠退出这几条路径各自有 `shutdown` 覆盖，故**撤回**此前「确定存在库泄漏」的说法——不是已证泄漏，也**不是**已证无问题。
   - **同一族（正常退出时 worker/ffmpeg 是否退出）**：**待实测**；在跑过真实退出之前，**不能说**「不可自动化验证」。
   - **G8（`sprite_bubble.close()` 未停/未断开 `_follow_timer`）**：close 后 timer 仍会跟随 overlay 寿命、并持有旧 follower；**是否累积、有无可见影响需要一条失败测试**才能定性，本报告**不称**「无界」也不称「有界已证」。
7. **范围外**：全平台（macOS/Linux）不在本轮；不采用插件/容器方案。

## 八、证据短索引（不改动已有证据，只指路）

- 继承对照与缺口：`.scratch/windows-parity-20260926-a/FEATURE-MATRIX.md`
- G1：`.../island-toggle-fix-evidence/`；G2：`.../geometry-fix-evidence/` + `.../visible-follow-correction/`
- G3：`.../sound-fix-evidence/`（**被驳回的中间版，保留对照**）+ `.../contract-correction/`
- G3b：`.../sound-switch-fix-evidence/` + `.../cache-inplace/`
- G4：`.../pet-collision-toggle-evidence/`（含 `hot-toggle-hist/`）+ `.../per-slot-collision-evidence/`（含 `narrow-refresh/`）
- G5：`.../recycle-settings-evidence/`
- 卡顿工具与门：`.scratch/windows-jank-20260926-a/`（`jank_recorder.py`、`instrumented_entry.py`、`identity-check.txt`、`validation-20260926-b/`、`live-20260927-a/`）

## 九、累计静态检查（2026-09-27 追加；只静态——未跑 pytest/collect/桌宠/构建/采门）

**环境**：`D:\dsh-pet-src\.venv`（ruff 0.16.7）/ Windows / Python 3.13.7。范围 = **当前工作树累计 diff**（原 19 项 WIP + 本阶段改动，不含 `.scratch/`）。日志与 rc **独占新目录**，未覆盖任何既有文件：`.scratch/windows-parity-20260926-a/cumulative-static-20260927-a/`（另附 `SUMMARY.md`）。

| 门 | 命令 | 真实 rc | 结果 |
|---|---|---|---|
| 累计静态检查 | `.venv/Scripts/python.exe -m ruff check --no-cache pet tests tools` | **0** | `All checks passed!`（`ruff-cumulative.log`/`.rc`） |
| 空白错误 | `git diff --check` | **0** | 仅 9 条 LF→CRLF 信息性提示，非空白错误（`git-diff-check.log`/`.rc`） |
| AST 解析 | `ast.parse` 逐文件（`git status` 列出的 31 个已改/未跟踪 `.py`，**忽略 `.scratch`**、不写 pyc） | **0** | `files_checked=31 parsed_ok=31`（未跟踪 6；`ast-parse.log`/`.rc`） |

**本轮相对上一版报告的新增改动（上一版漏列）**：`pet/sprite_bubble.py` 由 +28/−2 → **+72/−4**，并新增改动文件 `tests/test_sprite_bubble.py` **+156/−3** —— G8 follower close 生命周期收口（证据 `bubble-close-evidence/EVIDENCE.md`，红/绿原件同目录）。本节的 G8 部分**取代 §七 第 6 项中的 G8 记录**（该项说的「未停/未断开 timer」已修）；**G7 部分不变**。
**G8 红→绿（证据文件原值，历史分项、非本轮实跑）**：红 `2 failed, 8 passed`（① close 后 `_follow_timer` 仍 `isActive`；② 同 overlay 反复建/关 3 个跟随器后 `QTimer` 子对象数高于基线）→ 绿 **10 passed**；相关族①气泡/几何/外围/壳 **61 passed**、相关族②self_talk/投喂/聊天/菜单/提醒/实例门 **79 passed**。

**口径（禁止外推）**：① 本轮只跑静态，**没有 pytest、没有 collect**；② 本阶段累计全量仍为 **0 次**，历史 **3638 passed / 11 skipped**（`closeout-reboot-20260926-i`）**不是当前工作树**的数字，不得迁移；③ 本轮实测内存 **95.5% / available 698 MiB**（主线；更早证据点 95.2%/748 MiB）是**未跑全量的原因**，不是产品结论；④ ruff / `diff --check` / AST 全绿**不能**推出「功能全继承」或「不卡」；⑤ 交付状态仍为**不可交验**——本阶段实机记录仍缺。

## 十、本轮实际结果：当前工作树完整门禁（2026-09-27 02:08–02:15；ruff + 全量 pytest）

**结论**：`ruff check --no-cache pet tests tools` **rc=0**（"All checks passed!"）；全量 pytest **rc=0 → 3708 passed / 11 skipped / 269 warnings in 410.88s**（**0 failed、0 error**）。起 **02:08:26**、止 **02:15:19 (+08:00)**。命令：`QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider --basetemp <新目录>/tmp`（cwd = 本 repo；Python 3.13.7 `.venv`；未用 xdist、未单独 collect、失败未重跑）。证据（独占）：`.scratch/windows-parity-20260926-a/full-suite-20260927-b/`（`REPORT.md`、`pytest-full.log`/`.rc`、`ruff.log`/`.rc`、`env-and-start.log`、`mem-precheck-10s.log`、`load-sample.log`）。关键 sha（运行时刻）：`app.py 2817effdd0a6abf3`、`sprite_sound f6e5204cd44e4eb4`、`sprite_bubble ce37c4371cecc7c0`、`overlay_shell b87918fb35be4b63`、`overlay_spawn_state 6689ecc52fba8f7a`、`pet_sprite 45d5e5f1b5b67140`、`sprite_collision fca603d922e23946`；工作树 34 项既有 WIP 跑前跑后一致，无 git mutation/产品改动/配置写/部署。

**这取代 §九 的口径 ②③（累计全量 0 次 / 内存挡住）**：本阶段累计全量**已跑 1 次且全绿**。但仍**不得**与历史 **3638 passed / 11 skipped**（`exports/fair-movefix-20260926-a` 另一棵树、更早时间点）互替——用例数差 +70 与新增 tail/G 系测试方向一致，但两棵树集合不同，**不作等价增量结论**；11 条 skipped 的**身份未列**（`-q` 不输出原因，未为列原因重跑）。`tests/test_webm_clip_loop.py`、`tests/test_architecture.py` 均在 `testpaths=tests` 内被收集执行。

**内存（采样 84 点 / 5s）**：起手 10s 稳定 81.6–83.1% / 2641–2879 MiB；运行中**峰值 99.6% / available 59 MiB @02:14:31**，02:14:10–02:15:18 持续低水位（<1.2 GiB 约 68s、其中 <600 MiB 约 60s），本测试树 python RSS 峰值约 4.6 GiB；跑完 02:15:23 恢复 **66.7% / 5211 MiB**。**诚实登记**：低水位确实出现，我**未中途停止**（采样为后台记录、无实时守门，属流程缺陷），期间测试未报 MemoryError 且最终 rc=0——结论只适用于本次已完成的运行，不据此宣称内存充足。

**残留归属（跑后只读枚举，未杀进程）**：无 pytest 残留、无测试产生的 ffmpeg 残留（采样仅 02:09:05 出现 1 个测试期 ffmpeg，已退出）；现存 1 个 `dsh-pet-standalone-webm-chat.exe` **PID 17636**（日常部署，未触碰）与 3 个 ffmpeg（命令行指向 `D:\dsh-pet\_internal\assets\...`，属该部署自身解码子进程）；3 个 python 为 uv 缓存的 serena MCP 及子进程（测试前基线）。无新增 `__pycache__`；`tmp/` 留 1762 个用例临时目录（全在本证据目录内）。

## 十一、第二轮功能继承修复（2026-09-27）

> **状态：仍未达到 PR 可提交验收。** 本节是**第二轮**的记录（第一轮见 §一–§十，第二轮审计来源
> `.scratch/windows-parity-20260926-a/GAP-LIST-20260927.md`）。口径同 §一：**全部批次禁起桌宠、
> 禁 `python -m pet`**，只跑聚焦套件；全量在批次全部落地后单独跑一次。**卡顿线本轮完全没有处理**
> （用户叫停、另立任务），本节不写任何「已优化 / 丝滑」。
>
> **本节章节命名说明**：`test_pr_report_discipline.py` 要求报告含「修改文件说明 / 性能分析 /
> 实机运行记录」三个**标题级**必备章节。本文 §二/§三/§四 已占用这三个名字，故本节按模板
> 「后续轮次在同一文档追加新章节」的约定，把三者作为**本节子节**并加「（第二轮）」后缀，
> 避免标题重名；判定标准见 `DEV-HANDOVER.md` §8.3。

**范围**：38 条缺口（I1–I3 / M1–M5 / A1–A6 / N1–N5 / S1–S2 / P1–P2 / O1–O12 / T1–T3），
按「同一文件只归一批」串行分 8 批（B1–B8）+ 3 处收尾小修。批次纪律原文：`.scratch/windows-parity-20260926-a/DISPATCH-COMMON.md`
（禁 git stash/reset/checkout/commit/push；禁改文件范围外的任何文件；以旧版 `base-2786c15` 实现为准恢复契约，
不自造新机制；不降可见帧率、不加常驻 timer/线程）。逐缺口的状态 / 改动文件 / 红→绿 / 证据目录见
`.scratch/windows-parity-20260926-a/FEATURE-MATRIX.md` 的「第二轮（2026-09-27）」一节，本节不重复整表。

**逐缺口归属一句话**：B1 岛拖拽（I1/I2/I3）、B2 菜单作用对象（M1–M5）、B3 app 宿主（A1–A6）、
B4 动画状态机（N1–N5）、B5 碰撞音效音源与岛击门（S1/S2）、B6 气泡起止同步与重排方法（P1/P2）、
B7a 壳接线（O1/O2/O4–O9/O12 + P2 调用方 + N1 壳侧一行）、B7b per-slot 与逐只气泡/音效/自言自语/角色
（O3/O10/O11/F1/C1/C3/C5 + 闭合 A5）、B8 设置页文案（T1/T2/T3）。

### 修改文件说明（第二轮）

**归因口径（承 §二，不加新规则）**：① 下表「累计增删」= `cd /d/dsh-pet-src && git diff --numstat`（相对
基线 `ebf971e`）的**整文件累计值**，不是本轮增量；② 本轮增量只在**批次报告的留存记录给出过该数字**时才写，
否则写「不可拆分」——本工作区含更早的多轮 WIP，**不把整文件 diff 归给本轮**；③ 归属依据 =
留存报告 / 前后快照 sha（如 B7a 的 `final.sha256` + `b7a-only.diff` + `*.pre-b7a`）/ 红绿记录，
**不以文件 mtime 作证明**。

#### 本轮改动明确归属的文件

| 文件 | 累计增删 vs `ebf971e` | 本轮归属与依据 |
|---|---|---|
| `pet/sprite_menu_facade.py` | +114 / −30 | **整份属于本轮**（B2 + B7b + 收尾小修）。B2 报告记「+58 / −29 vs HEAD」并只列自己的改动函数，且**专门**对 `overlay_shell.py` 注明「该文件有他人 WIP」而对本文件无此注 → 说明 B2 动手前本文件无工作区 diff。B2：`_is_main_sprite` / `_persist_sprite_setting`(新) + `_cats`/`switch_clip`/`trigger_move`/`set_playback_speed`/`change_scale`/`set_drag_physics`/`go_default_corner`/`hide`/`trigger_golden_spin`/`on_look_screen`/`on_show_balance`/`on_check_update`；B7b：`cfg`（该 sprite 的配置视图）/ `persist_sprite_setting` 调用 / `request_switch_character`；收尾小修：`change_scale` 写 `sprite.scale` 之后调 `self._shell.on_sprite_scale_changed(self.sprite)`（`sprite_menu_facade.py:415`） |
| `pet/overlay_window.py` | +29 / −0 | **整份属于本轮**（B6）。只加 `_sync_follow_now`（位置监听小节）+ `_commit_drag_if_threshold_crossed` 尾部（+3 行）+ `_finish_grab` 的 `committed` 快照与条件调用（+4 行）；B6 报告明确「未动 `mouseMoveEvent` 及其他函数」。 |
| `pet/sprite_feeding.py` | +8 / −0 | **整份属于本轮**（B7a）。只加 `interpret_offer` 接缝（同旧 `file_eater:183-186`）。 |
| `pet/settings_pet_controls.py` | +91 / −10 | **整份属于本轮**（B8）。新增 `STREAM_CAPTURE_HINT`/`STREAM_CAPTURE_OVERLAY_HINT`/`IDLE_LOW_FPS_OVERLAY_HINT`/`IDLE_LOW_FPS_LEGACY_HINT`/`OVERLAY_WINDOW_SCOPE_IDS`/`ALL_PETS_SCOPE_NOTE` + `_is_overlay_topology()`/`idle_low_fps_hint()`/`_apply_window_scope_rows(host)`；`stream_capture_hint()` overlay 分支改「暂不支持」；`build_pet_controls()` overlay 下 `stream_capture_check.setEnabled(False)`。 |
| `pet/modern_settings_dialog.py` | +3 / −1 | **整份属于本轮**（B8）。`idle_low_fps` 行文案改调 `settings_pet_controls.idle_low_fps_hint()`；`__init__` 末尾（`_apply_dialogue_scope_rows` 之后）接线 `_apply_window_scope_rows`。依据可复核：HEAD 版 2391 行 + 本文件净 +2 = 工作区实测 **2393 行**，与 B7b 报告「他批 WIP 红：2393 > 2391」完全对上。 |
| `tests/test_overlay_app_hosts.py` | **新增**（321 行，未跟踪） | 本轮新增（B3，10 用例）。 |
| `tests/test_overlay_bubble_wiring.py` | **新增**（138 行，未跟踪） | 本轮新增（B7a，5 例；B7b 扩一条「子宠只重排自己那只」）。 |
| `tests/test_overlay_lifecycle_gaps.py` | **新增**（172 行，未跟踪） | 本轮新增（B7a，6 例）。 |
| `tests/test_overlay_per_slot_settings.py` | **新增**（610 行，未跟踪） | 本轮新增（B7b，18 例，真壳 + 真 spawn + 预写 slot 文件）。 |
| `tests/test_settings_overlay_copy.py` | **新增**（202 行，未跟踪） | 本轮新增（B8，27 条断言覆盖 T1/T2/T3）。 |
| `tests/test_sprite_click_turn_tail.py` | **新增**（176 行，未跟踪） | 本轮新增（B4，4 例）。 |
| `tests/test_sprite_menu_target.py` | **新增**（409 行，未跟踪） | 本轮新增（B2，9 用例；真壳 `spawn_pet` 子宠 + `pet.app` 真实余额/更新实现，仅桩网络边界）。 |
| `tests/test_architecture.py` | +3 / −1 | 本轮（B8 之后收尾小修）：`MODERN_SETTINGS_DIALOG_PY_LINE_BUDGET` 2391 → **2393**，按该文件既有约定随实测校准。 |
| `tests/test_stream_capture_copy.py` | +8 / −8 | 本轮（B8，**改断言**）：`test_stream_capture_copy_says_restart_under_overlay_topology` 原把「overlay 下重启后生效」锁成期望（依据是未落地的 `PHASE4_DESIGN` §T4），改为断言「暂不支持」+「不含重启」；文件头 docstring 同步。这是 B8 唯一改动的既有测试。 |
| `tests/test_sprite_menu_parity.py` | +9 / −5 | 本轮（B2，**改断言 2 处**）：恒真断言 `abs(scale - float(scale)) < 1e-9` → 按 `px` 标签反查 `SCALE_STEPS` 的真断言（sprite scale + 主配置双断言）；`trigger_golden_spin` 桩改带参并断言作用对象 = 主 sprite（契约变更）。 |
| `tests/test_sprite_physics.py` | +119 / −1 | 本轮（B4 +4 例；收尾小修去掉文件尾多余空行——B8 报告 `git diff --check` 命中的就是它）。 |

#### 本轮与更早 WIP 混在同一文件（累计行数**不可按行拆分**）

| 文件 | 累计增删 vs `ebf971e` | 更早量 | 本轮所述改动（**不是**行数归属） |
|---|---|---|---|
| `pet/overlay_shell.py` | +1467 / −118 | 第一轮已记累计 +221 / −5（G1–G5 与更早 WIP 混在一起） | B1 仅 `attach_island` 函数体；B2 **仅 3 处**（`trigger_golden_spin`/`look_at_screen`/`_on_look_done`，+26 / −26，「其余函数一字未动」）；B7a 自述 **+269 净，仅缺口相关函数**；B7b 另改 per-slot 键集 / `_SpriteConfig` / `_SpritePetHost` / `_SpriteSelfTalkHost` / 气泡族 8 个 / self_talk host 5 个 / `switch_character` 族等。四批叠加 + 更早 WIP → **逐行归属未拆分**。 |
| `pet/app.py` | +224 / −28 | 第一轮已记累计 +18 / −2（G1 attach 门与 issue #111 段 WIP 混在一起） | B3 报告自述「**+210 / −27，含本批前既有 WIP**」（`_OverlayChatHost`/`_chat_host`/`AppShell.tray` 属性/`_settings_owner_instance_id`/`_notify_settings_already_open` 等）；收尾小修在 `start()` 后加 `FileInterpretController(self._overlay_shell).offer`（`app.py:1914-1916`）。**不可按行拆分**。 |
| `pet/island_bridge.py` | +107 / −17 | 更早 WIP **+41 / −6** | 本轮 B1：可选 `kinetic` 回调 + `_notify_kinetic()` + `_impulse_floor()`/`_MIN_MEMBER_MASS`。按两份报告累计差可估本轮 ≈ +66 / −11，但**不称精确定值**。 |
| `pet/sprite_behavior.py` | +772 / −29 | 更早 WIP **+471 / −17** | 本轮 B4：`sing_continue_provider`/`_continue_sing`、`_SpriteState` 的 click/turn 三件套 + `landing_pinned`、`_tail_done`/`_clear_tail`、`_warm_landing_idles`/`_unpin_landing_idles`/`_landing_idle_clips`/`_warm_clips`、`_facing_want`、`play_once` 守卫、`on_clip_finished`/`forget`/`_tick_sprite`/`_enter_*`/`_bind_with_gen`/`_play_animation_gap_step`/`_roll_next`。估算同上，**不称精确定值**。 |
| `pet/sprite_sound.py` | +247 / −46 | 第一轮 G3/G3b 已改 **+79 / −31**（同一份报告 §二，非"更早 WIP"） | 本轮 B5（自述相对本批改前快照 **+82 / −20**：`_resolve_path` 分流 / 新增 `_candidates` / `_play` / `on_collision` / 新增 `_hit_floor`）+ B7b（`config_for`/`sprite_for_event`/`on_click(sprite)`/`on_collision(event, sprite)`/多槽候选缓存）+ 收尾小修（`_MIN_MEMBER_MASS`、`_hit_floor` 换算）。 |
| `pet/sprite_bubble.py` | +165 / −6 | 第一轮 G2 +28 / −2 → G8 后累计 **+72 / −4**（§九已记） | 本轮 B6：位置监听对象改为跟随器自身（新增 `__call__`）、`_reposition_if_visible`/`follow_now`/`refresh_anchor`/`reflow`、`close` 改摘除 `self`；B7b：docstring 同步。 |
| `pet/overlay_spawn_state.py` | +92 / −0 | 第一轮 G4 **+32 / −0** | 本轮 B7b：新增 `read_slot_config` / `write_slot_setting`。 |
| `tests/test_island_bridge_velocity.py` | +349 / −12 | 更早 WIP **+305 / −12** | 本轮 B1 改测试为 8ms（125Hz）连喂 4 次。 |
| `tests/test_island_shell_wiring.py` | +211 / −0 | 更早 WIP **+137 / −0** | 本轮 B1 三条真壳 attach 用例。 |
| `tests/test_sprite_bubble.py` | +339 / −4 | 第一轮 G2/G8 累计 **+156 / −3** | 本轮 B6（新增 6 条）+ B7b（1 条 docstring 同步）。 |
| `tests/test_sprite_sound.py` | +404 / −10 | 第一轮 G3/G3b 累计 **+273 / −10** | 本轮 B5（+116，新增 4 用例 + `_recording_player`/`_fire` 辅助）+ 收尾小修（岛击门换算用例）。 |
| `tests/test_overlay_music_sing.py` | +77 / −9 | —（第一轮未列） | B4（改 1 例：原 `rolls=[0.05]` 自证式通过 → 0.85 移动桶 + 注入 provider，增 3）+ B7a（改写 1 例为不手工注入 provider）。**是否含更早 WIP 未核**。 |
| `tests/test_overlay_sprite_settings.py` | +130 / −0 | — | B7a（+4）+ B7b（改写 `test_scale_applies_at_runtime`）。**是否含更早 WIP 未核**。 |
| `tests/test_overlay_tray_icon.py` | +41 / −2 | — | B7a 自述 **+2 / −1 改写**；累计 +41 / −2 明显大于此 → **该文件含本批之外的行，未核**。 |
| `tests/test_overlay_tray_routing.py` | +60 / −0 | — | B7a 自述 +2；累计 60 → **同上，未核**。 |
| `tests/test_overlay_spawn_state.py` | +62 / −0 | — | B7b 自述 +7（纯逻辑读写点）；累计 62 → **同上，未核**。 |
| `tests/test_sprite_animation_gap.py` | +39 / −0 | — | B4 自述 +2；累计 39 → **同上，未核**。 |
| `tests/test_sprite_behavior.py` | +34 / −0 | — | B4 自述 +1；累计 34 → **同上，未核**。 |
| `tests/test_sprite_feeding.py` | +55 / −0 | — | B7a 自述 +3；累计 55 → **同上，未核**。 |
| `tests/test_overlay_instance_gate.py` | +45 / −4 | 更早 WIP **+45 / −4** | 累计值与 §二 记录**逐字相同** → **本轮未触碰本文件**（同理：`tests/test_overlay_peripherals.py` +11 / −19、`tests/test_overlay_shell.py` +136 / −2、`tests/test_session_end_ffmpeg_guard.py` +52 / −2、`tests/test_frameseq_*` / `tests/test_convert_frameseq.py` / `tools/convert_frameseq.py` / `pet/frameseq_provision.py` / `pet/library.py` / `pet/slot_manager.py` / `pet/pet_sprite.py` / `pet/sprite_collision.py` 全部与本轮无关，仅列出以免误判为漏改）。 |
| `docs/INDEX.md` | +2 / −0 | 更早 1 行（架构对照）+ 本报告 1 行（第一轮登记） | **本轮未改**。 |

**注**：`pet/sprite_physics.py` **本轮零改动**——B4 报告明确「放 behavior 而非 sprite_physics：物理侧无该状态对象」；
本轮只在 `tests/test_sprite_physics.py` 加了 4 条用例 + 去 EOF 空行。

#### 未改动（故意）

`pet/collision.py`（数学）、`pet/webm_clip.py`、`pet/frameseq_clip.py`、`pet/tick_governor.py`/`pet/tick_driver.py`
（本轮**未动 tick 间隔**：G6 的修法边界仍是只允许动 tick 间隔，本轮按禁令不碰）、`pet/config.py`
（**未新增键、未新增校验**——per-slot 键集是 overlay 侧的读取口径，不是新配置键）、
`pet/settings_widgets.py`（B8 要灰化禁用态就得改它，超范围故未动）、多进程碰撞残层。

### 性能分析（第二轮）

**先说结论**：本轮**只有 B6 给出了实测数字**（每拖拽 +2 次 `reposition`、offscreen 0.142 ms/次），
其余全部为**结构事实**（可 grep 复现）或**未测**。凡未测的一律写「未测」，不用形容词代替数字。

| 指标 | 实测 | 归属（来源） |
|---|---|---|
| 单次 `reposition`（含 `set_pos`） | **0.142 ms/次**（offscreen，N=200） | 新增（B6，`fix-20260927-B6/REPORT-B6.md` 残留风险 3） |
| 每完成一次拖拽 | **+2 次 `reposition`**（起 / 止，离散事件，**不进常态 tick 路径**） | 新增（B6，同上） |
| 整次拖拽的新增 wall-clock | offscreen **≈ +0.28 ms**；真机按仓库既有口径单次移动 **≈1.5 ms** WM 税（`sprite_bubble.py` V-5 注释）→ **≈ +3 ms/次拖拽**（**推算值，非实测**） | 新增（B6 报告原文） |
| 稳态气泡跟随开销 | **零新增**：30Hz 限频上限不变、无新 timer / 无新线程 / 无新系统调用；`follow_now()` **不写节流时钟**（故起止拍走立即分支而非 33ms 补发） | 新增（B6） |
| 设置页 overlay 行说明补写 | 构建期一次 `findChild` 循环（7 行），无运行期开销 | 既有构建路径（B8） |
| 稳态 CPU / RSS / 内存增长 | **未测**（本轮无任何内存采样；§十 的内存采样属第一轮运行） | 未测 |

**新增路径的绝对成本与触发频率（逐条）**

| 新增路径 | 触发频率 | 绝对成本 |
|---|---|---|
| B6 `follow_now`（气泡起止立即同步） | 每次拖拽 2 次（起步提交 + 松手提交） | 0.142 ms/次（上面实测）；离散事件，不进 tick |
| B6 `reflow` / `refresh_anchor` | 每次「改大小」/「切角色」各 1 次 | **未测**（本批只加方法，B7a 才接上调用方） |
| B1 `note_kinetic`（岛拖拽唤醒 tick 档位） | 岛拖拽期间每次相邻采样位移 ≥ `_MOTION_MIN_STEP` | **未测**；只改 tick 档位判定，不新增计时器 |
| B1 `_impulse_floor()`（冲量门换算） | 每次岛桥碰撞判定 | **未测**；纯算术（乘法），无 I/O |
| B4 落地首帧后台 warm | 每次进入 THROWN 边沿 1 次 | **未测**；复用既有 `_WARM_EXECUTOR`（**不新增线程**），与预测预热**同队列** |
| B7a 碰撞物理 4 键下发 | 每次配置同步（build / 刷新 / spawn / 提升） | **未测**；求解器改为每次 tick 现读 4 个属性（既有 tick 内的读取，非新增循环） |
| B7b per-slot 配置读（`read_slot_config`） | 逐 sprite 取源时；`_refresh_slot_settings_if_changed` **只对签名变了的 slot 重下发** | **未测**；新增磁盘读 |
| B7b per-slot 配置写（`write_slot_setting`） | 子宠设置保存时 1 次 | **未测**；原子写单键到 `config-slot-N.json` |
| B7b 子宠配图预热 | 子宠 spawn 时 1 次 | **未测**；走**共享路径缓存**（同图不重复解码），且用 `_warm_shared_self_talk_images` **不动代次**（不会作废主宠在飞的预热）→ **异图目录才多一次解码** |
| B7b 音效 per-sprite 解析（成员 id→sprite） | 每次点击 / 每次碰撞事件 | **未测**；事件驱动，候选缓存改多槽 `(gate, pack, dir)` |
| B8 文案 / 置灰 | 设置页构建期 | 无运行期开销 |

**新增系统调用 / 网络 / 磁盘 / 线程 / timer（如实逐条）**

- **线程**：**无新增**。B4 的落地首帧后台 warm 复用既有 `_WARM_EXECUTOR`；B7b 的配图预热复用共享路径缓存。
- **网络**：**无新增**（本轮零联网路径）。
- **磁盘**：**新增 2 条**（B7b）——子宠 per-slot 配置的**读**（`read_slot_config`，逐 sprite 取源时）与
  **原子写**（`write_slot_setting`，子宠设置保存时 1 次）。其余批无新增磁盘 I/O。
- **常驻 timer：无新增常驻高频表**，但有 **2 处必须如实列出**：
  1. **B7b 新增 per-子宠「单发」QTimer**（`_SpriteSelfTalkHost._self_talk_timer`，`QTimer(shell)` +
     `setSingleShot(True)`，`overlay_shell.py:437-439`）——**N 只子宠 = N 个 timer 对象**；
     **不是**常驻高频：每次冒泡后重排下一次，与旧版（`window.py:458-480` + `:740`，每窗各自计时）同构。
     实际频率由该 sprite 的 `self_talk_min_interval` / `self_talk_max_interval` 决定 —— **具体频率未测**。
     主宠仍走壳自身既有的 `_self_talk_timer`（`overlay_shell.py:1406`，历史行为逐点不变）。
  2. **B7a 托盘图标轮询改策略**（`overlay_shell.py:119-121`）：`_TRAY_ICON_POLL_MS = 500`、
     `_TRAY_ICON_POLL_BUDGET = 20`、`_TRAY_ICON_SLOW_POLL_MS = 5000`。
     改动前 = 20 拍（≈10s）后**永久停表**（永不自愈）；改动后 = 超预算**降频到每 5s 一次**，
     直到真的拿到帧才停表。**timer 对象本身是既有的**（`_tray_icon_timer`），本轮只改停表策略——
     但**病态路径下由「停表」变成「每 5s 一次常驻轮询」**，这是本轮唯一新增的常驻低频活动，如实登记。
     改写旧断言 1 条：`test_tray_icon_poll_gives_up_after_budget`（原把「20 拍永久放弃」锁成期望）。
- **内存与缓存**：**未测**。结构上的新增小对象有——B7b 的 `_bubble_followers` dict（每 sprite 一个 follower）、
  每子宠一个 `_SpriteSelfTalkHost` + 一个 `_SpriteConfig` 视图、音效候选缓存改多槽键；
  B4 的起飞 pin 由 `_SpriteState` 内的 clip 清单**强引用到落地 / `forget`**（飞行中换角色时旧库 clip
  延迟释放，与旧机同量级）。**以上均无量测数字。**

**结论（逐条回答模板 §四 的四问）**：① **稳态开销**：B6 明确零新增（30Hz 上限不变），其余批未测 → 整体**未测**；
② **新增路径绝对成本与频率**：见上表，只有 B6 的 0.142 ms/次是实测；③ **新增系统调用/网络/磁盘/线程/timer**：
无新增线程/网络；新增 2 条 per-slot 磁盘读写；新增 N 个**单发**子宠 timer + 托盘病态路径下 5s 低频轮询；
④ **内存与缓存增长**：结构上有新增小对象，**量未测**。**卡顿方向本轮零进展**（用户叫停、另立任务）。

### 实机运行记录（第二轮）

**本节首先声明：本轮 8 个批次 + 3 处收尾小修，全部在「禁起桌宠、禁 `python -m pet`」的纪律下完成**
（`DISPATCH-COMMON.md` 原文逐字：「**禁止全量 pytest、禁止起桌宠、禁止 python -m pet**」），
证据层只到 **offscreen Qt + 合成 `QMouseEvent` + 真实控件 / 真实 Config / 真实壳 / 真实 `spawn_pet` +
打桩音频后端与桩网络边界**。因此下面**没有用户可见行为的实机确认**，也不把 offscreen 当实机。

**① 全量门禁（本轮所有改动之后，唯一一次全量）**

| 门 | 命令 / 方法 | 真实结果 |
|---|---|---|
| 全量 pytest | `QT_QPA_PLATFORM=offscreen`，cwd = 本 repo，Python 3.13.7 `.venv`，`-q -p no:cacheprovider`，未用 xdist | **`rc=0`** → **`3826 passed, 11 skipped, 270 warnings in 436.22s (0:07:16)`** |
| 证据（独占目录） | `.scratch/windows-parity-20260926-a/full-suite-20260927-c/` | `rc.txt` = `rc=0`；`pytest.txt` 末行即上表数字；另有 `worktree.txt`（跑前跑后工作树一致，34 项已改 + 15 项未跟踪）与 `tmp/` |

**口径**：这是**这一棵树、这一时刻**的数字。第一轮 §十 记的 **3708 passed / 11 skipped** 是更早时刻；
两者**不得互替**（差 +118 与本轮新增的 7 个测试文件 + 各批加例方向一致，但两次数集不同，**不称等价增量**）。
历史 **3638 passed** 更不得迁移。11 条 skipped 的**身份仍未列**（`-q` 不输出原因，未为列原因重跑）。

**② 各批聚焦红→绿（不同命令、不同文件集，不可相加成唯一总数）**

| 批 | 红（修复前） | 绿（修复后） | 相关族 / 宽域 | ruff |
|---|---|---|---|---|
| B1 岛拖拽 | 红由 3 个语义探针证明（`head_semantics_check.py`：岛速 `0.0`；`prefix_semantics_check.py i2/i3`：tier 2→2、j=32.5 无 bump），非 pytest 计数 | **75 passed**（必跑 4 文件） | **51 passed**（attach_island / IslandWindowBridge 消费者） | All checks passed |
| B2 菜单作用对象 | **6 failed**（新用例）+ 1 failed（parity 桩签名）+ 21 passed | **78 passed**（派发 5 文件） | **226 passed**（追加 8 文件） | 4 文件全绿 |
| B3 app 宿主 | **8 failed, 1 passed**（1.82s） | **10 passed**（1.70s） | 派发 12 文件 **386 passed**；直接消费者 18 文件 **542 passed, 1 skipped** | All checks passed |
| B4 动画 | **11 failed / 78 passed** | **161 passed**（10 文件聚焦集） | 同批 import `sprite_behavior` 的 8 个既有文件 **136 passed** | All checks passed |
| B5 音效音源 | **4 failed / 33 passed**（4 个新用例全红、存量 33 全绿） | **37 passed** | 相关面合并 **167 passed, 1 skipped** | All checks passed |
| B6 气泡 | **5 failed, 11 passed**（**最终测试码** + 运行时回滚本批产品改动，防「测试跟着实现漂」） | **16 passed** | 规定三件套 **42 passed**；相关族 95 / 67 / 109 / 178+1skip 全绿 | 3 文件全绿 |
| B7a 壳接线 | **22 failed / 44 passed**（用 `revert_b7a_hunks.py` 临时回退本批 hunk 得到；产品文件已 sha256 复原） | **66 passed**（本批文件）/ **112**（派发清单）/ **428**（宽域） | 宽域 `-k overlay/sprite_menu/sprite_bubble/sprite_feeding/island_shell/file_eater` | All checks passed |
| B7b per-slot | **24 failed / 3 passed**（`red_probe_plugin.py` 在**运行期**短路回改动前——本仓有他批未提交 WIP，不能整体回退产品文件；通过的 3 条是改动前就有的「缺文件/损坏/坏值回退」语义） | **398 passed**（派发清单）/ **130**（本批 8 文件）/ **308**（overlay 串行）/ **90**（sprite 家族） | 额外相关族 **138 passed + 1 failed**（失败的正是 `test_architecture.py::test_modern_settings_dialog_py_line_budget` 2393 > 2391，随后由收尾小修校准预算转绿） | 9 文件全绿 |
| B8 文案 | **12 failed / 15 passed** | **418 passed, 1 skipped**（18 个设置/回归文件） | — | All checks passed；`git diff --check` 对本批 3 文件 exit 0 |

**③ 边界与失败路径（真实观察到的「本该失败」）**

- **B8 置灰有效性**：`test_disabled_stream_capture_ignores_clicks_but_legacy_toggle_works` **真发鼠标点击**——
  overlay 置灰后勾选态不变，legacy 对照组**点得动**（证明点击确实送达、断言非空转）。
- **B8 非 GUI 渲染检查**（`render_check.py`，不启桌宠、不跑 `python -m pet`）：overlay + `slot-1` 设置页、
  win32 口径、640/900/1100px 三档 × 常规/桌宠/互动 域切页后测量——无缺行、无「缺生效范围说明」、
  `hint.height() >= heightForWidth(width)`（无裁切，含两行文案行）、`stream_capture_check.isEnabled() == False`；
  位图证据 `render-{常规,桌宠,互动}-{640,900,1100}px.png`（9 张）。
- **B1 残留缺口的真实探针值**：B1 期间探针实测 `sprite_sound` 岛 pair 音效闸门 = **60.0** 而 j = **32.5**
  → **放行 False**，即桥已放行但音效侧再吞一次；该缺口随后由 S2 + 收尾小修（dv × 最小质量）闭合，
  用例 `tests/test_sprite_sound.py::test_light_pet_island_hit_below_raw_dv_floor_still_sounds`。
- **显式豁免记录**：B2 期间的 `related-run-foreign-wip-failure.txt` 记了
  `test_overlay_spawn.py::test_spawn_and_clear_pets` 的 `_unpin_landing_idles` AttributeError——
  那是 B4 **正在并发写** `pet/sprite_behavior.py` 的瞬时状态，重跑 18 passed，**非本批引入**，已登记不误判。

**④ 明确未实机验证项（本轮全部）**

下表每一项都只有 offscreen / 合成事件 / 打桩后端的证据，**观感与出声必须实机复核一眼才算验过**：

| 项 | 本轮到达的证据层 | 为什么不能自动 / 实机要看什么 |
|---|---|---|
| **拖岛撞鱼**（岛速不被清零、弹开、THROWN） | 真 `SpriteCollisionWorld` + 真岛桥，合成 8ms 拖拽事件（B1） | 合成事件给不出真 8–16ms 鼠标节奏与观感；要看真拖岛时鱼的弹开与位移 |
| **气泡跟手**（拖拽起止立即同步） | offscreen + 合成 `QMouseEvent`，`follow_now` 逐帧断言（B6） | 真机走 `SetWindowPos`（≈1.5ms WM 税/次）——B6 报告原文即写「真实 SetWindowPos 的跟手观感需实机一眼」 |
| **分宠音效**（子宠用自己那份配置发声） | 真壳 + 真 `spawn_pet`，**音频后端打桩**（B5/B7b） | 打桩层听不到声；要实机确认每只宠各自的音量/音源包真的出声 |
| **子宠切角色** | 真壳 + 真 spawn，库替换与 slot 文件写入断言（B7b） | 断言只证「库换了、文件写了」；要看画面与素材真的换 |
| **子宠气泡 / 子宠自言自语** | 真控件 + offscreen（B7b） | 要看气泡落点是否贴在各自头顶、单发 timer 的节奏观感 |
| **托盘图标**（兜底图标 / 自愈 / 降频） | 真壳 + 改写后的轮询断言（B7a） | 要看图标真的出现、5s 降频后仍能自愈；`ToggleSwitch` 自绘**不区分禁用态**，视觉提示只靠文案 + tooltip（要灰化需改 `settings_widgets.py`，超范围） |
| **设置页观感**（T1/T2/T3 文案、置灰、行说明） | offscreen 位图 640/900/1100px × 3 域 + 几何断言（B8） | **交互式视觉未人眼验收**（按 DISPATCH-COMMON 禁起桌宠） |
| **岛拖拽唤醒 tick / 甩岛过鱼** | 语义探针断言 `applied_tier` 0↔2（B1） | 要看「甩岛过鱼真的结算」的可感效果 |
| **屏迁移保气泡 / scale 运行期生效 / 碰撞物理 4 键** | 真 Config + 真壳 + 真 spawn + 真实 Qt offscreen（B7a） | 要真改分辨率 / 真拖滑块看观感 |
| **拖文件解读** | 接缝 + 真壳（B7a/O9） | 要真拖一个文件到宠身上 |

**⑤ 卡顿线：本轮零处理（明确）**

- **偶发卡顿不在本轮范围**：GAP-LIST「不修/登记」第 5 条逐字为「**偶发卡顿：用户叫停，另立任务**」。
  本轮**没有**跑卡顿轮次、**没有** py-spy、**没有**内存采样、**没有**新增任何卡顿测量结论。
- 第一轮 §四 的卡顿记录（正式轮 0 轮、`jank-result.json` 缺落盘、py-spy 未 attach）**状态不变**；
  §十 的内存水位（峰值 99.6%）属第一轮那次运行的采样，**不能**当本轮的性能证据。
- 因此本节不写「已优化 / 已丝滑 / 卡顿已解决」，也不写「卡顿仍在」——**未测**。

**⑥ 本轮遗留的文档同步缺口（登记，不在本轮文件范围）**

- `.scratch/single-overlay-window/PHASE4_DESIGN.md` §T4 仍写「overlay 下勾选捕获模式 = 重启级切换」，
  与现状（**暂不支持**，B8 已按实际行为置灰 + 改文案）**相反**；`docs/PR-REPORT-OVERLAY-REVIEW-FIXES-2026-09-24.md`
  的历史记录也如此。文档不在批次文件范围，**留给拓扑文档收口者改判**。
- `tests/test_island_icon_routing.py:117` 的注释仍写「回退系统标准图标」（断言仍过，文件不在 B7a 范围）。
- `docs/INDEX.md` 中本报告的摘要行只描述了第一轮内容，**未追加第二轮**。

## 十二、新架构优化（2026-09-27）

> **本节是「功能继承收口（§一–§十一）之后」的新架构优化阶段记录。** 计划原文
> `.scratch/windows-parity-20260926-a/OPT-PLAN-20260927.md`（基于 6 路只读审计，只做低风险、
> 可机测、**不降可见帧率**的项）。批次纪律承 §十一：**不增常驻高频 timer、不新增线程、
> 不改帧时序语义、不新增常驻无界缓存**。
>
> **状态**：功能继承（第一轮 G1–G5 + 第二轮 B1–B8）+ 本阶段优化 O1–O5 均已收口；
> **最终全量已跑**：全量 pytest rc=0：3911 passed / 11 skipped / 0 failed / 0 error（446.42 s），ruff 全绿、git diff --check 通过；证据 `.scratch/windows-parity-20260926-a/full-suite-20260927-e/`（撤回 pinned 之后、本轮全部改动之后）。本地 PR 说明草稿见 §十三。
>
> **结论先说（必须如实读）**：优化的**实测收益集中在隐藏 / 锁屏挂起 / 后台三类不可见状态**
> （离线 bench：隐藏期 `tick_sim` 312→14、帧推进 119→0、进程 CPU 降 54–81%；锁屏 `tick` 312→0；
> 隐藏期穿透刷新 100→0、光标探测 16→0；可见静止 `GetWindowLongW` 99→1/s；DSH 关时 loopback
> connect 10→0/10s、线程 4→0；overlay 共享全屏线程每秒空醒 12→0；帧路径 `QPixmap.fromImage`
> 240→0/240 帧、上屏 `_apply` p50 0.2→0.018 ms、帧 0 解码 2→1）。
> **但在真机可见常态（三宠待机 / 三宠移动）下，这些改动落在噪声内——既没有显著提升，
> 也没有退步**（详见下文真机 A/B 表）。

**批次划分**（各批文件不重叠，串行 / 成对执行）：

| 批 | 主题 | 文件 |
|---|---|---|
| O1 | 帧路径 | `pet/frameseq_clip.py`、`pet/pet_sprite.py` |
| O2 | 隐藏期轮询 / 穿透态缓存 / 会话过滤器窄读 | `pet/platform_win.py`、`pet/overlay_peripherals.py`、`pet/overlay_window.py`、`pet/session_watcher.py` |
| O3+O4 | 逐只·整窗隐藏降载 + 锁屏/挂起降档 | `pet/tick_driver.py`、`pet/pet_sprite.py`、`pet/frameseq_clip.py`、`pet/webm_clip.py`、`pet/session_watcher.py`、`pet/overlay_shell.py` |
| O5 | 后台常驻 | `pet/app.py`、`pet/multi_window_shared.py`、`pet/dsh_state.py` |

**未入选（计划原文登记，不在本阶段范围）**：跨宠帧共享 / 解码扇出（中风险，下一轮）、
AC 下 T1 满速（用户拍板过，不动）、扩大 FrameSeq 覆盖 `random`（磁盘成本，需用户决定）、
全屏合成窗结构税、旋转脏区多边形、首跑预热风暴让路、无戳旧帧集清理（需用户决定删除策略）。

### 修改文件说明（优化）

**归因口径（承 §二 / §十一，不新增规则）**：① 「累计增删」= `cd /d/dsh-pet-src && git diff --numstat`
（相对基线 `ebf971e`）的**整文件累计值**，不是本阶段增量；② 本阶段增量只在**批次报告留存过该数字**
时才写，否则写「不可拆分」——工作区含更早多轮未提交 WIP，**不把整文件 diff 归给本阶段**；
③ 归属依据 = 各批留存报告 / 改动前逐字节副本 / 红绿记录，**不以文件 mtime 作证明**。

#### O1 帧路径（`fix-20260927-O1/`）

| 文件 | 本批自述增量 | 累计 vs `ebf971e` | 是否混有更早 WIP |
|---|---|---|---|
| `pet/frameseq_clip.py` | +72 / −9（批内快照口径） | +98 / −11 | **混**：另含 O34 的 `_paused` / `pause` / `resume` 与「撤回 pinned 首帧保留」（下 c 项）。**逐行归属未拆分** |
| `pet/pet_sprite.py` | +31 / −11\*（\*批报告原文即注明：该 numstat 含工作区里其它批的 WIP `ffmpeg_recycle_minutes`；本批**只动 `_rebuild_pixmap`**） | +84 / −13 | **混**：另含第一轮 G5 与 O34 的 `pause_clip`/`resume_clip` |
| `tests/test_frameseq_clip.py` | +264 / −4（8 新例 + 2 个计数探针夹具） | +309 / −4 | **混**：另含撤回后的 2 处用例改写（c 项） |
| `tests/test_sprite_dpr.py` | +133／−0（3 新例：恒等短路、反向守门与链路顺序、flipped 轴向 + 命中图不别名） | +133 / −0 | 否 |
| `tests/test_overlay_window.py` | +87 / −1（1 新例：真 overlay `paintEvent` 渲染，每帧零 `fromImage`） | +110 / −1 | **混**：另含第二轮 B6（+29 / −0） |
| `tests/test_frame_path_waste.py` | **新增（未跟踪，257 行，4 例）** | — | 否 |

O1 逐条改动：① `FrameSeqClip._apply` 只存 QImage + 帧号，`currentPixmap()` 惰性构建并按帧缓存
（新帧到货即失效），全仓消费者仍拿到**同一帧非空 pixmap**；预热线程不再在非 GUI 线程建 QPixmap。
② `PetSprite._rebuild_pixmap` 两步恒等短路（格式已是 ARGB32_Premultiplied 不 `convert`；目标物理尺寸
== 源尺寸不 `scaled`）+ `mirrored(True, False)` → `flipped(Qt.Orientation.Horizontal)`。③ `warm_first_frame`
解出的帧 0 寄存 `_pending[0]`，`start()` 在显示槽已是帧 0 时原地复用、只补发一次 `frameChanged(0)`。
④（**已撤回，见 c**）`clear_display_frame` 在 pinned 时保留当前 QImage。⑤ `stop()`/`clear_display_frame()`
清 `_pending`（`_wanted` 在途标记照旧保留）。

#### O2 隐藏期轮询（`fix-20260927-O2/`）

| 文件 | 本批自述增量 | 累计 vs `ebf971e` | 是否混有更早 WIP |
|---|---|---|---|
| `pet/platform_win.py` | +62 / −1 | +69 / −1 | 未核（本阶段前该文件不在 §二/§十一 变更清单内） |
| `pet/overlay_peripherals.py` | +82 / −4 | +106 / −4 | 未核（同上） |
| `pet/overlay_window.py` | +28 / −5 | +68 / −5 | **混**：第二轮 B6（+29 / −0）+ 主代理小修 a（`_note_user_input`） |
| `pet/session_watcher.py` | +27 / −6 | +200 / −16 | **混**：O34 的挂起/锁屏分支（同一文件同阶段另一批） |
| `tests/test_input_controller_poll_tiers.py` | +117 | +119 / −2 | 未核 |
| `tests/test_overlay_peripherals.py` | +103（新增闸门 4 例） | +102 / −20 | **混**：第二轮记录过更早 WIP +11 / −19 |
| `tests/test_overlay_hidden_polling.py` | **新增（未跟踪，218 行）** | — | 另有主代理小修 b |
| `tests/test_session_watcher_message_read.py` | **新增（未跟踪，109 行）** | — | 否 |

O2 逐条改动：① `platform_win.py` 新增 `_apply_through`（穿透态缓存：句柄 / 目标态 / `mouse_through`
三者未变**且**未到 `RECHECK_EVERY_N_REFRESHES=100` 次低频校正窗口 → 直接返回，不再 `GetWindowLongW`）、
`_invalidate_through_cache`、`resume()`（与 `stop()` 对称：复位缓存 + 立即 refresh + 重开表）。
② `overlay_peripherals.py` 新增 `OverlayVisibilityGate`（进程级可见 overlay 登记，弱引用窗口 +
`weakref.WeakMethod` 订阅 `FullscreenCursorWatcher.on_overlay_visibility_changed`）与
`note_overlay_visibility`/`visible_overlay_count`；光标探测表改为「配置门开 **且** 至少一个 overlay 可见」
才跑，恢复显示时立即补一次 `_poll_cursor`；**全屏 1Hz 表不动**（那是全屏避让后恢复显示的唯一路径）。
③ `overlay_window.py` 新增 `hideEvent`（停穿透轮询 + 上报不可见）、`showEvent` 改为「上报可见 →
控制器不存在则建、存在则 `resume()` → 每次显示补 `_set_windows_no_activate`」。④ `session_watcher.py`
先按 `_WinMsg.message.offset`（ctypes 布局算出，不硬编码）**窄读 4 字节 `message` 字段**，确认是
`WM_QUERYENDSESSION`/`WM_ENDSESSION` 才整结构解析（解析失败仍返回 reason，绝不漏关机）。

#### O3+O4 隐藏 / 锁屏降载（`fix-20260927-O34/`）

**本批无数量归属**：批报告原文写明「`git diff --numstat` 无法隔离本批增量（工作区带前面各批未提交
WIP，禁 stash），故只列文件与函数」。改动文件与函数（照抄批报告）：

- `pet/tick_driver.py`：`_suspended`、`_sprite_visible` / `_visible_for_tier`（新）、
  `note_sprite_visibility_changed`（新）、`_sync_tier` 挂起短路、`suspended` / `set_suspended`（新）。
- `pet/pet_sprite.py`：`_clip_paused`、`pause_clip` / `resume_clip` / `clip_paused`（新）、
  `bind_clip` / `restart_clip` 尾部（隐藏中换绑重压暂停）。
- `pet/frameseq_clip.py` / `pet/webm_clip.py`：`_paused`、`pause` / `resume`（新）、
  `start`（/`_rearm_loop_reader`/`set_playback_speed`）守卫。
- `pet/session_watcher.py`：新常量、`_suspend_state` / `session_power_event`（新）、
  `_wts_register/_wts_unregister_session_notification`（新 win32 边界）、`nativeEventFilter` /
  `_report_suspend`、`register/unregister_session_notifications`（新）、`install_session_watcher`（+参数）。
- `pet/overlay_shell.py`：`set_sprite_visible`（+节拍/通知）、`_set_sprite_clip_paused`、
  `_set_all_clips_paused`、`_note_sprite_visibility_changed`、`_all_libraries`、`_pause_warm_all` /
  `_resume_warm_all`（新）、`set_pet_visible` / `_on_fullscreen_changed`（+成对分支）、
  `_install_session_watcher` / `_register_session_notifications` / `_on_suspend_changed`（新）、
  `_on_about_to_quit`（+反注册）。
- 测试：`tests/test_session_lock_suspend.py`（**新增，未跟踪，334 行**）、`tests/test_tick_driver.py`
  （累计 +284 / −0）、`tests/test_sprite_visibility.py`（累计 +298 / −0）。新增测试 58 条。

`pet/tick_governor.py` **本批零改动**（T3 复用既有分支，不新增机制）。

#### O5 后台常驻（`fix-20260927-O5/`）

| 文件 | 本批自述增量 | 累计 vs `ebf971e` | 是否混有更早 WIP |
|---|---|---|---|
| `pet/app.py` | +43 / −1 | +267 / −29 | **混**：第二轮 B3 已记「+210/−27 含本批前既有 WIP」；不可按行拆分 |
| `pet/multi_window_shared.py` | +13 / −1 | +13 / −1 | 否（该文件不在 §二/§十一 清单内） |
| `pet/dsh_state.py` | +5 / −2（**纯注释**：类/模块 docstring 由「始终轻量运行」改写为「生命周期由 app 按 `agent_link.dsh` 掌握」） | +5 / −2 | 否 |
| `tests/test_background_service_gates.py` | **新增（未跟踪，258 行，9 例）** | — | 否 |
| `tests/test_overlay_app_hosts.py` | +36（1 例） | 新增（未跟踪，359 行） | 本轮新增文件，B3 建、O5 加 1 例 |

O5 逐条改动：① `AppShell._dsh_tracker_wanted` / `_sync_dsh_state_tracker`，`start()` 改为调后者，
`_apply_external_config_change()` 末尾同步一次 → `DshStateTracker` 只在 `agent_link.dsh` 为真时运行。
② `SharedSubsystems.start()` 按 `overlay_settings_command.is_overlay_topology()` 门控共享全屏 watcher
（legacy 逐位不变）。③ config 目录指令消费在 app 侧对 overlay 让路（原实现会随机摘走指令 →
设置页「一键退出子肥鱼」静默失效）；两条 `QFileSystemWatcher` 职责不同，按派发口径**保留不改**。

#### 主代理直接做的小修（本阶段收尾，a–d）

**a. 挂起自愈（防解锁消息丢失后卡 T3+停播）** — `pet/tick_driver.py:458` 新增
`note_user_input()`：挂起态下用户按下/右键即解除挂起（优先走宿主注入的 `on_user_resume`，
缺省直接 `set_suspended(False)`；非挂起态 no-op）。`pet/overlay_window.py:160` 新增
`_note_user_input()`，由 `mousePressEvent`（`:577`）与 `contextMenuEvent`（`:589`）调用。
`pet/overlay_shell.py:4384` 安装会话探测器后给 driver 注入
`on_user_resume = lambda: self._on_suspend_changed(False, "user-input")`——走**完整**
`_on_suspend_changed(False)`（含续预热），不只降档复位。`set_on_top`（`overlay_shell.py:2884`）与
`_migrate_to_screen`（`:4297`）重建原生窗口后重新 `_register_session_notifications`
（原生 HWND 换新，旧锁屏注册随之失效）。测试 `tests/test_tick_driver.py` 新增 2 例
（`test_user_input_self_heals_stuck_suspend`、`test_user_input_prefers_host_resume_hook_and_is_noop_when_awake`）。

**b. `tests/test_overlay_hidden_polling.py` 顺序隔离** — autouse fixture `_isolate_visibility_gate`
（`:75-87`）每例把进程级可见性登记置空、结束后还原：跨文件残留「show 过但未 close 的可见 overlay」
会让本文件 4 例顺序相关失败。计数断言同时由绝对计数改为**相对基线**（先记录可见期计数，再断言
隐藏期增量 == 0）。只隔离测试间残留，**不改产品语义**。

**c. 撤回 O1 第 4 项（FrameSeqClip pinned 首帧常驻）** — 真机 A/B（b 组）实测：三宠待机私有内存
**161.6 → 179.1 MB（+17.5 MB）**、单宠 **134.4 → 141.0 MB（+6.6 MB）**，与「7 段 pinned × 每宠一库 ×
0.88 MB」吻合；换来的只是**一次 ~1.2 ms 的帧 0 解码**（帧序列冷解码本来就快，与 WebMClip 不同，
不值得常驻）。撤回后（c 组）三宠待机私有 **161.2 → 164.4 MB**（噪声级）。落地：`pet/frameseq_clip.py`
`clear_display_frame` 对 pinned clip 也清（惰性 pixmap 一并丢）；`tests/test_frameseq_clip.py` 对应用例
改为 `test_clear_display_frame_releases_pinned_first_frame`，`test_retained_frame_is_not_reused_as_frame_zero`
改用 `stop()` 保留显示槽。**O1 其余 4 项不受影响。**

**d. `AGENTS.md`（+4 / −1）** — 在「两种渲染拓扑」段补一句：overlay 拓扑下**共享全屏 watcher 不启动**
（overlay 壳自带 `FullscreenCursorWatcher`），且 `DshStateTracker` **只在 `agent_link.dsh` 开启时运行**。

#### 未改动（故意）

`pet/collision.py`（数学）、`pet/tick_governor.py`（O34 复用既有 T3 分支）、`pet/config.py`
（未新增键、未新增校验）、多进程碰撞残层。`pet/window.py:1986` 仍是废弃的 `mirrored(True, False)`
（legacy 窗口路径，不在 O1 文件范围，轴向等价、只有 DeprecationWarning）。

### 性能分析（优化）

**分两类口径**：① **离线 bench**（offscreen 真事件循环 / 真素材，**不启动桌宠**）；② **真机 A/B**
（runner，见「实机运行记录（优化）」）。**两类不混用**，也不把离线数字当成真机结论。

#### ① O1 帧路径（真素材 `assets/characters/shenshen/frameseq/idle/待机呼吸休闲`，241 帧 640×360@24fps，每档 240 帧，耗时列为 3 次重复的中位数；原件 `fix-20260927-O1/BENCH-frame-path.txt`）

| 档位（240 帧） | 变体 | `fromImage` 次数 | 帧解码 | 帧 0 解码 | 上屏 `_apply` p50 | 重建 p50 / p95 |
|---|---|---|---|---|---|---|
| A scale=0.72 dpr=1.0 冷起播 | before | 240 | 242 | 2 | 0.2010 ms | 0.562 / 0.843 |
| A 同上 | after | **0** | 241 | **1** | **0.0184 ms** | 0.452 / 0.632 |
| A scale=0.72 dpr=1.0 预热起播 | before | 240 | 242 | 2 | 0.0668 ms | 0.381 / 0.538 |
| A 同上 | after | **0** | 241 | **1** | **0.0056 ms** | 0.402 / 0.524 |
| B scale=1.00 dpr=1.0 恒等档 | before → after | 240 → **0** | 242 → 241 | 2 → **1** | 0.0757 → 0.0058 | 0.127 → 0.144 |
| C scale=1.00 预乘源 | before → after | 239 → **0** | —（C 档帧源非 `FrameSeqClip` 实例，不同口径） | — | 0.0785 → 0.0056 | 0.156 → 0.152 |
| D scale=0.72 朝右（镜像） | before → after | 240 → **0** | 242 → 241 | 2 → **1** | 0.0658 → 0.0067 | 0.523 → 0.537 |
| E scale=0.72 dpr=1.5（HiDPI） | before → after | 240 → **0** | 242 → 241 | 2 → **1** | 0.0701 → 0.0072 | 1.164 → 1.192 |

变换级微基准（真帧 640×360，p50 / p95 ms）：`QImage(path)` 解码 1.2503/1.4637、
`convertToFormat ARGB32→Premult` 0.0397/0.0532、`convertToFormat Premult→Premult（短路命中）` 0.0014/0.0015、
`mirrored(True,False)` 0.0937/0.0992 vs `flipped(Horizontal)` 0.0923/0.1026、
`scaled 640×360→640×360` 0.0019/0.0022、`scaled →461×259` 0.2772/0.305、
`QPixmap.fromImage(预乘)` 0.0012/0.0014、`QPixmap.fromImage(ARGB32 直通=素材真实格式)` 0.0377/0.0546、
`QImage.copy()` 0.0446/0.0482。

读数结论（批报告原文口径）：(a) 每 240 帧 GUI 线程少 240 次 `QPixmap.fromImage`；素材真实格式是
直通 ARGB32，`fromImage` 需隐式转换 → 单次 0.0377 ms ⇒ **≈ 0.06 ms/帧 GUI 线程时间**
（24fps 下 ≈1.5 ms/s/只）；语义零变化。(b) **每次起播少解一帧 0**（242→241，帧解码 1.25 ms/帧），
且起播时帧 0 立即可用（不再等一次线程往返）。(c) **O1-2 恒等短路的实测收益只有 µs 级**
（重建 p50/p95 各档都落在重复测量噪声内：Qt 自己对同格式 `convert` 1.4 µs、同尺寸 smooth `scaled`
1.9 µs 已短路）——保留它是「不再白调 API + 未来尺寸画像变化时自动省」，**不是本批可测收益来源**。

#### ② O2 隐藏期轮询（offscreen 真事件循环，1000 ms 窗口；`fix-20260927-O2/bench-before.json` / `bench-after.json`）

| 指标（1 s 窗口） | 改前 | 改后 |
|---|---|---|
| 隐藏期穿透 refresh 次数 | 100 | **0** |
| 隐藏期 `GetWindowLongW` 次数 | 100 | **0** |
| 隐藏期光标可见性探测次数 | 16 | **0** |
| 可见静止（盒内 10 ms 档）refresh 次数 | 99 | 99（帧率不变） |
| 可见静止 `GetWindowLongW` 次数 | 99 | **1** |
| 会话过滤器单条非会话消息耗时 | 0.974 µs | **0.362 µs**（窄读 0.253 vs 整结构 0.801） |

真机句柄核对（真 Win32、真 HWND，**未起桌宠 / 未显示窗口**；`probe-real-hwnd.json`）：命中不透明
像素位 = 1 / 空处 = 0 / `stop()` → 0 / `resume()` → 立即 1；未知外部改写 ≤100 次 refresh 自愈；
`mouse_through` 变化当拍重放。

#### ③ O34 隐藏 / 锁屏降载（offscreen 真 driver + 真 sprite + 真 `FrameSeqClip` 素材 400 帧@24fps；每臂 5 s 窗口 + 1 s 预热；`fix-20260927-O34/BENCH-final.txt`）

| 5 s 窗口 | `tick_sim` 调用 改前→改后 | clip 帧推进 改前→改后 | 进程 CPU 改前→改后 | 恢复后首 tick | 隐藏期帧号 |
|---|---|---|---|---|---|
| 逐只藏光全部 | 312 → **14** | 119（23.8 fps）→ **0** | 343.8 ms → 156.2 ms（**−55%**） | 1.8 ms（T1）→ 17.4 ms（T0 满速） | 23→142 照跑 / 23→23 **冻结不回 0** |
| `set_suspended(True)` | 312 → **0** | 119 → **0** | 453.1 ms → 140.6 ms（**−69%**） | 1.0 ms（T1）→ 17.1 ms（T0 满速） | 同上 |
| 可见路径（都不藏，对照） | 312 → 313 | 119 → 119（23.8 fps） | 359.4 ms → 656.2 ms（**噪声重叠**，同机并行负载） | — | — |

规则成本微基准（真 overlay + 真 sprite，2000 次 × 5 轮取 min）：可见性判定 **0.52–0.60 µs → 1.90–1.98 µs**
（+1.4 µs/tick；170 Hz 下 = **每核 +0.024%**）；可见帧率 / 帧数实测**完全不变**。
批报告同时登记「机上噪声说明」：`process_cpu_ms` 同条件重复跑散布大（本机同时有其它代理在跑），
故结论只取确定性量（tick 次数、帧数、帧号、恢复后首 tick 间隔），CPU 只作量级参考。

#### ④ O5 后台常驻（默认配置；offscreen 真进程 + 真事件循环，10 s 窗口；`fix-20260927-O5/bench_background_residency.py`）

| 指标 / 10 s（默认配置） | 改前 | 改后 |
|---|---|---|
| (a) tracker `is_running` 调用（loopback connect，DSH 离线） | 10 | **0** |
| (a) 同上（DSH 在线 `O5_DSH_ONLINE=1`） | 5 | **0** |
| (a) `dsh-online-probe` 线程启动次数 | 4 | **0** |
| (a) 1.2 s 桥事件轮询 tick | 10 | **0** |
| (a) 桥目录 glob / 文件读（DSH 在线时） | 10 / 10 | **0 / 0** |
| (b) overlay：`pet-shared-fs-watch` 线程 / 循环唤醒 | 存在 / 12 | **不存在 / 0** |
| (b) legacy：同上（对照，必须不变） | 存在 / 12 | 存在 / 12 |
| (c) 一次外部保存 → `_apply_external_config_change` | 1 | 1（不变） |
| (c) overlay：一次保存 app 侧真消费指令次数 | 2 | **0**（归壳） |
| (c) legacy：同上（对照，必须不变） | 2 | 2 |
| (c) 监视配置目录的 watcher（app 侧 start 时装） | 1 | 1（壳侧另 1，职责不同） |

#### ⑤ 稳态开销 / 新增路径频率 / 有无新增 timer·线程·系统调用（逐条回答模板四问）

- **有没有新增常驻 timer？** **没有**。本阶段所有新机制都挂在**既有**事件 / 既有定时器上：
  O34 的档位规则跑在既有 tick 内（+1.4 µs/tick）；O2 的可见性闸门由既有显示/隐藏事件驱动；
  O5 是**减**表（共享全屏线程不再启动）。唯一「新增计时器」是既有的 per-子宠单发 timer（第二轮 B7b 记）。
- **有没有新增线程？** **没有**，且净减少：O5 使 overlay 拓扑下 `pet-shared-fs-watch` 不再存在，
  DSH 关时 `dsh-online-probe` 线程启动次数 4→0（10 s 窗口）。
- **有没有新增系统调用 / 网络 / 磁盘？**
  - **系统调用：净减少。** O2 使隐藏期 `GetWindowLongW` 100→0/s、光标探测 16→0/s，可见静止
    99→1/s；但引入 **每 100 次 refresh 一次的低频校正读**（`RECHECK_EVERY_N_REFRESHES=100`，
    10 ms 档 ≈ 1 s 一次），用于兜住「未知来源的外部样式改写」（旧实现靠每拍读兜住，≤10 ms；
    新实现最坏 ≈1 s，**如实登记为放宽**）。O34 新增 **`WTSRegisterSessionNotification` 一次性注册**
    （每个 overlay 原生 HWND 一次；`set_on_top` / 屏迁移重建 HWND 后补注册一次；退出时反注册）——
    **一次性，不在热路径**。
  - **网络：** O5 净减（DSH 关时 loopback connect 10→0/10 s）；其余批零联网路径。
  - **磁盘：** O1 帧 0 解码每次起播 2→1（读盘次数减少）；O5 净减（桥目录 glob / 文件读 10→0/10 s）；
    无新增写盘。
- **内存有无增长？** 唯一实测到的内存增长来自 O1 第 4 项 pinned 首帧保留（三宠 +17.5 MB），
  **已撤回**；撤回后（c 组）三宠待机私有 161.2→164.4 MB，落在轮间噪声内（b 组同场景 161.6→179.1 MB
  是被撤回的那一版）。其余改动结构上只增加小对象：`_img_frame` 一个 int、`_pending[0]` 复用同一
  QImage（引用计数 +1，无像素拷贝）、O2 的穿透态缓存（每控制器 1 条）、O5 去掉若干长寿命线程与轮询。

### 实机运行记录（优化）

**最终口径（c 组，`opt-ab-20260927-c/`）** —— 这是本阶段唯一「两侧同拓扑、同启动路径」的可比 A/B：

- **两侧都走** `runner --side new`（同一个启动/布局/探针路径），只换 `--new-export-dir`：
  **优化前** = `.scratch/arch-ab/exports/fair-movefix-20260926-a`，
  **优化后** = `.scratch/arch-ab/exports/final-parity-opt-20260927-b`（**撤回 pinned 之后的包**）。
- **条件**：`--frameseq on`、两侧帧序列目录内容一致（final 包已复制 fair-movefix 的完整 frameseq）、
  **ABBA**（pre post post pre）各 2 有效轮、每轮 `--seconds 60 --warmup 15`（60 s 采样 + 15 s 预热）、
  **170 Hz 屏、AC 供电**、严格串行（轮间 `sleep 20`）、每轮前 `prep`。

**① 三宠待机（idle3，`aligned` 口径：对齐窗 + 同刻求和内存 + 逐鱼帧）**

| 轮 | 侧 | CPU % | 树 RSS 均 MB | 私有均 MB | 私有峰 MB | 逐鱼 fps | 重复帧 | paint p95 ms | paint max ms |
|---|---|---|---|---|---|---|---|---|---|
| r1 | pre | 52.97 | 215.58 | 161.31 | 167.6 | 23.69 | 0 | 25.083 | 32.605 |
| r2 | post | 56.52 | 221.64 | 168.46 | 172.8 | 23.70 | 0 | 24.926 | 58.406 |
| r3 | post | 49.93 | 213.61 | 160.29 | 166.8 | 23.69 | 0 | 24.979 | 27.566 |
| r4 | pre | 51.76 | 215.28 | 160.99 | 167.8 | 23.69 | 0 | 25.153 | 45.538 |
| **中位** | **pre** | **52.36** | 215.43 | **161.15** | 167.7 | **23.69** | 0 | **25.12** | **39.07** |
| **中位** | **post** | **53.23** | 217.62 | **164.38** | 169.8 | **23.70** | 0 | **24.95** | **42.99** |

**② 三宠移动（move3，`runner root 窗口` 口径）**

| 轮 | 侧 | CPU % | 树 RSS 峰 MB | 私有峰 MB |
|---|---|---|---|---|
| r5 | pre | 60.7 | 232.8 | 178.7 |
| r6 | post | 56.4 | 230.8 | 177.5 |
| r7 | post | 57.7 | 230.0 | 175.9 |
| r8 | pre | 58.4 | 233.0 | 178.9 |
| **中位** | **pre** | **59.55** | 232.9 | **178.8** |
| **中位** | **post** | **57.05** | 230.4 | **176.7** |

**③ 单宠待机（idle1，**只有 b 组数据，即包含 pinned 撤回之前**，故不能代表最终包）**

| 轮 | 侧 | 备注 | CPU % | 私有均 MB | paint p95 / max ms |
|---|---|---|---|---|---|
| r1 | pre | **作废**（见下） | — | — | — |
| r2 | post | b 组（撤回前） | 21.79 | 140.61 | 37.759 / 44.327 |
| r3 | post | b 组（撤回前） | 20.34 | 141.38 | 37.505 / 43.690 |
| r4 | pre | 有效 | 21.49 | 134.41 | 37.943 / 44.077 |
| **中位** | **pre** | n=1 | **21.49** | **134.41** | 37.94 / 44.08 |
| **中位** | **post** | n=2，撤回前 | **21.06** | **141.0** | 37.63 / 44.01 |

**④ 作废轮及原因（原始数据全部保留，未删）**

- **`opt-ab-20260927-a` 整组作废**：runner 的 base 侧仍是**旧多进程启动路径**，不适配 overlay 包
  ——三宠布局接线 `AttributeError`；且工作树快照的帧序列目录不完整，导致 `idle1-r2` 回退 WebM
  （非帧序列路径）。⇒ **两侧不同路径，不构成可比 A/B**。原始数据与 `run.log` 保留在
  `.scratch/windows-parity-20260926-a/opt-ab-20260927-a/`（含 `frameseq-worktree-partial-moved-aside`）。
- **`optab2-idle1-r1-pre`（b 组单宠第 1 轮）作废**：待机期间 `kinetic_tail` 触发拖拽悬空动画
  （探针读到 clip 序列 `['东张西望','待机呼吸休闲','被鼠标拖拽悬空反馈']`、位置 198 个取值 = 位置漂移、
  同帧重复 4 次）→ **按预登记作废**（`aggregate-all.json` 中该行 `valid=false` 并附原因原文）。

**⑤ 复跑命令**（原文 `opt-ab-20260927-c/run.sh`，严格串行、label 唯一、每轮前 prep、ABBA）：

```bash
cd /d/dsh-pet-src
P=.venv/Scripts/python.exe; R=.scratch/arch-ab/runner.py
OLD=.scratch/arch-ab/exports/fair-movefix-20260926-a
NEW=.scratch/arch-ab/exports/final-parity-opt-20260927-b
for spec in "3 idle" "3 move"; do set -- $spec
  for v in pre post post pre; do
    d=$OLD; [ $v = post ] && d=$NEW
    $P $R prep --label <唯一label> --pets $1 --new-export-dir $d
    timeout 600 $P $R run --label <唯一label> --side new --pets $1 --scenario $2 \
      --seconds 60 --warmup 15 --frameseq on --new-export-dir $d
  done
done
```

汇总：`.venv/Scripts/python.exe opt-ab-20260927-c/aggregate_all.py`（只读，输出写本目录、存在即换名；
`idle` 用 `analyze_controlled.analyze_side`，`move` 用 runner 自己的 smoke 门 + `per_pid` root 窗口 CPU/峰值）。

**⑥ 结论（如实写，不粉饰）**

- **真机可见常态下，本阶段优化的收益在噪声内**：三宠待机 CPU 52.36 → 53.23%（**持平**，轮间噪声量级）、
  私有 161.2 → 164.4 MB、逐鱼 fps 23.69 → 23.70（不变）、重复帧 0 / 0、paint p95 25.1 → 25.0 ms；
  三宠移动 CPU 59.55 → 57.05%、私有峰 178.8 → 176.7 MB（方向为正但只有 2 轮，**不据此宣称提升**）。
  ⇒ **没有显著提升，也没有退步。**
- **优化的实测收益集中在不可见状态**：离线 bench 的隐藏 / 锁屏 / 后台三类（见「性能分析（优化）」①②③④）
  降幅 54–81%、轮询归零、线程消失；**这些在真机 CPU 均值上没有可见差异**，因为 runner 的可见待机
  场景里它们根本不触发。
- **真机隐藏 / 锁屏场景未测**（runner 无该场景）→ 列「未验证」。
- **paint max 优化后两组都更高**（b 组 29.5 → 50.0 ms；c 组 39.1 → 43.0 ms），但**只有 2 轮**、
  **原因未定位** → 列为**待观察**，**不下结论**。

### 未验证与残留（优化）

1. **真机隐藏 / 锁屏 / 后台场景未测**：所有隐藏 / 挂起 / 后台收益都只有 **offscreen bench** 证据
   （`BENCH-final.txt` / `bench-after.json` / `after-*.json`）——**runner 没有该场景**，且按纪律未起桌宠。
   列未验证，不得用离线数字冒充真机结论。
2. **隐藏期 reader 仍解码**：O34 只停 clip 自身 `QTimer`（规范要求「仅停自身定时器」），未加解码背压
   → 非节流路径丢帧但 ffmpeg 照解码，**隐藏期 CPU 未归零**（已降 54–81%）。彻底停解码需在
   `_fill_queue` 的节流背压缝上加项，超出该批文件授权。
3. **既有 flake `test_shared_prefetch_thread_shutdown_and_recreate` 约 1/50 原生崩溃**：O1 期间的
   `access violation` 调查（`fix-20260927-O1/CRASH-NOTES.md`）结论 —— 该用例**改前 1/50 崩、改后 1/50 崩**
   （deselect 本批新增用例后单跑既有 12 例 ×50 对照），属**分支既有债**（共享预取线程 shutdown 后仍留活
   worker，`deleteLater` 落进已停线程）；建议单独一批处理。同文件中**本批新增用例自己的收尾竞态**已用
   `_settle()` 修掉（60 次 0 崩）。
4. **paint max 待观察**：优化后两组都更高（b: 29.5→50.0；c: 39.1→43.0），样本只有 2 轮/组、原因未定位
   —— 不下结论、不修、下阶段若要判需更多轮次。
5. **GPU / present 未测**：本阶段没有任何 present / GPU 口径测量（与 §十三、`ARCHITECTURE-FAIR-COMPARISON`
   的既有边界一致）。
6. **Linux / macOS 未测**：O2 的穿透态缓存与 O4 的锁屏注册都是 Windows 分支；POSIX 上全 no-op，
   但**未在 POSIX 实机跑过**。
7. **偶发卡顿线本轮未处理**：用户叫停、另立任务；本阶段**没有**跑卡顿轮次、没有 py-spy、没有新增
   卡顿测量结论（承 §十一 ⑤）。
8. **其它残留（批报告登记，不在本阶段文件范围）**：`pet/window.py:1986` 仍是废弃
   `mirrored(True, False)`；`tests/test_overlay_shell.py::_stub_shell_start` 里对 `_dsh_state_tracker.start`
   的 monkeypatch 现在成了死桩（默认门关，无行为影响）；O34 的锁屏注册「创建时句柄」问题已由小修 a
   的 `set_on_top` / `_migrate_to_screen` 补注册覆盖，但**未实机验证**。

## 十三、本地 PR 说明草稿（功能继承 + 优化，不执行提交 / 推送）

> **本节只是草稿**：不 commit、不 push、不开 PR、不评论（对外提交一律等用户明确点头）。
> 最终全量数字已填入（2026-09-27 17:5x）。

**标题建议（<70 字符）**：
`feat(overlay): Windows 功能继承收口 + 帧路径/隐藏期/后台常驻优化`

**摘要**：把 overlay 新架构与旧版（`base-2786c15`）的功能差距收口到可交付状态，并在不降可见帧率、
不新增常驻 timer/线程的前提下，降低隐藏 / 锁屏 / 后台三类不可见状态的常驻开销。真机 A/B 显示
**可见常态收益在噪声内（无提升也无退步）**，收益集中在不可见路径。

**改动分组**

1. **功能继承修复（第一轮 G1–G5 + 第二轮 B1–B8）**：岛碰撞开关门、同屏几何（子宠迁移 + 可见气泡/
   岛墙全局原点）、碰撞音量直取配置 + 点击/碰撞门独立、宠物间总碰撞的 per-sprite/per-slot 资格位与
   窄刷新、ffmpeg 回收阈值接线；岛拖拽、菜单作用对象、app 宿主、动画状态机、音效音源、气泡起止同步、
   壳接线、per-slot 逐只设置、设置页文案（详见 §一–§十一 与 `.scratch/.../FEATURE-MATRIX.md`）。
2. **优化 O1–O5**：帧路径（QPixmap 惰性化、重建链恒等短路、帧 0 不重复解码、`mirrored`→`flipped`）；
   隐藏期轮询（穿透态缓存、隐藏停探测、会话过滤器窄读）；隐藏/锁屏降载（零可见 → T3、逐只停节拍、
   预热成对、`WM_WTSSESSION_CHANGE`/`WM_POWERBROADCAST` 只降档不 hide）；后台常驻
   （`DshStateTracker` 按门惰性启动、overlay 下共享全屏 watcher 不启动、指令消费去重）。
   另含收尾小修：挂起自愈（用户输入解除挂起）、隐藏轮询测试顺序隔离、**撤回 FrameSeqClip pinned
   首帧常驻**（真机 +17.5 MB 换一次 1.2 ms 解码，不划算）。
3. **测试与文档**：新增 18 个测试文件（见下「提交提醒」）；改写若干既有断言（B5/B6/B8/B7a 各记）；
   `docs/PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md`（本报告）、
   `docs/PR-REPORT-ARCHITECTURE-FAIR-COMPARISON-2026-09-26.md`、`docs/ISSUE-111-...md`（追加）、
   `docs/INDEX.md`、`AGENTS.md`、`.scratch/single-overlay-window/HANDOFF.md`。

**测试结果**

| 门 | 结果 |
|---|---|
| 最终全量（这一棵树、这一时刻） | 全量 pytest rc=0：3911 passed / 11 skipped / 0 failed / 0 error（446.42 s），ruff 全绿、git diff --check 通过；证据 `.scratch/windows-parity-20260926-a/full-suite-20260927-e/`（撤回 pinned 之后、本轮全部改动之后） |
| 撤回 pinned **之前**的全量（`.scratch/.../full-suite-20260927-d/`，`rc=0`） | **3911 passed, 11 skipped, 263 warnings in 582.13s** |
| 撤回 pinned **之后**相关族复跑（frameseq / library / frame_path / sprite_dpr / tray_icon） | **167 passed** |
| 各批聚焦红→绿 | O1 红 15 failed/53 passed → 绿 193 passed（连跑 3 次一致）；O2 红 14 failed/8 passed → 绿 22 passed；O34 红（消融）36 failed/21 passed → 绿 58 passed；O5 红 6 failed/4 passed → 绿 530 passed/1 skipped；ruff 各批 `All checks passed` |

**口径**：以上全量是**这一棵树、这一时刻**的数字，改一行代码即失效；历史 **3638 passed / 11 skipped**
（`exports/fair-movefix-20260926-a`，另一棵树、更早时间点）**不得互替**，也不作等价增量结论；
11 条 skipped 的**身份未列**（`-q` 不输出原因）。`docs/PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md`
§十二 的离线数字均为 **offscreen bench**，不等于真机结论。

**未验证清单**：真机隐藏 / 锁屏 / 后台三类场景；隐藏期 reader 仍解码；GPU / present；Linux / macOS；
长稳（§十一 既有边界不变）；偶发卡顿（用户叫停、另立任务）；paint max 偏高（2 轮、原因未定位、
待观察）；既有 flake `test_shared_prefetch_thread_shutdown_and_recreate` 约 1/50 原生崩溃。

**需要人工确认的点**

1. **窗口级键在 overlay 下是全局的**：`OVERLAY_WINDOW_SCOPE_IDS`（`on_top` / `mouse_through` /
   `pet_opacity` / `lock_position` / `shift_drag` / `cursor_hidden_passthrough` 等）现在是**一份进程级配置**，
   设置页只在行说明里加「（对所有桌宠生效）」，**UI 上仍是单行控件**。旧版多窗口语义下这些是逐窗口的
   —— 若要逐宠独立，需要新的交互设计，**请确认按全局收口可接受**。
2. **per-slot 写盘带 `user_customized`**：子宠设置保存走 `write_slot_setting(..., user_customized=True)`
   （`overlay_spawn_state.py:234`），语义是「已自定义的 slot 下次生成不被主设置刷新」
   （`slot_manager.py:60-84`）。**请确认**「在子宠自己的设置界面改任意一项即整 slot 免疫主设置刷新」
   是想要的行为（旧契约如此，但覆盖面较大）。
3. **FrameSeq 未覆盖 `random` 类素材，需决定**：扩大覆盖会显著增加转码磁盘成本，计划原文列为
   「需用户决定」——本阶段**未做**。
4. **AC 供电下保持 T1 满速**：计划原文明确「用户拍板过，不动」。本阶段优化**没有**触碰 AC 满速策略
   （降载只在隐藏 / 锁屏 / 电池 / 零可见 sprite 时发生）。**请确认该拍板仍然有效**——若希望 AC 待机也降载，
   是另一项取舍（会改变可见观感）。

**提交提醒**：本工作树含**未跟踪的新文件**，提交时必须 `git add`，否则会漏进 PR。用
`cd /d/dsh-pet-src && git status --short | grep '^??'` 列出（当前 20 项）：

- `docs/PR-REPORT-ARCHITECTURE-FAIR-COMPARISON-2026-09-26.md`、`docs/PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md`
- `tests/test_background_service_gates.py`、`tests/test_frame_path_waste.py`、`tests/test_overlay_app_hosts.py`、
  `tests/test_overlay_bubble_wiring.py`、`tests/test_overlay_collision_toggle.py`、
  `tests/test_overlay_geometry_parity.py`、`tests/test_overlay_hidden_polling.py`、
  `tests/test_overlay_lifecycle_gaps.py`、`tests/test_overlay_per_slot_settings.py`、
  `tests/test_overlay_recycle_settings.py`、`tests/test_session_lock_suspend.py`、
  `tests/test_session_watcher_message_read.py`、`tests/test_settings_overlay_copy.py`、
  `tests/test_sprite_acts_tail.py`、`tests/test_sprite_click_turn_tail.py`、`tests/test_sprite_idle_tail.py`、
  `tests/test_sprite_menu_target.py`、`tests/test_sprite_move_tail.py`

**不提交**：`.scratch/` 下的全部取证目录、`__pycache__`、构建产物。

## 十四、随机动作 / 事件转 Q80 帧序列（2026-09-27～28）

**门禁**：full-suite-20260927-f（`ebf971e` + 未提交 WIP 含 R1/R2）：pytest 3929 passed / 11 skipped rc=0（506.76s）、ruff `pet tests tools` All checks passed、`git diff --check` rc=0。

**做了什么**：原先只有热集（idle/move/turn/click/drag）转无损 WebP 帧序列，随机动作（`random/`，89 段）
与事件（`events/balance/`，6 段）仍走 WebM + ffmpeg 流式解码。本批把这 95 段也纳入首跑后台供给，
改用**有损 Q80**（`-lossless 0 -quality 80`，alpha 逐像素无损、最差帧 PSNR 41.8dB；无损版磁盘 ×3.4），
方案经 K3+DS 合并定稿（`.scratch/frameseq-random-decision-20260927/DECISION.md`）。

| 批 | 改动 | 文件 |
|---|---|---|
| R1 | `FrameSeqClip` 帧表**懒列**：构造不再 `glob`，帧数读 meta `frames`（缺失/非法才兜底列目录）；首次 start/jump/预取/预热时锁内原地填充，worker 共享同一 list | `pet/frameseq_clip.py`、`tests/test_frameseq_clip.py`（+4） |
| R2 | 编码档位按目录（热集无损 / random·events Q80），采纳谓词校验 encoder；`scan_generations` 递归（支持 `events/balance` 三层）；供给序 热集→events→random；磁盘准入 `free ≥ max(1GiB, 源×20)`；`frames_on_disk` 改 `os.scandir`；**"有无活干"判定从 GUI 线程移入 worker**，无事可做的收尾不 rescan | `pet/frameseq_provision.py`、`pet/library.py`、`tools/convert_frameseq.py`、`tests/test_frameseq_provision.py`（+11）、`tests/test_convert_frameseq.py`（+1） |

**为什么要 R1**：内存归因（`.scratch/frameseq-random-mem-20260927-a/REPORT.md`）证明 random 帧序列多出的
90–110MB 与是否播放无关——低优先级预热给全部 clip 建对象，每个 clip 构造时列出 ~239 个 `Path`，
每宠一库 × 3。离屏探针（`.scratch/frameseq-random-mem-20260927-b/NOTE.md`，私有内存 MB，预热完成后）：

| 口径 | WebM 基线 | random 帧序列（R1 前） | random 帧序列 + R1 |
|---|---|---|---|
| 1 库 | 53.4 | 139.1 | 55.9 |
| 3 库 | 79.2 | 325.0 | 65.3 |

**真机三宠 A/B**（`.scratch/frameseq-random-final-ab-20260928-a/`，B=`final-parity-opt-20260927-b`（random 走 WebM），
C=`final-parity-opt-20260927-c`（R1+R2+Q80 素材），严格串行、ABBA 交替；逐轮值）：

| 场景 | 指标 | B | C |
|---|---|---|---|
| act3（三鱼各点名一个 random 动作 15s） | 最大帧间隔 ms | 53.7 / 52.6 | 45.1 / 46.7 / 45.2 |
| | 首帧就绪 s（三鱼最慢） | 0.134 / 0.135 | 0.019 / 0.016 / 0.018 |
| | 缺帧 / 最低 fps | 0 / 23.72 | 0 / 23.79 |
| | 进程私有内存峰值 MB | 188.1 / 188.2 | 157.8 / 156.3 / 155.7 |
| | 树 CPU %（act 相位，下界） | 74.2 / 65.7 | 70.7 / 73.0 / 72.9 |
| idle3（60s） | 同刻求和私有内存均值 MB | 160.0 / 160.3 | 151.3 / 150.1 |
| | 树 CPU %（对齐窗） | 59.0 / 56.2 | 61.2 / 59.7 |

- **流畅度**：切入随机动作的首帧从 ~134ms 降到 ~18ms，最大帧间隔从 ~53ms 降到 ~45ms（B 的最大间隔全部落在
  WebM 圈末回绕），缺帧均为 0。
- **内存**：act3 私有峰值 −31MB，idle3 −9MB（R1 让帧序列不再比 WebM 多占，反而更省——少了 ffmpeg 流式缓冲）。
- **CPU**：两臂差异在逐轮波动内（act B 两轮相差 8.5pp）；**不宣称 CPU 收益**。idle3 C 略高 ~2pp，仅 2 轮，不足以判定。
  短命 ffmpeg 子进程 CPU 漏计 ⇒ B 臂 CPU 是下界（对 B 有利）。
- **作废轮**：第一批 10 轮全部 preflight 拒测（日常桌宠在跑，零样本，`VOID-attempt1.md`）；`act3-r1-B`（首轮冷启动，
  WebM 首帧 0.80s、窗口内缺尾 9 帧，按预登记判门无效，保留不补跑）。

**代价与边界**
- 磁盘：每角色 +446MB（95 段 / 22772 帧）；首跑后台分多次启动生成（每轮起手上限 120s，约 6 次启动转完，期间未转的段继续走 WebM）。
- 库创建：采纳 106 段需重算源哈希 + 数帧，每库 GUI 线程 ~0.25s（原 ~0.07s），只在创建时一次。
- 原生崩溃：`test_watchdog_revives_dead_shared_thread` 偶发 0xC0000005 为既有问题（R1 前 5/40、R1 后 3/40，
  `.scratch/frameseq-random-mem-20260927-b/crash-ab/RESULT.md`），未修。
- 未验证：GPU/屏幕实际呈现；Linux/macOS；真实会话里随机动作的播放时长占比；Q80 画质只看了最差帧 PSNR，未做主观 JND；
  用户机器首跑转换期间的体感（T2 实测转换使系统 CPU +12–15pp，BELOW_NORMAL 优先级）。

## 十五、设置保存瞬时锁冲突修复（2026-09-28，批号 S1）

**现象**（用户实机，9/28 09:41）：设置页（独立设置进程）点「保存并退出」弹「配置未能写入磁盘」，
且保存失败阻止关窗——什么都不改也关不掉。设置进程不写文件日志，主进程日志无 ERROR。

**根因**：Windows 上 MSVCRT `_wopen` 共享模式为 `_SH_DENYNO`（FILE_SHARE_READ|WRITE，**不含
FILE_SHARE_DELETE**）。主进程 3s 轮询/目录 watcher 触发的瞬时 `read_text()` 与设置进程
`os.replace(temp, config-slot-N.json)` 撞在同一文件 → `PermissionError`（WinError 5）→
`Config.save()` 返回 False。属瞬时共享冲突：实机探针（持真读句柄 50ms）裸 replace 必失败，
带重试 65ms 成功。历史残留 `config.json.<pid>.tmp`（9/18、9/24）证明该族问题改前就存在。

**修复**（`pet/config.py` + `pet/overlay_spawn_state.py`）：新增 `atomic_replace_with_retry`
（仅 PermissionError/WinError 5/32 重试，20ms 指数退避封顶 200ms、5 次 ≈300ms 上限；其余 OSError
立即上抛）；`Config.save` 与 spawn_state 三处原子写全部接入；失败路径 finally 清 temp 残留。
UX 未动（保存失败仍弹窗+阻止关窗，防丢数据的设计保持）。红 5 failed → 绿 82 passed（含
per-slot/overlay copy 既有族），ruff 通过；实机锁探针 `.scratch/.../fix-20260928-S1/real-lock-probe.out`。

**门禁**：full-suite-20260928-a（S1 后全量）：pytest 3934 passed / 11 skipped rc=0（493.5s）、ruff rc=0。

**未改（后续建议）**：其余 11 个 `os.replace` 写点同族风险，优先 `overlay_settings_command.py`
（设置进程写指令文件撞窗会静默丢指令）；`chat/session_store.py` 已有自研重试可统一到本 helper。

## 十六、实机验收期修复：右键菜单字体全库加载 + 碰撞音效耗时（2026-09-28，批号 F1/C1）

**F1 右键菜单一开 +70MB（RSS 常驻不回）**：实机定位链——干净启动仅 5 个字体映射（msyh 三字重），
右键过菜单的进程有 528 个字体映射区域（mingliub/NotoSerifSC/simsunb/YuGoth 全家等几乎整个
C:\Windows\Fonts）。分步探针（每步独立子进程，真 Qt/windows）证实真凶**不是**"macOS 族名不存在"，
而是 **多族 font-family 列表**：只要列表首族覆盖不了中文，Qt 为缺字回退枚举整个字体库——
三族栈（无论 macOS 还是 Windows 版）必踩。修复：`SYSTEM_FONT_STACK` Windows 改**单族**
`"Microsoft YaHei UI"`（覆盖中文即不触发枚举），自选 ui_font 分支去掉多族拼接。修复后 modern
菜单字体足迹与无样式表普通菜单逐项相同（增量 0）。证据 `fix-20260928-F1/`（stage_probe 35 组对照）。
残留：用户自选不含中文的 UI 字体仍会一次性触发（无 QFont.setFallbacks 可用）；macOS/Linux 栈未实机验证。

**C1 高频碰撞掉帧（音效环节）**：碰撞音效每次 GUI 线程实测 5.83ms（5 次/秒 ≈29ms/s，落在两帧里），
大头是 scale_pcm16 逐样本 Python 循环（3.19ms）与 read_pcm16 读盘解析。修复：缩放结果按 (clip,音量)
缓存（≤8 条/≤512KB 每条）、PCM 解析按 (路径,mtime,size) 缓存、路径 memo 去 GetFinalPathName 系统调用。
修后每次 1.44ms（−75%）。不改播放后端架构/节流语义/音量门。证据 `fix-20260928-C1/`（微基准可复跑）。
另有单次 3.7s 级卡死一条（09:40:47 窗）：同窗密集 burst p99 仅 14.7ms，音效路径生不出该空窗；
窗内唯一可观测事件是设置进程 edge-tts 试听落盘，最可能系统级抢占——**证据不足，未定位、未修**。

**门禁**：full-suite-20260928-b（F1+C1 后全量）：pytest 3942 passed / 11 skipped rc=0（541.7s）、ruff rc=0。

## 十七、实机验收期第二批：朗读默认关 + 岛重绘空转 + 飞行帧交付（2026-09-28，批号 T1/I1/I2）

**T1 点击台词朗读默认关**（用户要求）：`self_talk_speak_enabled` 默认值 True→False，
5 处口径一致（config defaults/规范化、控件初始态、两处运行时缺省）；已存配置的用户值不受影响
（有测试锁住）。红 3+2 failed → 绿 225 passed。

**I1 展开态岛被撞空转重绘**（拖岛撞鱼卡顿的 Python 侧根因之一）：`_animating()` 把 paintEvent
已丢弃的通道当活跃，展开卡片每次 bump 空转 ~1s 的 60fps 整窗重绘。12 次事件 238 次重绘/170ms
→ 修后 13 次/18.4ms。岛拖拽几何同步实测仅 0.034ms/tick（推翻"静态体重建"假设）。
登记观察项：拖鱼撞岛（两侧无限质量）不产生撞击事件——既有语义。

**I2 飞行期帧交付推迟**（"鱼上下飞帧数上不去"的根因）：飞行期每 tick 以真实速率重设 clip
interval，旧实现直接 `QTimer.start(ms)` **重开倒计时**，帧交付被反复推迟。修复：webm_clip 与
frameseq_clip 同款的 `_apply_interval`——同值不碰 timer、真变且帧表在跑则排队到圈边界/下一拍
落地（真变速语义不变，最迟顺延 1 帧）。实测（真 clip+真 sprite+真抛掷物理剖面）：飞行期交付
30.8fps→**36.7fps**，交付间隔 max 57ms→**31.5ms**（理论间隔 24~31ms）。

**门禁**：full-suite-20260928-c（T1+I1+I2 后全量）：pytest 3952 passed / 11 skipped rc=0（480s）、ruff rc=0。
