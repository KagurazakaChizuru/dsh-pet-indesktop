# 内存瘦身专项报告（单宠稳态）：+170MB 归属拆解 + 两刀落地

> **基线**：`94db199`（本分支最新 HEAD；工作过程中 990c34b/94db199 两笔由并行任务提交）
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-24
> **范围**：2 个实现文件（`pet/library.py`、`pet/app.py`）+ 2 个测试文件 + 5 个诊断工具 + 本文档 + `docs/INDEX.md` 登记
> **关联**：[`PR-REPORT-SINGLE-OVERLAY-WINDOW-2026-09-24.md`](PR-REPORT-SINGLE-OVERLAY-WINDOW-2026-09-24.md)（新架构总报告）

---

## 〇、结论摘要（先看这个）

**1. +170MB 不是"新架构结构税"。** 同配置、同流程、只切拓扑（`PET_RENDER_TOPOLOGY` 一个环境变量）：

| 口径 | overlay（新） | legacy（旧） | 差值 |
|---|---|---|---|
| 源码跑批（180s，单宠真配置） | 177.5MB | 145.0MB | **+32.5MB** |
| 同一份部署 exe（200s，单宠真配置） | 184.0MB | 140.7MB | **+43.3MB** |

"每宠一个顶层窗 → 单合成窗"的架构差价是 **+33~43MB**，不是 +170MB。

**2. 你观察到的 280-305MB 复现出来了，但那是 3 只宠。** 你配置目录里的
`overlay-active-pets.json = {"version":1,"slots":[4,5]}`（主宠 + slot4 + slot5）。
同一份 exe、同一份配置、保留该清单跑 200s：t=15s 233.7MB → **稳态均值 330.6MB / 峰值 345.0MB**。
单宠 −→ 3 宠 = **+146.7MB（均值）/ +161.0MB（峰值）**，≈ 80MB/只。

**3. 真正在"涨"的是已停播 clip 残留的解码帧，且与宠数、运行时长成正比。**
单宠 480s 实测 **6.91MB/min** 的持续增长（166.8 → 215.2MB）；同一时间残留帧队列
0 → 53 帧 ≈ 46.6MB，与 WS 斜率同源。这解释了"重启 191MB 起跑、3 分钟收敛 300MB"：
它不是收敛到某个高水位，而是在以 ~7MB/min 缓慢往上爬；宠数越多爬得越快。

**4. 第一刀把这个增长源掐掉（治本，不是压报表）：**

| 口径 | before | after | 差 |
|---|---|---|---|
| 单宠 480s 稳态均值 | 214.75MB | **156.17MB** | **−58.6MB** |
| 单宠 480s 稳态峰值 | 219.70MB | 162.82MB | −56.9MB |
| 单宠 480s 私有字节 | 159.09MB | 110.66MB | −48.4MB |
| 单宠 480s WS 斜率 | **+6.91MB/min** | **+0.40MB/min** | 增长源消失 |
| 残留解码帧（480s 末） | 53 帧 / 36.0MB | **0 帧 / 0MB** | — |

**5. 单宠稳态目标 ≤200MB：达标。** 打包版单宠稳态 184.0MB（裁剪前）→ 源码同口径
156.2MB（第一刀后）。**没有使用任何 `SetProcessWorkingSetSize` / `EmptyWorkingSet` /
`malloc_trim` 式化妆手段，也没有改任何报表口径** —— 所有数字都由同一个采样器
（进程内 `GetProcessMemoryInfo` / 进程外 `psutil`）在改动前后各跑一遍得到。

**6. 反证：「外围服务」不是大头。** 把灵动岛 + chat + agent_link 三条全关（`abl-periphery`，
180s，单宠，其余逐字同 `p180-base`）：**187.86 → 183.02MB，只差 4.8MB**，
且两次运行的残留帧状态几乎相同（22 vs 24 帧、16.70MB）。所以"大头在外围服务"
这个方向在**稳态**口径下不成立；真正的差值来源是宠数与残留帧增长。
（注意 `_shared` 的 DshMonitor/OpenCodeMonitor 对象即使配置关闭也仍被构造——
D0/T6 的"常开化"是刻意的，它们不是内存大头。）

---

## 一、测量口径（可复现，先立规矩）

三套口径分开，互不冒充：

| 代号 | 命令 | 采什么 | 用途 |
|---|---|---|---|
| **S（源码）** | `.venv/Scripts/python.exe tools/mem_run.py --label <L> --seconds <N> --mode ws --code-root <worktree>` | 进程内 `GetProcessMemoryInfo` 的 WorkingSetSize / PagefileUsage，2s 一行 | before/after 权威 WS |
| **P（打包）** | `.venv/Scripts/python.exe tools/ext_ws_probe.py --label <L> --exe dist-onedir/dsh-pet-standalone-webm-chat/dsh-pet-standalone-webm-chat.exe --seconds <N>` | 进程外 `psutil` 采样同一 exe | 部署产物口径（用户基准的来源） |
| **T（tracemalloc）** | 同 S 但 `--mode trace` | 25 帧 tracemalloc，每 20s 快照 | 只做归因，**不作数字** |

