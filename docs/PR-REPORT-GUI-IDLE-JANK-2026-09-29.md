# GUI 空转与卡顿批次（I3 + F-PERF + G + H）：岛撞收敛、慢爬重绘、气泡跟随、轮询风暴、事件过滤器快路径、死窗口守卫（2026-09-29）

> **基线**：`ebf971e`（fix(collision): 拖拽成员速度通道）+ 工作树未提交 WIP
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-29　　**拓扑**：`PET_RENDER_TOPOLOGY=overlay`
> **范围**：6 个产品文件 + 10 个测试文件（3 个新增）
> **关联**：`.scratch/windows-parity-20260926-a/fix-20260928-I3/REPORT.md`、`fix-20260928-FPERF/REPORT-FPERF.md`、
> `.scratch/overnight-20260929/MORNING-REPORT.md`（G/H 两批的唯一文字记录）、
> [`PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md`](PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md) §十七（I1/I2，本批 I3 是同一课题的反馈侧）

## 一、核心特性

四个批次解决的是同一类问题：**在没有用户操作时也在烧 GUI 线程**。逐项：

| 批 | 项 | 结论 |
|---|---|---|
| I3 | 岛被撞的速度**无界** + `_animating()` 把已丢弃的通道当活跃 | **已修**：速度上限 + 动画时间预算 0.9s 强制收尾；连撞 60 击峰值 `_squish_v` 207 → ≤3.5、`_tilt_v` 109 → ≤40；风暴后收尾 66 tick → 57 tick |
| I3 | 桥内**重复派发**撞击音效 | **已修**：删掉 `island_bridge.on_collision` 里的 `self._sound.on_collision`，改由世界监听单入口——真世界 tick 的岛击音效回调 **2 次 → 1 次** |
| I3 | 拖岛期 overlay **穿透轮询未降档** | **已修**：新增 `drag_state` 挂点，真拖拽链实测 `set_drag_active` 调用 `[] → [True] → [True, False]` |
| F-PERF P1 | 慢速爬行**空转重绘**（亚像素位移也上报 dirty） | **已修**：180 拍 × 0.4px 中 109 拍整数矩形未变（= 改前白刷 109 次）；改后 `overlay.update` 251 → **142**（−43%），终态位置一致 |
| F-PERF P2 | 气泡跟随**全量重建 + 整窗重绘** | **已修**：纯平移 120 拍的重建/重绘 **120 → 0**；中途换几何 120 → **1** |
| F-PERF P3 | 目录轮询 **stat/glob 风暴** | **已修**：4 文件 0.987 → **0.513 ms/拍**；64 文件的文件侧系统调用 9.761 → **4.685 ms/轮** |
| G | 应用级 `eventFilter` 每个事件都过 Python + `super()` C++ 往返 | **已修**：非 KeyPress 第一行返回；单次 **4.40µs → 0.96µs（−78%）** |
| G | `PetSprite.rect()` 每 tick 每宠解析 + 新建 QRect | **已修**：记忆化 **2.30µs → 0.77µs（−66%）** |
| H | 死窗口（C++ 已销毁）仍收到在途帧回调 → `RuntimeError: ... already deleted` | **已修**：`overlay_window` 6 个异步投递入口加存活闸；守卫开销 **0.079µs/次** |

**红线 / 不变量**：
- **单次撞击的观感不许变**：峰值形变 0.85（压缩 6.6px）与峰值速度/倾斜与改前**数值一致**——
  上限取的就是单次最强撞击的速度（`1.15×3.0=3.45 ≤ 3.5`、`13×3.0=39 ≤ 40`）。
- **Esc 消费语义不许变**：`QObject.eventFilter` 基类实现恒返回 False（Qt 文档明载），
  非 KeyPress 分支直接返回 False **语义完全等价**；有测试钉住「真瞄准中 Esc 仍取消并吞掉事件」。
- **`rect()` 返回共享对象**：调用点拿到的必须是「取值当时的快照」（产品代码只有 `translated()` 这类 const 接口）。
- **帧交付节奏不变**：P1 只影响「何时上报 dirty」，不下调帧交付；I3 不改音效门/音量/播放后端。

## 二、修改文件说明

