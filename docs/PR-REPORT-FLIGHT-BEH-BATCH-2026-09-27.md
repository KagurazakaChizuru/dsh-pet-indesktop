# PR 报告：飞行期禁气泡 + 飞行边沿 + 落地预热去重（F-BEH 批次）

> **基线**：`ebf971e`（分支 `feature/single-overlay-window` 未提交区批次）
> **分支**：`feature/single-overlay-window`　**日期**：目录名沿用 `fix-20260927-F-BEH`；批次证据文件实际落于 **2026-09-28 23:36–23:43** / 2026-10-01（正式成文）
> **范围**：6 个文件（产品 5、新增测试 1）
> **关联**：内部工作记录 `.scratch/windows-parity-20260926-a/fix-20260927-F-BEH/`（红绿/聚焦/相关族原始输出与回滚探针）；Windows parity 报告 `PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md`

## 一、核心特性

飞行中的桌宠嘴边**不该冒气泡**——被抛/飞行时气泡、自言自语、识屏答复、节日播报、
语音报时全部按 sprite 门禁收口；飞行期提醒**入队不丢弃**、落地再弹（与设置页抑制
的「丢弃」语义刻意区分）；同一飞行窗口内落地预热只提交一批（去重）；飞行中被移除的
sprite 补落地边沿，壳的飞行集合不残留死对象。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 飞行期禁气泡 | 气泡入口统一读 `OverlayShell._bubble_blocked(sprite)`，按 sprite 判定（主飞→子宠照常、子飞→主宠照常） |
| 2 | 提醒入队不丢 | 飞行期非存活提醒照旧入队由 pump 挡住，落地再弹；一次性播报的**气泡显示**（识屏/节日/报时）飞行期丢弃不补发（音频照常） |
| 3 | 落地预热去重 | `warm_landing_submitted` 同飞行只提交一次，落地复位，下场飞行照常 |
| 4 | 飞行集合不漏不死 | 进/出飞行各回调一次边沿；飞行中被移除的 sprite 补落地边沿 |

**红线 / 不变量**：设置页抑制期语义不变（仍丢弃非存活提醒）；`music_lyric` 歌词气泡
**不在**本批范围（自有 `_bubble_suppressed`，飞行期仍冒——已知残留，见 §七）。

## 二、修改文件说明

> 下列 numstat 为文件级**累计值**（这些文件同时承载多批次 WIP）；F-BEH 的自身足迹
> 按内部记录的功能面标注。本批无 git 写操作（改动均在未提交工作树）。

| 文件 | 增删（文件累计） | F-BEH 改动意图 |
|---|---|---|
| `pet/sprite_behavior.py` | +846 / −30 | `_SpriteState` 加 `was_flying`/`warm_landing_submitted`（`__slots__` 同步）；`tick` 调 `_sync_flight_edge`（进出 `INTERACTION_THROWN` 各回调一次，异常只 log）；`forget` 飞行中移除补落地边沿；`_warm_landing_idles` 同飞行去重 |
| `pet/overlay_shell.py` | +1833 / −144 | `_flying_sprites` 集合；`_on_sprite_flight_changed` 接线；新增 `_sprite_in_flight`/`_bubble_blocked`；全部气泡入口（show_bubble/自言自语×2/识屏 look/两个宿主转发面）改读统一门禁 |
| `pet/window_alerts.py` | +103 / −45 | 新增模块级 `bubble_blocked(host, sprite)`/`sprite_in_flight`；恢复分支抽取 `restore_after_suppression`（入口复判门禁）；隐藏改道判定改读门禁；`show_alert` 丢弃门只认设置页位 |
| `pet/festival_service.py` | +9 / −1 | `_bubble` 用 `sprite_in_flight` → 飞行期整条丢弃；其后 `bubble_blocked` 保持既有语义 |
| `pet/voice_chime_service.py` | +9 / −1 | 同上（函数内惰性 import 约定不变） |
| `tests/test_flight_bubble_suppression.py` | +423（新增） | 14 条用例（见 §六） |

## 三、实现要点

门禁单点化：气泡弹出的所有路径不各自读「抑制位」，统一过 `_bubble_blocked(sprite)`
（壳聚合：设置页抑制 ∨ sprite 在飞）。飞行边沿用 `_SpriteState.was_flying` 在 tick 内
检测进出 `INTERACTION_THROWN`，回调异常不外溢（tick 安全）。提醒的「入队不丢」与
「一次性丢弃」按提醒类型分流：队列型提醒的生命周期归 pump 守卫，一次性播报不进队列。
预热去重用状态位而非内容比对（pin 与预热内容一字不变，零误判面）。