**环境**：Windows，2560×1440 真实桌面（未用 offscreen），Python 3.13.7 / PySide6 6.11.2。
**配置**：`%APPDATA%/dsh-pet-standalone-webm-chat` 整份复制到临时目录后跑批
（**绝不写真实配置目录**）；单宠 = 删除 `overlay-active-pets.json`（缺文件即"首次运行语义 = 只有主宠"），
3 宠 = 原样保留。真配置要点：`chat.enabled=true`、`dynamic_island.enabled=true`、
`agent_link.dsh+opencode=true`、`proactive_screen=false`、`voice_chime=false`、`music=false`、
`media_prewarm=balanced`、`first_frame_cache_max_mb=8`、`character=shenshen`（106 段素材，热集 11 段已帧序列化）。
**流程**：冷启动 → 不交互 → 采样到 N 秒 → 主动退出；"稳态"= 最后 60s 统计量。
**样本量**：每个口径每次运行 ≥ 30 个采样点（2s 间隔），同标签 A/B 各 1 次运行；`-mode trace` 另有 9 个快照。

> **口径 T 的警告（必须写在数字旁边）**：tracemalloc 自身记账会把 WS 从 177MB 抬到
> **396MB**（实测），所以 trace 模式**只用来做归属聚合**，绝不用它的 WS 数字。

---

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/library.py` | +93 / −0 | 新增 `IDLE_FRAME_TRIM_INTERVAL_MS`、`_idle_trim_timer`、`release_idle_frames()`、`_drain_clip_queue()`、`_on_idle_trim()`；`movie()` 新建 clip 时调用回收；`schedule_low_priority_warm()` 起定时器、`pause_warm()` 停定时器 |
| `pet/app.py` | +24 / −4 | 顶部移除 `from . import balance as balance_mod` 与 `from .festival_service import FestivalReminderService` 两条**模块级**导入；`_show_balance_payload` / `_island_tier_hint` / `_balance_worker` / `_ensure_festival_service` 各自改为**函数内** `import`。装配区改动，未触碰 `_island_icon_pixmap` |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_library_idle_frame_trim.py` | +231 / −0 | 9 例：回收生效 / 在播 clip 不被误伤 / 存活 reader（含圈末驻留）不被误伤 / 驻留宽限期满 reader 已死时可回收 / 单段坏对象不拖垮整池 / `movie()` 事件驱动触发 / 定时器生命周期 / 定时器槽触发回收 |
| `tests/test_app_lazy_imports.py` | +76 / −0 | 2 例（子进程口径）：`import pet.app` 不得带出 `pet.balance` / `pet.festival_service` / `pet.festival_data` / 节日文案表 |

### 诊断工具（`tools/`，产品侧零 hook）

| 文件 | 增删 | 用途 |
|---|---|---|
| `tools/mem_probe.py` | +605 / −0 | 进程内探针：ws/trace 双模式、双口径 tracemalloc 聚合、Qt/gc 普查、clip 队列与 reader 普查 |
| `tools/mem_run.py` | +179 / −0 | 临时 APPDATA 跑批器（`--code-root` 隔离并发改动、`--override` 改配置副本） |
| `tools/ext_ws_probe.py` | +189 / −0 | 打包 exe 进程外 WS 采样（内嵌解释器无法注入） |
| `tools/import_cost.py` | +65 / −0 | 单模块导入成本微基准（每模块一个全新子进程） |
| `tools/mem_report.py` | +85 / −0 | 把各次运行的 `summary.json` 汇总成对照表（本报告表格即它打印的） |

### 未改动（看起来相关但故意没动）

`pet/webm_clip.py`、`pet/overlay_window.py`、`pet/overlay_shell.py`、`pet/frameseq_clip.py`、
`pet/window.py`、`pet/tick_*.py`、`pet/sprite_*.py`、`pet/island_bridge.py` —— 见「未采纳方向」逐条原因。

---

## 三、归因：+170MB 逐项归属表

### 3.1 拓扑差价（同配置同流程，只切 `PET_RENDER_TOPOLOGY`）

```
| label       | 口径     | 秒  | 拓扑            | t=15s | 稳态均值 | 稳态峰值 | 私有字节 | 子进程 |
| base-overlay| source   | 180 | overlay(默认)   |162.92 |  177.50  | 179.99   | 121.92   |   1    |
| base-legacy | source   | 180 | legacy          |134.98 |  145.04  | 152.35   | 103.24   |   2    |
| pkg-overlay | packaged | 200 | overlay(默认)   |161.91 |  183.95  | 188.39   | 128.98   |   4    |
| pkg-legacy  | packaged | 200 | legacy          |124.04 |  140.65  | 148.18   |  97.62   |   2    |
| pkg-3pets   | packaged | 200 | overlay 3 宠    |233.73 |  330.63  | 344.99   | 275.95   |   6    |
```

- **架构差价 = +32.5MB（源码）/ +43.3MB（打包）** → 与"全屏 2560×1440 单合成面"
  的估算量级一致（`2560×1440×4 = 14.7MB`/份缓冲，Qt 透明窗通常 1~2 份 + 命中/合成开销）。