> **归因口径**：I3 的两行数字来自证据目录里的 **PRE/FIXED 源码快照逐文件 diff**（可复现，
> 见「四、性能分析」的命令）；其余文件是**相对 HEAD 的累计 diff**，不按批次拆分。
> `pet/dynamic_island.py` / `pet/pet_sprite.py` / `pet/overlay_shell.py` 都被多条线改过。

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/dynamic_island.py` | **+55 / −8**（I3 批，PRE→FIXED 实测）；累计 +150 / −10 | **I3**：速度上限常数 `_SQUISH_V_MAX`/`_TILT_V_MAX`、`_BUMP_ANIM_MAX_S = 0.9`、`bump()` 钳制 + 重置预算、`_animating()` 阈值提到感知量级、`_settle_bump_animation()` 收尾 helper（预算到点 + 自然停表两处调用）、`_on_anim_tick` 倾斜状态钳位、停表分支连速度一起归零 |
| `pet/island_bridge.py` | **+81 / −13**（I3 批，PRE→FIXED 实测）；累计 +182 / −24 | **I3**：删除 `on_collision` 内的 `self._sound.on_collision(event)`（`sound=` 入参保留，仅供 `overlay_shell.attach_island` 调用点兼容）；新增 `drag_state` 挂点 + `_notify_drag_state`（翻转才发、未置起不回发 False、异常静默）、`_update_motion` 转达、`detach()`/`set_visible(False)` 两条中断复位、`IslandWindowBridge._sync_island_drag`（写 overlay `_input_controller.set_drag_active`，鱼拖拽进行中不抢档） |
| `pet/pet_sprite.py` | +165 / −23（**累计**，含 F-PERF P1 + G 记忆化 + 更早 P2c） | **P1**：亚像素位移不再上报 dirty（跨整数像素才重绘，帧到位仍需上报）；**G**：`rect()`/`_logical_size()` 按签名记忆化 |
| `pet/speech_bubble.py` | +92 / −6（**累计**，含 F-PERF P2 + N2 常量） | **P2**：跟随平移复用表面路径、锚点未变不 reposition、几何真变才重建 + 重绘；换图（新 pixmap）仍必须重绘 |
| `pet/agent_link.py` | +145 / −19（**累计**，含 F-PERF P3 + N1） | **P3**：目录扫描节流（`scan_interval`）+ tailer 每读一次只 `stat` 一次（去掉 `is_file` + `stat` 双调用） |
| `pet/overlay_shell.py` | +1833 / −144（**累计**，含多条线） | **G**：`eventFilter` 快路径（非 KeyPress / 不消费的 KeyPress 就地返回 False，不构造 `super()` 往返） |
| `pet/overlay_window.py` | +126 / −5 | **H**：`_alive()`（`shiboken6.isValid(self)`）+ 6 个异步投递入口的存活闸（`tick_advance`、`_on_sprite_dirty`、屏信号回调、托盘/几何回调等），死窗口安静跳过而不是抛异常 |

### 测试

| 文件 | 增删 / 行数 | 覆盖 |
|---|---|---|
| `tests/test_dynamic_island_bump_convergence.py` | 新增 162 行 | I3：3 个用例（连撞收敛、预算收尾、单次观感不变） |
| `tests/test_island_bridge.py` | +230 / −10 | I3：改写 2 个音效用例（旧断言把「桥内派发」锁成期望）+ 4 个拖拽通道 + 3 个核心桥拖拽 |
| `tests/test_island_bridge_velocity.py` | +418 / −12 | I3：真岛拖拽端到端降档 |
| `tests/test_overlay_peripherals.py` | +108 / −24 | I3：1 个音效断言 + 头部说明 |
| `tests/test_pet_sprite.py` | +81 / −1 | P1：4 个新用例（亚像素不上报 / 帧挂起时仍上报 / 帧到位 / 跨像素边界） |
| `tests/test_speech_bubble.py` | +134 / −0 | P2：5 个新用例（含换图必须重绘） |
| `tests/test_agent_link.py` | +218 / −0（累计） | P3：扫描节流与 offset 语义 4 个新用例（与 N1 共文件） |
| `tests/test_overlay_shell_event_filter.py` | 新增 231 行 | G：契约不变 + 快路径确实生效（monkeypatch 计数，改前红、改后绿） |
| `tests/test_pet_sprite_geometry_memo.py` | 新增 208 行 | G：缓存命中、作废不漏、共享对象不引入别名事故 |
| `tests/test_dead_target_frame_callbacks.py` | 新增 158 行 | H：`shiboken6.delete(obj)` 造「窗口已销毁但回调仍被持有」，同款手法见 `test_menu_layout.py` |

### 未改动（故意）

`pet/collision.py`（数学）、`pet/config.py`（**未新增配置键**）、
`pet/overlay_window.py` 的绘制链本身（H 只加存活闸，不改绘制）。

## 三、实现要点

- **I3 为什么要「动画时间预算」而不是「速度衰减」**：连撞把弹簧泵到无界（207 / 109），
  单次撞击却完全正常。上限取单次最强撞击的速度即可**只切连撞拖出来的尾巴**，且预算按
  **动画时间**（不是墙钟）累计——单次撞击自然收尾 0.83s < 0.9s，故预算不切正常观感。
- **I3 音效为什么要回收到世界单入口**：桥与世界两条路径各派发一次 → 一次物理撞击响两声。
  删除桥内派发不是「去掉一个功能」，而是**去掉一次重复**（`sound=` 入参暂留以兼容调用点签名）。
- **P1 的边界**：亚像素位移在帧序列下本来就是「同一张图换位置」，不上屏不改变最终位置，
  只是把「每拍模糊一次」变成「跨 1px 重绘一次」；终态坐标有探针断言。
- **P2 的去重键**：`(锚点矩形, 窗口尺寸)`。若外部在不动锚点的情况下 resize 可见气泡，
  跟随拍会跳过落位（现无此调用点；`show_*`/`reflow` 都会走 `_place` 刷新记录）——
  换 pixmap 单独走一条「必须重绘」的分支（有变异检验，见下）。
- **H 的竞态是真的**：不只是测试污染——`overlay_shell` 屏热插拔重建 overlay 窗时，
  在途帧交付会打到旧窗。守卫是 `shiboken6.isValid`，不是 try/except 吞异常。

## 四、性能分析

**方法（可复现）**

| 项 | 命令 / 脚本 | 证据文件 |
|---|---|---|
| I3 岛撞收敛 | `.../fix-20260928-I3/probe_bump_frames.py`（真岛 + 真 `paintEvent`，dt=16ms，PRE/FIXED 快照换入对照） | `frames-before.txt` / `frames-after.txt` / `probe-springs.txt` |
| I3 批内行数 | `git diff --no-index --numstat .../PRE-dynamic_island.py .../FIXED-dynamic_island.py`（连岛桥各一次） | 本报告重跑，见下 |
| F-PERF | `.../fix-20260928-FPERF/probe-slow-crawl-p1.py`、`probe-follow-e2e.py`、`bench-FPERF.py` | `probe-slow-crawl-p1.txt` / `probe-follow-e2e.txt` / `bench-FPERF.txt` |
| G 实机占比 | `.scratch/overnight-20260929/fluency_run.py`（**真窗口**、3 sprite、900s ×2 轮）+ py-spy 采样 | `pyspy-fluency.json`（run1/webm）、`pyspy-fluency-run2.json`（run2/帧序列） |
| G 微基准 | 证据记录在 `.scratch/overnight-20260929/MORNING-REPORT.md:59-64`（**无独立原件目录**，见「已知限制」） | 同上 |
| H 守卫开销 | MORNING-REPORT「守卫开销 0.079µs/次」 | 同上 |

环境：Windows / `.venv` Python 3.13.7 / PySide6；Probe 级为 offscreen 真产品对象；
py-spy 那组是**真窗口**（脚本 docstring 明确「不要设 `QT_QPA_PLATFORM=offscreen`」）。

**I3 岛撞（重绘帧 / 空转帧 / 峰值速度；前 = PRE 快照，后 = FIXED）**

| 场景 | 重绘帧 | 空转帧 | 峰值 \|squish_v\| | 峰值 \|tilt_v\| |
|---|---|---|---|---|
| 单次最强撞击 | 55 → 52 | 28 → 25 | 2.98 → 2.98（不动） | 32.8 → 32.8（不动） |
| 连撞 10 击（60fps） | 84 → **60** | 33 → 26 | 15.0 → **2.98** | 109.3 → **32.8** |
| 连撞 40 击（60fps） | 106 → **90** | 23 → 26 | 19.2 → **2.98** | 109.3 → **32.8** |
| 稀疏连撞 30 击（每 4 tick） | 172 → **167** | 27 → 26 | 4.1 → **2.98** | 42.2 → **32.8** |

**F-PERF（端到端探针，真 `OverlayWindow`/`PetSprite`/`SpriteBubbleFollower`）**

| 指标 | 实测 | 归属 |
|---|---|---|
| P1 180 拍 × 0.4px：整数矩形未变的拍数 | **109**（改前白刷 109 次） | 热路径 |
| P1 `dirty_cb` 次数 / `overlay.update` 次数 | 71 次（old==new 为 0）/ **251 → 142（−43%）** | 热路径 |
| P2 纯平移 120 拍：表面路径重建 / 重绘 | **120 → 0 / 120 → 0** | 热路径 |
| P2 中途换几何：重建 / 重绘 | **120 → 1** | 热路径 |
| P2 微基准 | 气泡几何重建 64 → **11 µs/拍**；单次整窗重绘 0.675 ms（30Hz 即 20.3 ms/s）**被跳过** | 热路径 |
| P3 4 文件 × 200 拍 | 1.010（全量口径 0.987）→ **0.513 ms/拍** | 轮询 |
| P3 64 文件 × 200 拍 | 6.594 → **5.512 ms/拍**；文件侧系统调用 **9.761 → 4.685 ms/轮** | 轮询 |

**G：实机 py-spy 占比（本次补报告从同一份产物独立解析）**

```bash
cd D:/dsh-pet-src && .venv/Scripts/python.exe -c "<读 pyspy-fluency-run2.json：按 profile 取 samples，
统计栈顶帧名 eventFilter / rect / _logical_size 的占比>"
```

| 口径 | `eventFilter` | `rect()` | `_logical_size()` |
|---|---|---|---|
| run2 帧序列、MainThread 14814 样本、**栈顶（自占）** | **10.75%** | **4.41%** | **1.95%** |
| 证据记录值（MORNING-REPORT / 产品 docstring） | 9.4% | 2.1%（MORNING 作 ~3.4%） | 1.3% |
| 同一份产物的**栈出现率（含调用者开销）** | 14.9% | 6.5% | — |

—— 两个口径量级一致但**不是同一个数**：证据记录的 9.4%/2.1% 与本次解析的栈顶 10.75%/4.41%
互不矛盾、也不互相证明（采样窗口与聚合方式不同）。**登在表里，不做加总。**

**结论（逐条回答模板四问）**

1. **稳态开销**：全部为**下降**。最直接的稳态收益是 G 两项（`eventFilter` 是全应用每个事件
   都要过的路径、`rect()` 是每 tick 每宠数十次），以及 P1/P2 直接减少的 `overlay.update` 调用。
2. **新增路径成本与频率**：I3 每次撞击多一次浮点减法 + 两次比较（预算递减）；G 的 `rect()`/`_logical_size()`
   多一次签名比较（命中即返回对象）；H 的守卫 `0.079µs/次`（6 个入口，只在异步投递发生时才走）。
3. **新系统调用 / 网络 / 磁盘 / 线程**：**零新增**。I3/G/H 都不新增定时器或线程；
   P3 是**减少**系统调用（`is_file` + `stat` → 单次 `stat`，64 文件/轮 9.761 → 4.685 ms）。
4. **内存与缓存**：I3 零增长（无新容器，只多一个 float 字段）；G 新增一个 QRect + 两个整数签名
   （每 sprite 一条）；P2 缓存的是去重键而不是位图；**无新增长寿命缓存**。

## 五、实机运行记录

1. **真机 py-spy（G 批的依据，本机真窗口）**：`.scratch/overnight-20260929/fluency_run.py`
   以 `PET_RENDER_TOPOLOGY=overlay`、3 只 sprite、每 2.5s 全体抛掷、5s 一次气泡、900s × 2 轮
   运行，同时用 py-spy 采样。两份产物 `pyspy-fluency.json`（run1，webm 管线）与
   `pyspy-fluency-run2.json`（run2，帧序列管线）**都在磁盘上，本次补报告重新解析过**
   （上表）。同一批实机数据还给出：run2 帧序列下 tick 最大 76.1ms、GUI 心跳最大间隔 187ms、
   >250ms 动画断帧 **0 次**（run1 webm 每宠 23-25 次）。
2. **G/H 的产品改动本身没有独立证据目录**：两个批次的文字与数字只存在于
   `.scratch/overnight-20260929/MORNING-REPORT.md`（G 在 §「G批微优化」、H 在 §「H批」）。
   **本次补报告没有重跑它们的微基准**——本次只重跑了它们的**测试文件**（见 §六 末行：11 文件合并 110 passed）、
   并独立复算了 py-spy 占比；表里的 4.40→0.96µs / 2.30→0.77µs / 0.079µs 仍是**记录口径**。
3. **H 的现场复现（全量套件实锤）**：某个更早的用例泄漏了一只活着的 `PetSprite` + `FrameSeqClip`，
   它继续收帧 → 回调落到**已销毁**的 `ShellOverlayWindow`，抛
   `RuntimeError: libshiboken: Internal C++ object (ShellOverlayWindow) already deleted`
   （单独跑绿、全量红）。泄漏源定位到 `tests/test_feature_gating.py:67` 的 `AppShell.start()`
   （收口需扩 `_shutdown_live_for_tests`，**列为后续项，本批未修**）。
4. **I3 / F-PERF 全程 offscreen，未起桌宠**（证据报告自己写明）。I3 报告还诚实登记了一条
   **未收敛**的用例：`tests/test_sprite_sound.py::test_island_light_hit_uses_static_floor`
   在**改动前同样红**（换入 PRE 快照跑同一条 `-k` 选择：12 failed 含它），根因是
   `test_overlay_collision_toggle.py` 经真 `SpriteSoundPlayer` 排队了一次 `QTimer.singleShot(0)`
   播放却没抽干事件循环，延迟播放落到紧随其后的用例里 —— **既有缺陷、与本批无关**，
   一行修法（用例末尾补 `QApplication.processEvents()`）**本批未落地**（越界）。
5. **无法自动验证的能力**：① 真机观感——I3 的「拖岛撞鱼是否还卡」需要人在真合成环境下拖岛，
   证据报告明确写「本批全程 offscreen，未起桌宠」——主观视觉平滑度依赖实际合成器表现，
当前已通过 offscreen 物理参数与帧率探针完成数值闭环验证；
   ② 拖动半透明顶层窗 + 其下 overlay 重绘的 OS 合成税只能在实机 instrument；
   ③ 气泡跟随去重键在外部 resize 场景下的行为（现无调用点）。

## 六、测试与验证

| 批 / 门 | 命令 | 红（改前） | 绿（改后） |
|---|---|---|---|
| I3 聚焦 + 验收 | `pytest -q <I3 用例>` | **11 failed, 62 passed** | **102 passed**；相关面 95 passed；`ruff` All checks passed |
| I3 未收敛项 | `-k test_island_light_hit_uses_static_floor` | 改前同样红（既有缺陷） | 未修（见「实机运行记录」第 4 条） |
| P1 | `pytest -q tests/test_pet_sprite.py` | 3 failed / 1 passed | **4 passed** |
| P2 | `pytest -q tests/test_speech_bubble.py` | 3 failed / 1 passed | **5 passed** |
| P3 | `pytest -q tests/test_agent_link.py` | 2 failed / 12 passed | **14 passed** |
| F-PERF 汇总聚焦 | `pytest tests/ -k 'pet_sprite or speech_bubble or bubble or agent_link or tailer' -q` | — | **508 passed, 1 skipped, 3504 deselected** |
| F-PERF 变异检验 | 改 `P2` 去重键（`mutation-P2-imagekey.txt`） | 换图后不重建 → 用例判红（**断言有区分度**） | 还原后绿 |
| G | `pytest tests/test_overlay_shell_event_filter.py tests/test_pet_sprite_geometry_memo.py` | 快路径/memo 未落地时红（monkeypatch 计数与 `catalog` 读取计数） | **本次补报告现场复跑：绿**（见本表末行） |
| H | `pytest tests/test_dead_target_frame_callbacks.py`（`shiboken6.delete` 造死窗） | 全量套件里的 `already deleted` unraisable | **本次补报告现场复跑：绿**（见本表末行） |
| ruff | `ruff check --no-cache <改动文件>` | — | All checks passed（各批证据） |
| 全量（本批之前最后记录） | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | — | **3942 passed / 11 skipped / rc=0**（541.7s，`full-suite-20260928-b/`） |
| 全量（含本批，交接记录） | 同上 | — | **4158 passed**（`.scratch/HANDOFF-20260929.md:7`，**本次未复跑**）；**2026-10-01 已复跑：4187 passed / 0 failed** |
| **本批新用例（本次补报告现场复跑，唯一新跑的批次测试）** | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_overlay_shell_event_filter.py tests/test_pet_sprite_geometry_memo.py tests/test_dead_target_frame_callbacks.py tests/test_island_topmost.py tests/test_harness_ownership.py tests/test_library_shared_media.py tests/test_menu_tree_release.py tests/test_mem_probe_census.py tests/test_overlay_self_talk_image_cache.py tests/test_dynamic_island_bump_convergence.py tests/test_webm_meta_cache.py` | — | **110 passed in 8.12s（rc=0）**——11 个文件合并跑，含本批 G（`event_filter`/`geometry_memo`）与 H（`dead_target_frame_callbacks`）三个新文件 |
| 交付证据纪律 | `pytest tests/test_pr_report_discipline.py -q` | — | **55 passed**（补报告前基线 43 passed；补写 6 份 2026-09-29 报告后 +12 条参数化用例） |

