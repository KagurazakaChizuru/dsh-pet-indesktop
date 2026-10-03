# 同角色多宠共享只读媒体视图 + 首帧解码跨库复用（SHAREDLIB）（2026-09-29）

> **基线**：`ebf971e`（fix(collision): 拖拽成员速度通道）+ 工作树未提交 WIP
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-29　　**拓扑**：`PET_RENDER_TOPOLOGY=overlay`
> **范围**：3 个产品文件 + 1 个测试约定文件 + 1 个新增测试文件
> **关联**：`.scratch/windows-parity-20260926-a/fix-20260929-SHAREDLIB/REPORT.md`、
> `.scratch/overnight-20260929/MORNING-REPORT.md`（「待你拍板」第 2 条：三宠共享素材库做不做）、
> `PR-REPORT-MEMORY-DIET-SINGLE-PET-2026-09-24.md`（内存口径前作）

## 一、核心特性

overlay 单进程多 sprite 下，**每只与主宠同角色的子宠都各建一份完整 `MovieLibrary`**：
各自 106 个 clip 对象、各自一份 `_paths`/manifest/`move_curves`、各自重算帧序列世代源哈希
（每段一次 sha256）、各自把同一批素材预热一遍。本批把「**只读数据**」进程级共享，
把「**播放态**」严格留在每只宠自己手里：

| # | 机制 | 说明 |
|---|---|---|
| 1 | 只读媒体视图按 (角色, 素材目录) 进程级共享 | `SharedCharacterMedia` + 弱值注册表；最后一个库被回收即整份失效（切角色/退出重进不留残影） |
| 2 | 低优先级池（99 段 clip 对象 + 逐段预热）只由**预热责任持有者**跑一次 | 兄弟库按需 lazy 建、不预热；持有者 `shutdown()` 时把责任**交接**给活着的兄弟库 |
| 3 | WebM 首帧解码结果按媒体身份**跨库共享** | 同进程任一库解出，其它库取用同一张 `QImage`（0 spawn / 0 解码），并覆盖「三库并发预热」窗口（有界等待 2s） |

**红线 / 不变量**：
- **播放态必须独立**：clip 实例、播放位置、定时器、`frameChanged`/`finished` 连接一律不共享
  （否决「同角色复用同一个 `MovieLibrary` 实例」方案的原因，见「实现要点」）。
- **单库行为逐位不变**：没有共享视图时 `claim_shared_warm` 恒 True，单库/异角色路径与共享前一致。
- **帧内容不因此多占**：共享表只存 `QImage` **引用**（PySide 隐式共享），且与 clip 侧首帧预算同值、
  设**硬上界**（全 pin 也逐最久未用）。

## 二、修改文件说明