- **宠数差价 = +146.7MB（均值）/ +161.0MB（峰值，=2 只额外宠）** → ≈80MB/只。
  结论：**用户口径的 +170MB ≈ +43MB 架构 + ~+115~160MB 宠数**，与"新架构"无关。

### 3.2 Python 堆归属（tracemalloc 口径 B：最内层我方帧 = 真正分配点）

基线运行 `base-overlay-trace`（180s，单宠真配置），Python 堆合计 **95.97MB**：

```
       MB     blocks  bucket（分配点）
   50.099         57  pet/webm_clip.py:2545   ← frame = next(it) 解出的 RGBA 帧
    3.289      45133  pet/frameseq_clip.py:123
    2.826      30284  <ext> linecache.py:172          ← 探针自身（traceback 渲染）
    2.326      20103  <ext> importlib._bootstrap_external:784
    1.833          1  tools/mem_probe.py:298          ← 探针自身（快照持有）
    1.814      16373  pet/voice_chime_service.py:26   ← 模块导入（本配置确需）
    1.705      15749  pet/app.py:1593                 ← 模块导入
    1.619      15514  pet/balance.py:20               ← 模块导入（本配置不需要！）
    1.612      13838  pet/app.py:34                   ← QtCore 导入
    1.432      10936  tools/mem_probe.py:390          ← 探针自身（gc 普查）
    1.425      16248  pet/festival_calendar.py:24     ← 模块导入（本配置不需要！）
    0.969       8021  tools/mem_probe.py:304          ← 探针自身
    0.924       7735  pet/dsh_state.py:40
    0.858       7082  pet/webm_clip.py:772
    0.819       6932  pet/app.py:52                   ← PetWindow 导入（见「未采纳」）
```

**50.1MB / 57 块 = 57 × 640×360×4(0.879MB)**，占该进程 Python 堆的 52%，是单项第一，
且**只出现在读者路径**。该 bucket 的大小随"已播过又切走的动画段数"逐段增长
（跨运行实测 4 / 9 / 21 / 22 / 23 / 24 / 53 / 57 帧，每次运行随机动作命中不同），
所以**不要把它当常数**：配对 A/B（`trace-base` vs `trace-cut1`，同基线同流程）取到的是
23 帧/20.2MB，结论相同 —— 见 4.1 的 paired 证据。它由 clip 帧队列普查第二条独立证据交叉验证：

```
| label          | 秒  | 稳态均值 | 残留帧 | 残留帧MB | 存活reader |
| census-overlay | 180 |  188.05  |   21   |  14.06   |     1      |
| p180-base      | 180 |  187.86  |   22   |  16.70   |     1      |
| p480-base      | 480 |  214.75  |   53   |  36.04   |     1      |
```

（两次 180s 运行的残留帧数 21 vs 22 一致；`base-overlay-trace` 因多跑 29s 且随机动作
命中更多，累积到 57 帧 —— 残留量随"播过又切走的动画段数"线性增长，见 5.2 斜率实测。）

### 3.3 归因总表（MB 级）

| # | 项 | 归属量 | 证据（口径） | 处置 |
|---|---|---|---|---|
| 1 | **已停播 clip 残留解码帧** | 22 帧/16.7MB @180s；53 帧/36.0MB @480s；23 帧/20.2MB @trace | T 口径 B `webm_clip.py:2545`（配对 A/B：23 块 → **该 bucket 消失**）；clip 队列普查 `clip_queue_mb` | **第一刀已砍** |
| 2 | **启动导入图**（`pet.app` 拉进的模块与数据表） | 全图 ~25MB；其中**本配置不需要**的 `pet.balance` + `pet.festival_*` ≈ 2.3–3.7MB | T 口径 A `mem_probe:605`=20.4MB（25 帧截断）+ `app.py:39/59` 等；子进程 import 图 29.37→27.05MB；`tools/import_cost.py` 隔离值 4.75/2.95MB（**上限**，含共享依赖） | **第二刀砍 2.3MB（确定值）** |
| 3 | **单合成窗结构税**（全屏合成面 + overlay-only 面） | +32.5MB（S）/ +43.3MB（P） | 同二进制切拓扑 A/B | **不可砍**（文件在禁改/只读名单） |
| 4 | Qt 图像常驻 | QImage 11.2–22.6MB、QPixmap 5–15 个 | 普查 `qimage_mb`/`qpixmap_n` | 部分随第一刀下降（22.6→14.7MB、15→5 个） |
| 5 | 106 个 clip 播放器对象 + 106 个 QTimer | <1MB Python + 少量 Qt | T 口径 B `webm_clip.py:878`=0.37MB、`:909`=0.33MB；QTimer 计数 132–133 | 不砍（收益不抵风险） |
| 6 | 灵动岛 + 岛卡片控件 | **实测 ≤4.8MB（与 chat/agent 合计）** | `abl-periphery` 消融：187.86 → 183.02MB | 不砍（见「未采纳」） |
| 7 | hub / agent 桥 / 共享 watcher（常开面） | 同上（**两拓扑同存，非差值来源**） | T 口径 B `agent_link.py:1425`=0.13MB；普查 `SharedSubsystems/MultiWindowProxy/DshMonitor/OpenCodeMonitor` 各 1 个 | 不砍 |
| 8 | Qt 全局 pixmap 缓存 | `cacheLimit=10240KB`（是**上限**不是占用） | 普查 `qpixmap_cache_limit` | 不砍（无占用证据） |
| 9 | PySide6 wrapper 累积 | 未见累积 | 多次普查 `QObject`/`QThread`/`QMenu`/`QAction` 计数稳定（QThread 恒 2） | 不砍 |
| 10 | FrameSeqClip 帧路径/元数据 | 3.3MB（两次运行逐字节一致：45133 块） | T 口径 B `frameseq_clip.py:146` | 文件禁用；第一刀顺带清其停播显示槽 |