## 七、已知限制与后续

1. **I3 两条拖拽源共用一个轮询档位**：鱼拖拽进行中时岛侧不抢档；若鱼在岛仍拖拽时松手，
   岛侧剩余拖拽期停在 10ms 档而不是 100ms（丢优化，不影响正确性）。彻底修需 overlay 侧引用计数
   （`overlay_window.py` / `platform_win.py` 在 I3 文件范围外）。
2. **I3 丢 release 事件的极端中断**：岛可见 + 鼠标捕获被抢 + 此后无几何回调 → `_dragging`
   一直为 True。已覆盖隐藏/摘桥两条复位路径；根治要装 stale-press 看门狗（= 新增常驻 timer，批纪律禁止）。
3. **`overlay_shell.attach_island` 仍传 `sound=self._sound`**：现在是**未使用的兼容入参**，
   建议后续从壳层删除实参并同步 `IslandBridge` 签名。
4. **P2 的已知边界**：不动锚点 resize 可见气泡会跳过落位；`P1` 改后亚像素位移期间不上屏
   （视觉由「逐拍亚像素模糊」变为 1px 粒度位移）。
5. **G 批没有独立证据目录**：微基准数字（4.40→0.96µs、2.30→0.77µs、0.079µs）只有
   MORNING-REPORT 的文字记录，**原件未落盘**——引用时按「记录口径」对待，本次只独立复算了 py-spy 占比。
6. **H 的泄漏源未修**：`test_feature_gating.py:67` 的 live sprite 泄漏仍在，本批只加了产品级守卫
   让竞态不崩；测试探针已收窄到本用例目录。
7. **本批全部 `pet/overlay_shell.py` 相关行数不可按批拆分**（累计 diff 含 09-24 起多条线）。

## 八、风险与回滚

- **影响面**：岛动画/音效派发/拖拽档位、sprite 脏区上报、气泡跟随、目录轮询节流、
  应用级事件过滤器、overlay 异步投递。无配置键变化。
- **回滚**：八项互不依赖，可逐项回滚；回滚不残留落盘状态。
- **失败模式**：Ⅰ）I3 上限取错会误切单次撞击观感（现已用「单次最强撞击速度」标定，并有
  `probe-springs.txt` 前后逐位相同作证）；Ⅱ）G 的 `rect()` 若被调用点原地改写，共享对象契约会破
  （产品代码已 grep 确认不存在，测试文件里零处改动动词）；Ⅲ）H 的守卫若误判存活，回调会被静默丢弃
  （失败模式是「少一次重绘」，下一帧自愈）。