> 归因依据 = 证据报告逐函数记录的改动范围（含「新增 / 改既有」逐条列出）；
> 下表「本批约」是证据报告给出的规模，累计列是 `git diff --numstat` 相对 HEAD 的值
> （`pet/library.py`、`pet/webm_clip.py` 含更早的多条线 WIP），**两者不可互相替代**。

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/library.py` | +539 / −55（**累计**；本批约 **+330**，另改 6 处既有函数体） | 新增 `_SHARED_MEDIA`（`WeakValueDictionary`）+ `shared_media_key` / `lookup_shared_media` / `publish_shared_media` + `PEER_FIRST_FRAME_WAIT_S`；新增 `SharedCharacterMedia`（`__slots__` + `__weakref__`，`claim_warm_owner` / `is_warm_owner` / `release_warm_owner`）；`__init__` 尾部走 `_adopt_shared_media`（命中：不读盘、不哈希、不重建表）或 `_publish_shared_media`；`_load_all` 只保留「读 manifest/路径/帧序列世代」，高优先级 clip 建立拆到 `_register_high_priority`（顺带把交互核素材 pin 进跨库首帧表）；`_priority_names` 拆出 `_build_priority_names`（返回浅拷贝防改写共享表）；`rescan_frameseq` 由「重新绑定 dict」改为**就地**清空+填充（兄弟库持有同一 dict）；新增 `_warm_frame` / `_await_peer_first_frame`（2s 宽预算 + 20ms 轮询，`_warm_paused`/`_shutdown` 立即放弃）；`shutdown` + 新增 `_hand_off_shared_warm`；`resume_warm` 每次重新认领；新增 `claim_shared_warm` |
| `pet/webm_clip.py` | +328 / −10（**累计**；本批约 **+190**，另改 3 处既有函数） | 新增跨库首帧共享表（`_ffr_share` / 锁 / 字节账 / `_ffr_share_pinned` / 统计与 `_ffr_share_key`、`_ffr_share_trim_locked`、`share_first_frame`、`shared_first_frame`、`shared_first_frame_ready`、`pin_shared_first_frame`、`bump_first_frame_spawns`、`first_frame_share_stats`、`reset_first_frame_share`）；`set_first_frame_budget` 同步更新共享表预算；`WebMClip.FIRST_FRAME_WARM_ADOPTABLE = True`；`_decode_first_qimage`（首帧解码唯一入口）开门先查共享表，命中直接返回同一张 `QImage`；`_store_first_frame` 幂等发布（锁序：clip 首帧锁 → 共享表锁，单向） |
| `pet/frameseq_clip.py` | +8（累计 +235 / −21，含 R1/M1） | `FrameSeqClip.FIRST_FRAME_WARM_TRIVIAL = True` + 类注释：帧 0 冷解码 ~1.2ms 且 `start()` 本就异步交付首帧，兄弟库不重复预热（也不因此把 7 段 × 0.88MB 的帧常驻——那正是 O1 真机 A/B 撤回的 17.5MB） |
| `tests/conftest.py` | +4 / −0 | 逐用例收口里补 `webm_clip.reset_first_frame_share()`：共享表强引用 `QImage`，不清会跨用例常驻并污染命中计数 |

### 测试

| 文件 | 行数 | 覆盖 |
|---|---|---|
| `tests/test_library_shared_media.py` | 新增 **558** 行（未跟踪，14 例） | 视图共享 / 生命周期 / 低优先级池推迟 / 责任交接 / 隐藏恢复不改归属 / 兄弟库跳过廉价帧预热 / webm 首帧共享 / 并发预热 / 三宠共享 / 切角色重建；另 4 例为「改动前后都该成立」的守卫（异目录不共享、按需建 clip、同名 clip 播放态独立、共享表硬上界） |

### 未改动（故意）

`pet/overlay_shell.py` / `pet/app.py` **零改动**——共享在 `MovieLibrary` 内部自动生效
（`app._create_library` 建库 + 排预热是唯一入口，overlay 子宠库、切角色重建、`_spawned_libs`
清理路径全部不需要动）。`pet/config.py` 未新增键。

## 三、实现要点

1. **为什么否决「同角色复用同一个 `MovieLibrary` 实例」**：`library.movie(name)` 会返回**共享 clip**，
   而 sprite 侧持有的是 clip 实例本身（`pet/pet_sprite.py:677 self._clip = library.movie(name)`）
   并连接其 `frameChanged`/`finished`——两只宠播同名 clip 就是共用播放位置与定时器，
   直接违反「播放态必须独立」的硬约束。
2. **采用 B+：共享不可变数据 + 播放态 per-pet + 预热责任单点 + 首帧解码共享**。切片边界是
   「库创建后无人写入」的只读数据：manifest 分类表、`name→路径`、`folder_map`/`folder_files`、
   `no_mirror`、`move_strides`/`move_curves`、`paths`、帧序列世代映射、优先级分类表。
   唯一例外是 `rescan_frameseq`——改成**就地**更新，兄弟库共享同一 dict 因而同帧可见。
3. **预热责任为什么需要交接**：责任持有者 `shutdown()` 时若只是「不预热了」，则「主宠退出 →
   子宠被提升为主」之后就**没人预热**了——所以显式 `_hand_off_shared_warm` 给第一个活着的兄弟库；
   `resume_warm` 每次重新认领，交接后隐藏/恢复也能接手，**不需要常驻轮询 timer**。
4. **并发窗口**：三库连续 spawn（活跃清单复活）时三份高优先级预热是并发的，谁都还没解出 →
   表是空的，各自 spawn（实测 3 库 × 4 段 = 12 次）。因此兄弟库预热 `WebMClip` 前**有界等 2s**；
   等不到（持有者隐藏/退出）照旧自己解，**正确性不依赖等待成功**。

## 四、性能分析

**方法（可复现）**

```bash
# 红（关掉共享两条通路 = 改动前代码路径，用例一字未改）
QT_QPA_PLATFORM=offscreen PYTHONPATH=.scratch/windows-parity-20260926-a/fix-20260929-SHAREDLIB \
  .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -p old_path_plugin \
  tests/test_library_shared_media.py          # → 10 failed, 4 passed