---

## 四、性能分析（每刀：证据 → 改法 → 功能等价论证 → before/after）

### 第一刀：`pet/library.py` 停播 clip 残留解码帧池级回收

**证据**：见 3.2（50.1MB / 57 帧 @ `webm_clip.py:2545`，占 Python 堆 52%）与 3.3 #1。
机制：动画切走后 clip 被 `stop()`，`webm_clip._hard_stop` 清了显示槽却**没排空帧队列**；
每个 WebMClip 的 `_queue` 上限 8 帧，而读者停摆后队列必然被写满 → **每段被播过又切走的
动画永久留下 8×0.879MB ≈ 7MB**。3 分钟里播过 3 段就是 21MB，480s 里 53 帧就是 46.6MB，
最终上限是 `66 段冷池 × 7MB ≈ 462MB`（与宠数再相乘）。

**改法**（`pet/library.py`，93 行）：素材池持有者这一层补不变量 ——
**不在播、且 reader 线程已退出的 clip，不得再持有解码帧**。
- `release_idle_frames()`：遍历已建 clip；`_running` 为真跳过；`_thread.is_alive()` 为真跳过；
  否则排空 `_queue`（`get_nowait` 到 `queue.Empty`，逐项 `len(item[0])` 累加释放字节）
  并在**非 `_soft_parked`** 时 `clear_display_frame()`；逐 clip `try/except` 兜底。
- 两个触发点：事件驱动挂在 `movie()` 的"新建 clip"分支（**切换动画 = 残留产生的时刻**）；
  低频兜底是 10s 的 `_idle_trim_timer`（随 `schedule_low_priority_warm()` 开、
  随 `pause_warm()`/`shutdown()` 停，保持"隐藏即停"的既有低功耗纪律）。

**功能等价论证（为什么不回退任何功能）**：
1. 帧队列只可能被该 clip 自己的 `QTimer(_poll)` 消费；`_running` 为假 = 定时器已停，
   这些帧物理上不可能再被任何路径读到；
2. `webm_clip.start()` 每次都重建 `self._queue = queue.Queue(maxsize=8)`，
   下一次播放拿到的是**全新队列**，不依赖旧队列里的任何一帧 —— 这一条在代码里可直接读证
   （`webm_clip.py:1557`），也是"丢帧不影响视觉连续性"的既有契约；
3. 圈末软停驻留（`_soft_parked`，等 `start()` re-arm 续圈）时 reader **仍存活**，
   被 `is_alive()` 判据排除；宽限期满 reader 自行退出后 `_rearm_loop_reader()` 必失败
   （判 `is_alive`），`start()` 必走全新队列路径，此时回收同样无副作用；
4. 显示槽只在非 `_soft_parked` 的 clip 上清空，**与 `webm_clip.clear_display_frame`
   自己的契约一致**（该函数 docstring 明写"软停驻留（park）绝不清"）；
   而桌宠真正显示的是 `PetSprite` 自己那份 pixmap，清空已停播 clip 的显示槽无可见变化
   （`_hard_stop` 本来就会这么做）；
5. 回收**不新增任何线程、不新增系统调用、不新增磁盘/网络访问**，单次成本 = 已建 clip 数
   （≤106）次属性读 + 少数 clip 的排空，实测量级远低于 1ms。

**before/after（同口径、同配置、同流程）**：

```
| label     | 口径   | 秒  | t=15s | 稳态均值 | 稳态峰值 | 总峰值 | 私有字节 | 残留帧 | 残留帧MB | QImage MB | QPixmap | 线程 |
| p180-base | source | 180 |169.18 |  187.86  | 199.95   | 199.95 | 133.73   |   22   |  16.70   |  18.21    |   15    |  7   |
| p180-cut1 | source | 180 |159.11 |  169.15  | 174.73   | 174.73 | 114.20   |    0   |   0.00   |  11.18    |    6    |  5   |
| p480-base | source | 480 |163.96 |  214.75  | 219.70   | 219.70 | 159.09   |   53   |  36.04   |  22.61    |   15    |  6   |
| p480-cut1 | source | 480 |150.83 |  156.17  | 162.82   | 167.39 | 110.66   |    0   |   0.00   |  14.70    |    5    |  5   |
```