## 四、性能分析

**方法（可复现）**：`timeit`（10-30 万次均值，含测量对象说明；µs 级数字按区间给出——
裸对象/QObject 壳/真 Qt 壳的属性查找开销不同，三方独立复测 2-4 倍差但量级一致）+ 聚焦套件计时。
环境：Windows 11 / Python 3.13 / 项目 .venv

| 指标 | 实测 | 归属 |
|---|---|---|
| 门禁完整调用（`_bubble_blocked(sprite)` / `window_alerts.bubble_blocked(host, sprite)`） | **~0.15–0.66 µs/次区间**（测量对象形态相关：裸对象 0.15、壳宿主 0.29、真 Qt 壳 0.57-0.66；三方独立复测量级一致；集合检索本身 0.056-0.112 µs） | 新增热路径（每个气泡入口一次；60fps 帧预算的 ~0.004%，可忽略） |
| 飞行边沿检测 | `_sync_flight_edge` **每 tick 每 sprite** 一次状态比较（`sprite_behavior.py:380`，~0.1 µs 级）；**回调**只在进/出飞行各 1 次 | 新增 |
| 聚焦套件（同 -k） | **812 passed in 80.62s**（**09-28 快照**；2026-10-01 同 -k 复跑 822 passed，差值为其后新增命中测试） | 既有+新增 |

**结论**：①稳态开销 = 每气泡入口亚微秒级（区间见表）+ 每 tick 每 sprite 一次 ~0.1µs 级状态比较
（均可忽略）；②边沿回调只在进出飞行时触发，不逐 tick 执行；③无新系统调用/网络/磁盘/线程；
④内存 = 每壳一个 sprite id 集合（上限=宠物数，个位数）。

## 五、实机运行记录

- **红→绿现场**：回滚探针（`_rollback_probe.py`，去掉接线+去重 = 修复前语义）→
  **13 failed / 1 passed**（唯一绿 = 空 idle 池不变式，两侧都应绿）；恢复后 14 passed。
- **用户可见行为确认**：部署宠（D:\dsh-pet，构建于本分支之后）日常拖拽/抛掷场景下
  飞行期不再冒气泡、落地恢复——该行为在 09-29 起的部署上持续运行（用户日常观察，
  未接到回归反馈）。飞行期气泡这类瞬时视觉行为无法在 offscreen 自动验证视觉面，
  此处的实机依据 = 部署运行 + 用户未见异常（诚实标注其强度低于录像对比）。
- **边界与失败路径**：设置页抑制期丢弃语义不变（回归用例覆盖）；一次性播报飞行期
  丢弃不补发（设计口径，§七 登记）；歌词气泡飞行期仍冒（已知残留，§七）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `ruff check`（5 产品+新测试） | All checks passed |
| 红（回滚探针） | `_rollback_probe.py` | 13 failed / 1 passed（证明 14 条能抓修复前行为） |
| 聚焦 | 单文件 `test_flight_bubble_suppression.py` | **14 passed** |
| 聚焦族 | `-k 'bubble or self_talk or alert or festival or voice_chime or thrown or warm or sprite_behavior'` | **812 passed** |
| 相关族复跑 | alert_queue/overlay_*/sprite_*/physics/throw_flight_anim/festival/voice_chime*/architecture/todo_reminder/music_lyric | **594 passed**（另 178+233+169 passed） |
| 全量 | 见 PR 描述（本批随 2026-10-01 最终全量 4190 passed） | |

## 七、已知限制与后续

- **音乐歌词气泡飞行期仍冒**：`music_lyric_controller.py` 自有 `_bubble_blocked`
  （读设置页位），不在本批文件范围——已登记，后续统一进同一门禁。
- **一次性播报不补发**：识屏答复/节日/报时飞行期丢弃后不补（设计口径；若产品上要
  补发，需另立队列）。
- **飞行期提醒「入队不丢」是有意与设置页区分**：若上游认为飞行期也该丢弃，
  撤 `show_alert` 的设置页位判定即可。
- `MultiWindowProxy._bubble_suppressed` 仍为设置页聚合位（未加飞行分量，
  刻意保持联动节流语义）。

## 八、风险与回滚

影响面：气泡/自言自语/提醒/播报的隐藏判定路径。无配置键、无持久数据、无迁移。
回滚：按文件 hunk 回退（本批足迹见 §二；内部留档含 `_rollback_probe.py` 可复现红态），
无落盘状态残留。