# 绿
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider \
  tests/test_library_shared_media.py          # → 14 passed
# 计数/字节口径探针
.venv/Scripts/python.exe .scratch/.../fix-20260929-SHAREDLIB/measure_shared.py
.venv/Scripts/python.exe .scratch/.../fix-20260929-SHAREDLIB/measure_webm_spawns.py
.venv/Scripts/python.exe .scratch/.../fix-20260929-SHAREDLIB/measure_clip_weight.py
```

环境：Windows / `.venv` Python 3.13.7 + PySide6、`QT_QPA_PLATFORM=offscreen`、
真素材 `assets/characters/shenshen`（**106 段**，帧序列世代齐全）、`PET_FRAMESEQ=0`。
「改动前」= 同一进程内把 `lookup_shared_media` 与 `shared_first_frame` 打回 no-op
（**等价改动前的代码路径**，不是另一份构建）。

**A. 三份同角色库（真素材 106 段，默认 balanced 预热策略）**

| 指标 | 改动前 | 改动后 | 单库口径 |
|---|---|---|---|
| clip 对象总数（3 库） | 318（106/库） | **120**（106 + 7 + 7） | 106 |
| 预热期帧 0 解码次数（FrameSeqClip 真解码） | 21 | **7** | 7 |
| 帧序列世代源哈希次数（每段一次 sha256） | 318 | **106** | 106 |
| 私有内存（稳态，3 次采样中位） | +4.7 MB | **+2.35 MB** | — |
| 建库即达私有内存高水位 | +15.5 ~ +16.1 MB | **+0.2 ~ +1.2 MB** | — |
| `_paths` / `_frameseq_dirs` 是否同一对象 | 否 | **是** | — |

**B. 无帧序列（真 webm，ffmpeg 首帧路径）三库预热 spawn 次数**

| 场景 | 改动前 | 改动后 | 单库口径 |
|---|---|---|---|
| 4 段交互核、三库**顺序**预热（balanced） | 12 | **4** | 4 |
| 4 段交互核、三库**并发**预热（balanced） | 12 | **4** | 4 |
| 6 段（含低优先级池，`media_prewarm=full`） | 18 | **6** | 6 |

**C. 单 clip 对象私有内存重量**（`measure_clip_weight.py`，N=200 实测）

- `FrameSeqClip` ≈ **5.2 KB/clip**；`WebMClip` ≈ **12.9 KB/clip**。
- 由此：省下的 198 个 clip ≈ **1.0 MB**（FrameSeqClip 口径），与 A 表 +2.35MB 的稳态差值同量级
  （含 212 次重复哈希的保留缓冲）。

**纠偏（重要）**：派单材料里的「28.7KB/clip、3 库合计 ≈15MB」**未能复现**——
按实测重量，本批的**内存收益是 1~2MB 级，不是 15MB 级**；主要收益在 **CPU/IO 与稳态分配次数**
（少 212 次 sha256、少 8 次 ffmpeg spawn、少一份 99 段 clip 对象的构造与预热）。

**结论（逐条回答模板四问）**

1. **稳态开销**：下降——3 库的私有内存稳态 +4.7MB → **+2.35MB**，建库瞬时高水位
   +15.5~16.1MB → **+0.2~1.2MB**（后者是「三份库同时把同一批素材读进内存」的峰值，收益最直观）。
2. **新增路径成本与频率**：共享表的查表是字典命中（键 = `路径|mtime_ns|size`）；
   责任认领/交接只在库创建、`shutdown`、`resume_warm` 时发生；`_await_peer_first_frame`
   只在**兄弟库预热 WebMClip 前**发生，且**等不到就自己解**（最坏退化为改动前行为，多花 ≤2s 等待）。
3. **新系统调用 / 网络 / 磁盘 / 线程**：**无网络、无新线程**；
   磁盘侧显著减少（少 212 次源文件 sha256）；`ffmpeg` spawn 次数 12→4 / 18→6。
4. **内存与缓存增长**：新增一个进程级首帧表，**有硬上界**（与 clip 侧首帧预算同值、逐最久未用淘汰、
   只存 `QImage` 引用）；无新增长寿命缓存；共享视图本身由弱值注册表管理，最后一个库回收即释放。

## 五、实机运行记录

1. **本批验证时未做真机（可见窗口）验证（已于 2026-10-01 补齐三实例同屏实机截图，见文末「第二轮补充」）**——证据报告自述「本批派发禁止起桌宠/全量套件，
   故证据为 **offscreen 实例 + 探针脚本**；真机可见窗口下的观感（点击首帧、切角色）尚未由人眼确认」。
   **这条是诚实的空白，不是遗漏。**
2. **真素材真路径**：全部口径都用真素材 `assets/characters/shenshen`（106 段、帧序列世代齐全）
   与**真的** `MovieLibrary` / `WebMClip` / `FrameSeqClip`；「改动前」由关掉两条共享通路实现
   （`-p old_path_plugin`），因此前后对比是**同一进程、同一素材、同一策略**。
3. **部署时间序（本批之后确实出包）**：`D:/dsh-pet/dsh-pet-standalone-webm-chat.exe` mtime **09-29 15:52**、
   部署进程 PID **39276** 在跑（`CreationDate 2026/9/29 16:06:51`、`--slot 0`）——晚于本批收口（09:10）。
   **边界**：PyInstaller 把 `pet/**` 编进 PYZ，包内无 `.pyc` 可比对，故这是时间序推断而非字节级验证。
   三宠在**单进程**内这一点有独立证据：整夜内存 CSV（`.scratch/overnight-20260929/mem-20260929.csv`）
   的全部样本 `children=0`。
4. **一次未复现的原生 access violation（登记不销案）**：改后首次跑验收命令时 pytest 在第 47 个用例
   （`tests/test_frameseq_clip.py::test_retained_frame_is_not_reused_as_frame_zero`，FrameSeqClip
   单元用例，不碰本批任何机制）**原生崩溃退出（无 summary）**。随后同命令连跑 3 次全绿（552 passed），
   该用例单文件连跑 3 次、与本批新用例合并连跑 5 次均全绿；**无僵尸 pytest 进程残留**。
   按 §14 判据（先读日志再看是否回归）记为**未复现的原生 flake**，未定位到与本批改动的因果链。
5. **无法自动验证的能力**：真机点击首帧/切角色的观感（需人眼 + 可见窗口）；
   兄弟库 2s 有界等待在真机隐藏/恢复时序下的行为（探针覆盖了 `_warm_paused`/`_shutdown` 早退，未覆盖真隐藏）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 红（关共享 = 改动前路径，用例一字未改） | `QT_QPA_PLATFORM=offscreen PYTHONPATH=...python -m pytest -q -p no:cacheprovider -p old_path_plugin tests/test_library_shared_media.py` | **10 failed, 4 passed**（失败项：视图共享/生命周期/低优先级池推迟/责任交接/隐藏恢复不改归属/兄弟库跳过廉价帧预热/webm 首帧共享/并发预热/三宠共享/切角色重建；4 个通过项是改动前后都成立的守卫） |
| 绿 | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_library_shared_media.py` | **14 passed** |
| 聚焦绿 | `pytest tests/ -k 'library or overlay_shell or spawn or movie or warm or frameseq or webm' -q -p no:cacheprovider` | **552 passed, 1 skipped, 3550 deselected**（114s）；**连跑 3 次稳定** |
| ruff | `ruff check --no-cache pet/library.py pet/webm_clip.py pet/frameseq_clip.py pet/overlay_shell.py pet/app.py tests/test_library_shared_media.py tests/conftest.py` | All checks passed |
| 全量（本批之前最后记录） | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | **3942 passed / 11 skipped / rc=0**（541.7s，`full-suite-20260928-b/`） |
| 全量（含本批，交接记录） | 同上 | **4158 passed**（`.scratch/HANDOFF-20260929.md:7`，**本次未复跑**）；**2026-10-01 已复跑：4187 passed / 0 failed** |
| **本批新用例（本次补报告现场复跑）** | 11 个批次测试文件合并跑（命令全文见 [`PR-REPORT-GUI-IDLE-JANK-2026-09-29.md`](PR-REPORT-GUI-IDLE-JANK-2026-09-29.md) §六；含本批 `tests/test_library_shared_media.py` 14 例） | **110 passed in 8.12s（rc=0）** |
| 交付证据纪律 | `pytest tests/test_pr_report_discipline.py -q` | **55 passed**（补报告前基线 43 passed） |

## 七、已知限制与后续

1. **`maybe_provision_frameseq` 仍是每库一个 worker**：三个 worker 各扫一遍 `plan_clips` 的源哈希
   （≈53MB/库）。进程级迁移配额保证「每个启动周期最多转 1 段」跨库共享，所以重复的是**扫描**而非**转换**。
   不改它的原因：兄弟库若跳过供给，责任持有者提前退出就没人补供，要动「配额跨库共享 / 回退补供」契约，**超出本批风险预算**。
2. **`full` 策略下兄弟库的随机池帧 0 不再预热**：兄弟库播放池内动画时按需建 clip，其首帧优先从共享表取；
   只有「责任持有者还没走到这一段」时才露出旧帧 ~60–166ms —— 与改动前「兄弟库自己的单 worker 也没排到」是同一状态，**非新增退化**。
3. **兄弟库有界等待上限 2s**：持有者被隐藏/挂起/退出时等不到就自己解，只是这一次不省。
4. **原生 flake 未销案**（见「实机运行记录」第 4 条）。
5. **未做实机（可见窗口）验证**（见「实机运行记录」第 1 条）。
6. **`AGENTS.md` / `docs/` 未动**：本批文件范围不含它们；证据报告已写明「PR 报告文档与 INDEX 登记
   需由主控补齐」——**本报告与 INDEX 登记就是这项补齐**。

## 八、风险与回滚

- **影响面**：库创建（含子宠 spawn / 切角色重建）、预热调度、WebM 首帧解码、帧序列重扫。
  无配置键变化、无落盘格式变化。
- **回滚**：`library.py` + `webm_clip.py` + `frameseq_clip.py` 一处回滚即可（共享注册表命中即整份失效，
  回滚后旧的「每库一份」行为立即恢复）；`tests/conftest.py` 的 `reset_first_frame_share()` 在回滚后成为无害调用。
- **失败模式**：① 共享表若无限生长会被硬上界挡住（逐最久未用淘汰，代价是重解一次首帧）；
   ② 责任交接若在极端时序下丢失，最坏结果是「低优先级池没人预热」（帧按需建，功能不受影响，只是慢）；
   ③ 兄弟库 2s 等待超时 = 回退到改动前行为。

---

## 第二轮补充（2026-10-01）：可见窗口实机证据

原报告 §五 登记的「没有可见窗口验证」已补：部署宠（D:\dsh-pet，本分支构建）当前
**三只 shenshen 同屏**（同一角色三实例）。**静态截图只支撑「某时刻三实例同屏渲染正确」**；「各自独立播放、无错帧/闪屏、
共享对象身份」由 `tests/test_library_shared_media.py` 14 条覆盖承担（复跑全绿）——
「共享」机制在画面上不可观测，单张静帧不支撑任何时间性结论。
证据图：`.scratch/pr-review/evidence-shared-media-3pets.png`（2026-10-01 09:4x 实机截取，
1568×882 缩放图，部署显示环境 2560×1440）。

配套运行证据：同实例日志「素材加载完成：shenshen 106 段动画」+「帧序列映射 106 段」
（供给零失败），即共享视图下 106 段全部按世代采纳播放。