**WS 斜率（同一 CSV 内 t=60s → 结束的线性斜率，最能量化"增长源是否消失"）**：

```
p480-base : t=61.09->481.37s  ws=166.77->215.17  slope=+6.91 MB/min   qframes= 0->53  (+7.6 帧/min)
p480-cut1 : t=61.17->481.37s  ws=151.27->154.07  slope= +0.40 MB/min  qframes= 0-> 0
p180-base : t=61.14->180.84s  ws=176.43->185.48  slope=+4.54 MB/min   qframes= 4->22
p180-cut1 : t=61.12->180.93s  ws=162.69->167.44  slope=+2.38 MB/min   qframes= 8-> 0（已回收）
```

**第一刀 paired A/B（同一基线提交 `9240bb2` 与 `14b7d59`，只差这一刀）**：
`trace-base` vs `trace-cut1`，同一配置同一流程，Python 堆 **66.31 → 46.12MB（−20.2MB）**，
两个极端指标都指向同一处、且相邻项**逐块一致**（说明不是采样噪声）：

```
trace-base 口径B:  20.216MB / 23 blocks  pet/webm_clip.py:2545   ← frame = next(it)
                   3.276MB / 45133      pet/frameseq_clip.py:146   ← 逐块一致
trace-cut1 口径B:  （webm_clip.py:2545 这个 bucket 整个消失）
                   3.289MB / 45133      pet/frameseq_clip.py:146   ← 逐块一致
```

**结论**：① 稳态开销下降 18.7MB（180s）/ **58.6MB（480s，−27%）**，且增长源消失
（6.91 → 0.40MB/min）；② 新增路径成本 = 每 10s 一次 ≤106 次属性读 + 每次切动画一次同样的
扫描（无逐帧开销，不在热路径上）；③ **无新增系统调用 / 网络 / 磁盘 / 线程**；
④ 内存只减不增（QImage 22.6→14.7MB、QPixmap 15→5、私有字节 −48.4MB）；
⑤ 残留帧计数 53 → **0**、Python 堆的 reader-frame bucket **整个消失**，
是"机制级"而非"报表级"的验证。

### 第二刀：`pet/app.py` 按配置关闭的功能模块懒加载

**证据**：`tools/import_cost.py`（每个模块一个全新子进程的 tracemalloc 增量）：

```
      MB   new pet modules  module
   18.04                51  pet.window
   13.99                21  pet.context_menus.shared
    9.94                 7  pet.chat
    9.93                15  pet.agent_link
    8.13                 8  pet.webm_clip
    5.48                 4  pet.dynamic_island
    4.75                 4  pet.balance            ← 本配置从不查余额
    4.29                 6  pet.voice_chime_service
    2.95                14  pet.festival_service   ← 总开关默认关闭
    0.05                 4  pet.autostart
```

本配置（`balance_refresh_minutes=0`、`balance` 从未被点开、`festival_reminder_enabled=false`）
在启动时白付 `pet.balance` 4.75MB + `pet.festival_service`（连带 `festival` /
`festival_calendar` / `festival_data` / 五份节日文案表）2.95MB ≈ **7.7MB Python 堆常驻**。

**改法**（`pet/app.py`，+24/−4）：把这两条模块级导入搬到真正的使用点
（`_show_balance_payload` / `_island_tier_hint` / `_balance_worker` / `_ensure_festival_service`）。
**功能等价论证**：模块级 `import` 与函数内 `import` 在 CPython 里语义等价（二者都只是
`sys.modules` 查表 + 首次执行模块体），唯一差别是**首次代价的付费时点**；所有调用点在
导入后行为逐字不变；`_chime_wanted()/ _festival_wanted()` 的既有门控逻辑一行没动。

**before/after**（`p180-cut1` vs `p180-cut2`，同口径 180s 单宠真配置；两者残留帧都是 0，
QImage/QPixmap 计数相同，所以差值不是队列噪声）：

```
| label     | 口径   | 秒  | t=15s | 稳态均值 | 稳态峰值 | 私有字节 | 残留帧 | QImage MB | QPixmap | 线程 |
| p180-cut1 | source | 180 |159.11 |  169.15  | 174.73   | 114.20   |    0   |  11.18    |    6    |  5   |
| p180-cut2 | source | 180 |164.08 |  163.65  | 171.62   | 108.44   |    0   |  11.18    |    6    |  5   |
```

**确定值（子进程口径，无噪声）**：`import pet.app` 的 tracemalloc Python 堆
**29.37MB → 27.05MB（−2.32MB）**，且模块清单一并消失：

```
opt1（仅第一刀）: 29.37MB | ['pet.balance', 'pet.festival_service', 'pet.festival_data']
opt2（+第二刀）  : 27.05MB | []
```

> 口径说明：`tools/import_cost.py` 的隔离值（balance 4.75MB / festival 2.95MB）是
> **上限**——它们各自把共享依赖的分摊也算进去了；在 `pet.app` 的真实导入序下，
> 增量只有 **2.32MB**（子进程实测）。WS 侧的 −5.5MB / 私有字节 −5.8MB 含
> 分配器页效应，故本刀按 **"2.3MB（确定）～5.5MB（WS 侧）"** 记账，不按 7.7MB 吹。

**结论**：① 启动导入图 −2.32MB Python 堆（确定值）；② 触发频率 = 每进程一次，
且在"真的要看余额 / 真的开了节日提醒"时才付；③ 无新增系统调用/网络/磁盘/线程；
④ 内存只减不增。

---

## 五、实机运行记录

**本机真实环境**：Windows + 2560×1440 真实桌面（**不是 offscreen**）、真实用户配置副本、
真实部署产物 exe（`dist-onedir/.../dsh-pet-standalone-webm-chat.exe`，mtime 2026-09-24 01:15:22）。
本次专项累计实机跑批 **12 次**（8 次源码口径 / 4 次打包口径），每次都让桌宠在桌面上真实启动、
播动画、走动、被灵动岛避让，跑满时长后主动退出。

**1) 用户基准的现场复现（单宠）**：

```
$ .venv/Scripts/python.exe tools/ext_ws_probe.py --label pkg-overlay \
    --exe dist-onedir/dsh-pet-standalone-webm-chat/dsh-pet-standalone-webm-chat.exe --seconds 200
{ "ws_t15_mb": 161.91, "ws_late_avg_mb": 183.95, "ws_late_max_mb": 188.39,
  "ws_peak_mb": 190.14, "private_late_avg_mb": 128.98, "children_max": 4 }
```

**2) 「300MB」的现场复现（保留真实 active-pets 清单 → 3 宠）**：

```
$ .venv/Scripts/python.exe tools/ext_ws_probe.py --label pkg-3pets \
    --exe dist-onedir/.../dsh-pet-standalone-webm-chat.exe --seconds 200 --keep-active-pets
{ "ws_t15_mb": 233.73, "ws_late_avg_mb": 330.63, "ws_late_max_mb": 344.99,
  "private_late_avg_mb": 275.95, "children_max": 6 }
# 依据：%APPDATA%/dsh-pet-standalone-webm-chat/overlay-active-pets.json → {"slots":[4,5]}
```

**3) 旧架构对照（同一份 exe，只加一个环境变量）**：

```
$ .venv/Scripts/python.exe tools/ext_ws_probe.py --label pkg-legacy ... --env PET_RENDER_TOPOLOGY=legacy
{ "ws_t15_mb": 124.04, "ws_late_avg_mb": 140.65, "ws_late_max_mb": 148.18, "private_late_avg_mb": 97.62 }
```

**4) 增长曲线现场（第一刀的直接证据，480s 单宠）**：

```
p480-base : 166.77MB@61s → 215.17MB@481s   (+6.91MB/min, 残留帧 0→53)
p480-cut1 : 151.27MB@61s → 154.07MB@481s   (+0.40MB/min, 残留帧 0→0)
```

**5) 外围服务消融（把"是不是岛/chat/agent 吃掉了 120MB"证伪）**：

```
$ .venv/Scripts/python.exe tools/mem_run.py --label abl-periphery --seconds 180 --mode ws \
    --code-root <base-worktree> \
    --override dynamic_island.enabled=false --override chat.enabled=false \
    --override agent_link.dsh=false --override agent_link.opencode=false
{ "ws_t15_mb": 164.86, "ws_late_avg_mb": 183.02, "ws_late_max_mb": 184.81,
  "clip_queue_frames": 24, "clip_queue_mb": 16.70, "qimage_mb": 19.09 }
# 对照 p180-base（同流程、同样开岛/chat/agent）：187.86 / 22 帧 / 16.70MB
# → 三条外围全关只省 4.8MB
```

**6) 边界与失败路径**：
- **legacy 拓扑照常**：`pkg-legacy` 用真 exe 起了老路径（t=15s 124.0MB），
  说明本改动的两条拓扑都真跑过（`library.py` 是两条拓扑共用模块）。
- **"本该被跳过"的负例**：测试 `test_release_idle_frames_keeps_playing_clip` /
  `..._keeps_live_reader_clip` / `..._skips_alive_thread_even_when_not_running` 断言
  **在播 clip、圈末驻留 clip、reader 尚存活但未在播的 clip 的队列必须原封不动**
  （帧数 2→2、显示槽清空次数 0）——即"该不动的一个都没动"在单元层被钉住。
- **单段坏对象**：`test_release_idle_frames_tolerates_broken_clip` 让一个 clip 的
  `_queue=None` 且 `clear_display_frame` 抛 `RuntimeError`，断言同池的健康 clip **仍被回收**
  （半销毁对象不得拖垮整池）。

**7) 无法自动验证的能力（给出为什么不能自动）**：
- 「点击/拖拽切换动画时会不会肉眼卡一下」：需要真实鼠标事件与 GPU 呈现时序，
  无法在无头口径自动判定。替代证据：① 回收只动"定时器已停 + reader 已死"的 clip，
  当前播放对象与其队列不满足判据（负例测试）；② `start()` 必重建队列（`webm_clip.py:1557`
  可读证），不存在"回退到被清空的旧队列"的路径；③ 480s 实机跑批期间桌宠动画连续
  （跑批日志无 `webm 解码失败` / `reader 退役池异常累积` 告警）。
- 「打独立设置进程是不是少付了这 7.7MB」：设置进程走 `pet/__main__.py --settings`，
  明确禁止导入 `pet.app`，本改动不在其路径上（`tools/import_cost.py` 已单独给出模块级数字）。

---

## 六、未采纳方向（尝试过 / 评估过但不做，附原因）

| 方向 | 评估结论 | 依据 |
|---|---|---|
| 岛卡片按需建（首次展开才 `_build_card`） | **不做** | 岛窗实测 129×44，卡片是 6 个空控件 + 1 个 stylesheet，整块 <1MB；而 `dynamic_island` 有 6 个测试族直接引用 `_card_box`/`_card_*`，风险与收益不成比例 |
| agent 桥按配置懒建 | **不做** | `pet.agent_link` 隔离值 9.93MB 看着大，但在真实导入序下只增量 **0.13MB**（T 口径 B `agent_link.py:1425`），因为 `multi_window_shared` 已经拉过它的依赖；且本配置 `dsh+opencode` 都开着，懒建省 0 |
| `pet.window` 延迟导入（overlay 拓扑不建 PetWindow） | **不做（受文件范围限制）** | `pet/platform_win.py` 在**模块级** `from .window import PetWindow`，而 overlay 拓扑必然导入 `platform_win`（`overlay_window` → `WindowsPerPixelInputController`）。把 app.py 的导入改懒只会把同一笔开销推到 `overlay_shell` 导入时，省 0。真正修法是 `platform_win` 改成 `TYPE_CHECKING` + 字符串注解，该文件不在本次文件范围 |
| `pet.voice_chime_service` 延迟导入 | **不做** | 真实配置 `self_talk_speak_enabled=true` 且 `click_show_self_talk=true` → `_chime_wanted()` 为真，服务本来就要建，懒 import 省 0 |
| 缩池 / 不建那 95 段冷池 clip 对象 | **不做** | 106 个 clip 对象本身只占 **0.37+0.33MB** Python 堆（T 口径 B `webm_clip.py:878/:909`），QTimer 132 个的开销也在 KB 级；真正的代价是它们**持有**的帧，已由第一刀解决 |
| 调 `QPixmapCache` 上限 | **不做** | `cacheLimit=10240KB` 是**上限**不是占用；普查里没有"缓存逼近上限"的证据，动它属于凭猜改参数 |
| 全屏合成面瘦身（缩小 overlay 窗口 / 按需 `setMask`） | **不做（受文件范围限制）** | 这是 +43MB 差价里最大的一块（`2560×1440×4=14.7MB`×1~2 份缓冲 + 合成开销），但 `overlay_window.py` 是只读参考、`overlay_shell.py` 在禁改名单 |
| `SetProcessWorkingSetSize` / `EmptyWorkingSet` / `malloc_trim` | **禁止** | 用户明令；这些只压 WS 数字不改真实占用 |
| 改报表口径（只换指标不换行为） | **禁止** | 同上；本报告所有 WS 都由同一个 2s 采样器给出，before/after 命令字面相同 |
| 首跑 25 reader 风暴错峰（provision 转换期间预热让路） | **未完成** | 属于"首跑一次性峰值 560MB"专项，与本次稳态目标不同轴；本次实测的部署产物里热集 11 段已帧序列化（`_internal/assets/characters/shenshen/frameseq` 12 个目录），跑批不会触发供给，故没有把它算进本次数字（见「未完成项」） |

---

## 七、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/library.py pet/app.py tests/test_library_idle_frame_trim.py tests/test_app_lazy_imports.py tools/` | **All checks passed!**（两刀的实现/测试/工具全部） |
| 第一刀新增单测（**先红后绿**） | `pytest tests/test_library_idle_frame_trim.py -q` | 红：`9 failed in 1.13s`（`AttributeError: 'MovieLibrary' object has no attribute '_on_idle_trim'` 等）→ 绿：`9 passed in 1.00s` |
| 第一刀回归面 | `pytest tests/ -q -k "library"` | `35 passed, 3290 deselected in 3.25s` |
| 第二刀新增单测 | `pytest tests/test_app_lazy_imports.py -q` | `20 passed`（主线补跑，d20d9fe 验收） |
| 聚焦（本次验收口径） | `QT_QPA_PLATFORM=offscreen pytest tests/ -q -k "library or frameseq or provision or shared or app or island"` | `400 passed, 1 skipped`（主线补跑，d20d9fe 验收） |
| 交付纪律 + 架构守卫 | `pytest tests/test_pr_report_discipline.py tests/test_architecture.py -q` | `43 passed`（主线补跑，d20d9fe 验收） |
| 全量 | `QT_QPA_PLATFORM=offscreen python -m pytest -q` | `3318 passed, 11 skipped`（主线补跑，门禁第 4 轮） |

### 环境中断说明（必须如实记录）

本会话在第二刀落地后、跑测试门之前，**主机的进程创建能力整体失效**：
所有 `pwsh` 调用（含子代理、含后台作业、含 `grep`/`ripgrep` 提供者）统一返回

```
Error: subprocess-local: Windows Job runner exited with exit code 3221225794 before proving its managed range empty
```

`0xC0000142 = STATUS_DLL_INIT_FAILED`。该故障发生在本次专项累计 **12 次真实 GUI 跑批
（每次都在桌面上起一只真宠、拉过 ffmpeg 子进程）之后**，与本改动无关（第一刀的全部
测试与 ruff 都在故障前已跑绿），但确实导致**第二刀与聚焦门未能执行**。

为此仓库内留了一份收尾脚本：`.scratch/_finish.ps1`（跑 ruff → 新测试 → 聚焦选择 →
纪律/架构守卫，**全绿才提交**，然后把两个提交与 `git log`/`numstat` 全部落进
`.scratch/_finish.log`）。恢复后执行：

```powershell
pwsh -NoProfile -File D:\dsh-pet-src\.scratch\_finish.ps1
```

**结论**：第一刀的测试门与静态检查已实测通过；第二刀只做了静态检查（ruff 通过）
与确定性证据（子进程 import 图 29.37→27.05MB），**功能测试门待补**，不计为已验收。

---

## 八、已知限制与后续

1. **本次只覆盖"单宠稳态 + 无交互"**：交互（点开岛卡片、开聊天窗、拖拽）路径下的增量
   没有实测，不在这份报告的数字范围内。
2. **多宠口径只测了打包版**：3 宠 330.6MB 是**未含第一刀**的旧 exe；第一刀在源码口径把
   增长源归零，预期对多宠同样成立（残留帧是**每只宠各自一份**），但**未做 3 宠 before/after**，
   列为未完成项。
3. **`FrameSeqClip._pending`（预取未上屏的 QImage 字典）不在本刀范围内**：
   `frameseq_clip.py` 在禁改名单 + 并行任务正在改它；第一刀只通过公开的
   `clear_display_frame()` 清其显示槽（实测 QImage 22.6→14.7MB 含这部分收益）。
4. **首跑一次性峰值（560MB）未处理**：见「未采纳方向」末条。
5. `tools/` 四个诊断脚本是"证据生产器"不是产品代码，默认不进打包产物（`packaging/` 的
   spec 只收 `pet`/`assets`）。

## 九、风险与回滚

- **影响面**：`pet/library.py`（素材池生命周期，两条拓扑共用）、`pet/app.py`（导入时点）。
  未改任何配置键、未改任何 schema、未新增持久化文件。
- **失败模式与兜底**：回收逐 clip `try/except`，任何单段异常只降级为"该段不回收"，
  绝不上抛到 Qt 事件循环（`_on_idle_trim` 外层再兜一层）；定时器随 `pause_warm()`/`shutdown()`
  停止，`MovieLibrary._shutdown_live_for_tests()` 的既有收口覆盖测试。
- **回滚**：`git revert` 第一刀 / 第二刀即可（无落盘状态残留、无配置迁移）。
  回滚后行为 = 改动前逐行一致（两刀都是"少做一件本来就该少做的事"，没有新增功能面）。

---

## 附：本报告全部数字的复现命令

```powershell
# 1) 打包版 A/B（用户基准口径）
.venv/Scripts/python.exe tools/ext_ws_probe.py --label pkg-overlay --exe dist-onedir/dsh-pet-standalone-webm-chat/dsh-pet-standalone-webm-chat.exe --seconds 200
.venv/Scripts/python.exe tools/ext_ws_probe.py --label pkg-legacy  --exe dist-onedir/dsh-pet-standalone-webm-chat/dsh-pet-standalone-webm-chat.exe --seconds 200 --env PET_RENDER_TOPOLOGY=legacy
.venv/Scripts/python.exe tools/ext_ws_probe.py --label pkg-3pets   --exe dist-onedir/dsh-pet-standalone-webm-chat/dsh-pet-standalone-webm-chat.exe --seconds 200 --keep-active-pets

# 2) 源码口径 before/after（--code-root 指向对应 git worktree）
.venv/Scripts/python.exe tools/mem_run.py --label p180-base --seconds 180 --mode ws --code-root <base-worktree>
.venv/Scripts/python.exe tools/mem_run.py --label p180-cut1 --seconds 180 --mode ws --code-root <cut1-worktree>
.venv/Scripts/python.exe tools/mem_run.py --label p480-base --seconds 480 --mode ws --code-root <base-worktree>
.venv/Scripts/python.exe tools/mem_run.py --label p480-cut1 --seconds 480 --mode ws --code-root <cut1-worktree>

# 3) 归因（Python 堆）
.venv/Scripts/python.exe tools/mem_run.py --label trace-base --seconds 180 --mode trace --code-root <base-worktree>
#    产物：.scratch/mem-probe/trace-base/snap/snap-final.txt（两套归因口径）

# 4) 一张表汇总
.venv/Scripts/python.exe tools/mem_report.py --all
```
