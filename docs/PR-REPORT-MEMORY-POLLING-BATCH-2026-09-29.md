# 内存与轮询批次（M1/M2/M3 + N1/N2/N3）：帧表去物化、菜单树泄漏、过采样缓存、桥目录轮询真 bug（2026-09-29）

> **基线**：`ebf971e`（fix(collision): 拖拽成员速度通道）+ 工作树未提交 WIP
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-29
> **范围**：6 个产品文件 + 1 个工具文件 + 7 个测试文件（2 个新增）
> **关联**：`.scratch/windows-parity-20260926-a/fix-20260928-M1M2/REPORT.md`、`fix-20260929-N/REPORT.md`、
> `PR-REPORT-MEMORY-DIET-SINGLE-PET-2026-09-24.md`（内存口径前作）、
> `PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md` §十四（R1 帧表懒列，本批 M1 是它的下一刀）

## 一、核心特性

过夜取证（`.scratch/overnight-20260929/MORNING-REPORT.md`）列出 6 个可省项，本批把其中
4 项查清并修掉，另 2 项如实纠偏（一个是测量假象、一个是现场已不可复现）：

| # | 项 | 结论 |
|---|---|---|
| M1 | 帧序列**帧表物化**（每段 241 个 `Path` 常驻且永不释放） | **已修**：路径按编号现推，`_frames` 换成 `_FramePaths`；探针实测常驻 Path 240 → **0**，Python 堆增量 232.5KB → 6.8KB |
| M2 | 右键菜单树**按次累积**（+255 QMenu / +1170 QAction per 15 轮） | **已修**：`release_menu_tree()` 抽成共用收口，overlay 两个 `exec()` 返回点接上；15 轮残留 **0 / 0** |
| M3 | mem_probe 读不出「爬稳态 vs 泄漏」 | **已修**：新增 `clip_listed_frames` 口径（数**物化**条目，不数逻辑帧数） |
| N1 | 桥目录轮询**真 bug**：按文件名字典序取前 64，活会话文件被挤出 | **已修**：改 mtime 倒序 + 清理「超龄且写者已死」（实机：活写者文件从名字序第 74 位 → mtime 序第 1 位） |
| N2 | 自言自语配图缓存**过采样**（代码注释写 10MB，实测 36.85MB） | **已修**：按显示盒 × DPR × 1.1 现算长边 + 签名门控；实机 24 张真素材 **36.85MB → 11.27MB**（scale 1.46）/ **5.27MB**（scale 1.00） |
| N3 | meta 磁盘缓存死条目 | **机制已修，但前提不可复现**：实机 4972 条里只有 1 条死（881.8KB，不是 2.9MB）——**不认领 2.9MB 收益** |

**红线 / 不变量**：
- M1 的 `len()`/`[]` 语义必须与旧列表**完全等价**（worker 只用到这两个接口）。
- M2 的释放语义必须与 legacy 路径**严格一致**（子菜单图标池 `clear()` + 50ms 轮询上限 3s + `deleteLater()`），
  且 **deferred 回调必须在菜单销毁前跑完**（实测次序 `['callback', 'destroyed']`）。
- N1 的目录 mtime 早退语义**原样保留**（节流不能被新实现绕开）。
- 不改 `pet/collision.py`、不改 `pet/config.py`（**未新增配置键**）、不改缓存条数上限与热路径。

## 二、修改文件说明

> **归因口径**：`git diff` 相对 HEAD 是**累计** diff；`pet/agent_link.py` 与
> `pet/overlay_shell.py` 被多条线改过，**不按行数拆分**。下表「本批」的依据是两份
> 证据报告逐函数记录的改动范围。

### 实现

| 文件 | 增删（相对 HEAD） | 改动意图 |
|---|---|---|
| `pet/frameseq_clip.py` | +235 / −21（**累计**，含 R1） | **M1**：新增 `_FramePaths`（`__len__`/`__getitem__` 按编号现推 `dir/f_%04d.webp`；`listed` 只在 meta 缺失时存 glob 兜底）；`_frames` 由 `list[Path]` 换成该序列；删 `_ensure_frames`/`_frames_ready`/`_frames_lock`（6 处调用点一并去掉） |
| `pet/context_menus/shared.py` | +41 / −0 | **M2**：新增 `release_menu_tree(menu)`（legacy 收口原样抽出：子菜单 `_animation_icon_pool.clear()` + 每 50ms `waitForDone(0)` 上限 3s + `menu.deleteLater()`，定时器绑 menu 作 context） |
| `pet/window.py` | +4 / −35 | **M2**：删除内联收口块，改调 `release_menu_tree(menu)`（行为逐位不变，`test_context_menu_lifecycle.py` 继续锁轮询语义） |
| `pet/overlay_shell.py` | +1833 / −144（**累计**，含 09-24～09-29 多条线） | **M2**：`ShellOverlayWindow.contextMenuEvent` 与 `_exec_full_menu_at` 在 deferred 派发之后各加一行收口（这两处此前从不释放，是 overlay 泄漏的实际入口）。**N2**：模块级 `self_talk_image_cache_edge` + `_SELF_TALK_IMAGE_CACHE_SLACK`；`_self_talk_screen_dpr/_self_talk_image_cache_edge/_self_talk_image_cache_signature/_refresh_self_talk_image_cache_for_dpr`；`_start_self_talk_image_load` 用现算 edge 预缩放；`_load_self_talk_settings` 签名门控；`handle_geometry_changed` 末尾接 DPR 变化重建 |
| `pet/speech_bubble.py` | +92 / −6（**累计**，含 F-PERF P2） | **N2**：新增 `SELF_TALK_IMAGE_BOX_W/H = 220/140`，`show_image` 标准盒改用该常量（缓存与显示共用一份数字） |
| `pet/webm_clip.py` | +328 / −10（**累计**，含共享素材库首帧表） | **N3**：新增 `_META_FILE_CACHE_DEAD`、`_meta_cache_source_path`、`_prune_dead_meta_file_cache`；`_get_meta_file_cache` 加载时**按父目录分组 `os.scandir`** 体检；`_save_meta_file_cache_entry` 合并后剔除死 key |
| `pet/agent_link.py` | +145 / −19（**累计**，含 F-PERF P3） | **N1**：新增 `_BRIDGE_STALE_FILE_AGE_S` / `_BRIDGE_STALE_CLEANUP_LIMIT` / `_BRIDGE_INSTANCE_FILE_RE` / `_bridge_writer_alive`；`_scan` 改走 `_scan_candidates`（scandir + mtime 倒序）；新增 `_cleanup_stale_dead_writers`（原 `_is_stale_dead_writer` 内联进循环，为的是能用「最旧端 + 预算」控制探活次数） |
| `tools/mem_probe.py` | +18 / −1 | **M3**：`_gc_census` 新增 `clip_listed_frames`（`getattr(obj,'_frames',None)` → `len(getattr(table,'listed',table))`，None/非法值安全）；`CSV_FIELDS`、`_sampler` 行、summary 的 `clip_listed_frames_late` 同步 |

### 测试

| 文件 | 增删 / 行数 | 覆盖 |
|---|---|---|
| `tests/test_menu_tree_release.py` | 新增 226 行 | M2：6 个用例（含 15 轮真实事件循环无残留） |
| `tests/test_mem_probe_census.py` | 新增 76 行 | M3：物化列表计长度、现推帧表计 0、None/非法安全 |
| `tests/test_overlay_self_talk_image_cache.py` | 新增 216 行 | N2：5 个用例（现算 edge、签名复用、DPR 重建） |
| `tests/test_frameseq_clip.py` | +481 / −5（累计） | M1：新增 `test_play_path_never_lists_frames_when_meta_is_authoritative`；**唯一被改断言的既有用例** `test_start_lists_frames_exactly_once` → 改名为「播放路径零 glob」（旧断言锁的是与 M1 目标直接冲突的行为） |
| `tests/test_overlay_tray_routing.py` | +67 / −12（累计） | M2：`_FakeMenu` 换成真 `QMenu` + 实例级 exec 桩（收口要求 builder 返回真实 QMenu）；**唯一被改的既有用例**，duck 替身无 `findChildren` |
| `tests/test_agent_link.py` | +218 / −0（累计） | N1：5 个新用例 + 2 处既有用例调整（见下） |
| `tests/test_webm_meta_cache.py` | +56 / −0 | N3：2 个用例 |
| `tests/test_overlay_self_talk.py` | +6 / −4 | N2：1 处断言收紧 |

**既有测试调整（逐条说明，来自证据报告）**：
1. `test_scan_interval_skips_repeated_glob_and_stats`：枚举实现 glob → scandir，计数桩随之从 `Path.glob` 改为 `os.scandir`，断言语义不变（节流期内零枚举）。
2. `test_directory_change_within_interval_is_discovered`：原用例把「当拍即发现」压在 OS 目录时间戳的及时性上；实测本机 Windows 目录 mtime 惰性更新（「建文件→stat→建文件」25/50 次不变）→ 高负载下随机变红（聚焦集复现 1 次）。改为显式 `os.utime` 推目录时间戳制造契约前提，**断言不放宽**。
3. `test_warm_self_talk_images_prescales_big_images`：断言从「长边 ≤640」改为「= 现算 edge」，否则旧断言继续把过采样行为锁成期望。

### 未改动（故意）

`pet/context_menus/menu_styles/modern.py` / `shared.py` 的 `aboutToShow.connect(lambda menu=menu: …)`
（实测 deleteLater 销毁 C++ 发送者即断开该连接、lambda 随之释放，残留 0，无需动根因写法）；
`pet/overlay_window.py:585` 基类 `OverlayWindow.contextMenuEvent` 的最小集菜单仍不收口
（生产只实例化 `ShellOverlayWindow`，该事件被 override，仅 demo/测试可达）。

## 三、实现要点

- **M1 为什么能去物化**：素材命名是转换器写出的连续 `f_%04d.webp`，帧数以 `meta.frames` 为权威，
  于是 `_frames[i] = dir/f_{i+1:04d}.webp` 可现推——**零 glob、零常驻**。兜底只在 meta 缺失/非法时
  保留 glob 列表（`listed`），把「meta 权威」变成可读的口径而不是隐含假设。
- **M2 为什么要共用收口**：菜单树以长命窗口为 parent，`exec()` 返回后不收口就按次累积。
  legacy 已有一段收口，overlay 两处 `exec()` 返回点从来没有——抽成同一个函数是为了**避免
  两份漂移**，而不是重构偏好。
- **N1 的取舍**：候选集从「名字序前 64」改成「mtime 倒序前 64」+ 清理「写者 pid 已死且超龄
  (>24h)」的陈旧文件（单拍最多体检/清理 8 个，从最旧端起）。代价是**新引入**一个偏移丢失窗口
  （见「已知限制」）。
- **N2 的缓存键**：`(清单路径+mtime+size, 目标长边)` 签名——`refresh_settings` 不再无条件
  清空重解 24 张图，签名不变直接复用。
- **N3 的体检方式**：按父目录分组 `os.scandir` 列名单（**不是**逐条 `exists`），
  实测 33.9ms vs 366ms（11~13x）。

## 四、性能分析

**方法（可复现，全部来自证据目录，本次补报告未重跑）**

| 项 | 命令 / 脚本 | 证据文件 |
|---|---|---|
| M1 帧表 | `.venv/Scripts/python.exe .scratch/windows-parity-20260926-a/fix-20260928-M1M2/probe-frames.py` | 同目录 `green-probe-frames.txt` |
| M2 菜单残留 | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe .../probe-menu-product-path.py [release\|norelease] 15` | `green-probe-menu.txt`（norelease 分支 = 等价改前） |
| N1/N2/N3 实机 | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe .../fix-20260929-N/probe_real_machine.py` | `fix-20260929-N/real-machine-probe.txt` |

环境：Windows / `.venv` Python 3.13.7 / PySide6；offscreen 探针用真 `OverlayWindow`/真 `PetSprite`；
N 批的探针读写**本机真实**桥目录、真实 `%TEMP%` 缓存与真实 24 张配图。

| 指标 | 实测 | 归属 |
|---|---|---|
| M1 构造+预热后常驻 `Path`（产品路径） | **1** 个（= clip 自带 `_dir`）；Python 堆增量 **6.8 KB** | 热路径 |
| M1 改前等价物 | 常驻 `Path` **240** 个；堆增量 **232.5 KB**（列表仍被引用，未释放） | 对照 |
| M1 外推（106 段 × 3 宠 = 318 clip） | 改前常驻 `Path` ≈ **76,320** 个 / **72.2 MB** Python 堆（M1 后为 0） | 外推 |
| M2 15 轮右键（产品调用点） | 改前 `QMenu` **+255** / `QAction` **+1170**；改后 **+0 / +0** | 热路径 |
| N1 桥目录枚举 | 旧（名字序）**2.05 ms/拍** → 新（mtime 序）**2.06 ms/拍**（等价）；实机目录 **172 → 12** 个文件（模拟清理后），每拍枚举量降 14× | 轮询 |
| N1 活写者命中 | 实机 5 个活写者中，`dsh-30652.jsonl` 名字序第 **74** 位（旧实现永读不到）→ mtime 序第 **1** 位（命中） | 功能 |
| N1 每拍白刷的陈旧 stat | 选中集合里 >24h 陈旧文件：旧 **62/64**、新 **60/64** | 轮询 |
| N2 配图缓存（24 张真素材） | scale 1.00：**36.85 MB → 5.27 MB**（−86%）；scale 1.46：**36.85 MB → 11.27 MB**（−69%） | 缓存 |
| N3 meta 体检 | 分组 `scandir` **33.9 ms** vs 逐条 `exists` **366.0 ms**（判定一致）；产品加载入口 4972 条 → 4971 条、**42.1 ms**（含 JSON 解析） | 启动一次 |
| N3 注入 2000 条死条目后 | 6972 条 / 1192.2 KB → 体检后 **4971 条 / 881.8 KB** | 机制验证 |

**结论（逐条回答模板四问）**

1. **稳态开销**：M1/M2 都**只减不增**——M1 把每段 ~240 个对象的常驻成本清零（外推 72.2MB
   Python 堆），M2 把按次累积变成 0；N1 每拍枚举耗时实测等价（2.05 → 2.06 ms，都在噪声内）。
2. **新增路径成本与频率**：N1 的清理是「单拍最多 8 个、从最旧端起」，只在有超龄死写者时发生；
   N2 的现算 edge 只在预缩放那一刻做一次（GUI 线程算好 DPR）；N3 的体检是**每进程一次**
   （33.9ms），落盘路径只花集合查找。
3. **新系统调用 / 网络 / 磁盘 / 线程**：无新增线程、无网络；N1 把「glob + 每拍 stat 最多 64 个」
   换成「scandir + 按 mtime 排序」，N3 把「逐条 exists」换成「按目录 scandir」（系统调用数下降）；
   N2 把「每次配置变更重解 24 张图」换成签名比对（CPU/IO 下降）。
4. **内存与缓存增长**：N2 的缓存从 36.85MB 降到 5.27/11.27MB；N3 的缓存**由体检保证不涨**
   （机制验证见上表最后一行）；M1 去掉一个**永不释放**的常驻结构。
   **纠偏**：过夜报告里「字体 87MB」是 psutil 映射尺寸的**测量假象**（真实常驻 4.1MB 共享页），
   本批**不认领**该项收益；「meta 缓存 2.9MB」的现场已不存在，同样不认领。

**整夜进程外观测（本次补报告从 CSV 现场复算，非证据报告原文）**

```bash
cd D:/dsh-pet-src && .venv/Scripts/python.exe -c "<读 .scratch/overnight-20260929/mem-20260929.csv 按 pid 分小时聚合 uss_mb>"
```

| PID（时段） | 样本 | USS 小时均值 | 备注 |
|---|---|---|---|
| 36764（00:05，1 条） | 1 | 127.0 | 开机基线点 |
| **18912（01:52–09:21，v3 之前的那一版）** | 450 | 01h 92.9 / 02h 93.2 / 03h 95.4 / 04h 96.6 / 05h 97.2 / 06h 94.9 / 07h 95.2 / 08h 102.8 / 09h 89.2 | 稳态 ~95MB，**回落而非单调爬升** |
| 33700（09:41–11:40） | 120 | 09h 102.3 / 10h 100.1 / 11h 86.8 | 重启后的版本 |
| 39276（16:07–20:50，v3 + 09-29 全部批次的部署版） | 284 | 16h 86.9 / 17h 63.7 / 18h 66.7 / 19h 64.6 / **20h 125.0（max 186.4）** | 见「已知限制」 |
| 子进程列（全部样本） | — | `children=0` | 三宠在**单进程**内（与顶置/共享素材库两批一致） |

配套的进程外 watchdog 记录（`.scratch/overnight-20260929/watchdog-notes.md`，每 2 小时一次）：

```
2026-09-29T02:28 ALIVE pid=18912, USS 91.6→95.3MB over 1h (+3.7MB/h，正常波动), RSS ~151MB, 无子进程
2026-09-29T04:29 ALIVE pid=18912, USS 95.3→97.9MB over 2h (+2.6MB, 缓速爬升仍属缓存暖化), RSS ~155MB
2026-09-29T06:29 ALIVE pid=18912, USS 97.9→94.6MB (回落, 确认是波动不是爬升), RSS ~151MB
```

## 五、实机运行记录

1. **N 批有真机取证（本机真实文件系统，不是 mock）**——`fix-20260929-N/real-machine-probe.txt`：
   - 真实桥目录 `C:\Users\me\AppData\Roaming\dsh-pet-bridge`：`dsh*.jsonl` 文件数 **172**、
     上限 `max_files=64`；活写者文件共 5 个，其中 `dsh-30652.jsonl` 名字序第 74 位（**落选**）、
     mtime 序第 1 位（选中）、最后写入 162.7 分钟前 —— 这就是 N1 那个「活会话永远读不到」的真 bug 现场。
   - 真实 `%LOCALAPPDATA%\Temp\dsh-pet-media-meta-cache.json` = 881.8 KB / 4972 条，
     其中源文件已不存在的 **1** 条、pytest 临时路径 **0** 条 —— **推翻了派单材料里「5497 条大半死条目」的前提**。
   - 真实 24 张配图 + 真实主屏 `devicePixelRatio = 1.0` 下的缓存字节（上表 N2）。
2. **M 批的取证是 offscreen 探针 + 真产品调用点**：探针经 `ShellOverlayWindow.contextMenuEvent`
   反复右键（真事件循环、真 `QMenu`），并另跑一条 `norelease` 分支（把 `release_menu_tree`
   换成 no-op = **等价改前代码**）作对照；帧表探针跑真产品路径（构造 + 预热）。**明确记录：
   M 批未在真机可见窗口下跑过桌宠。**
3. **整夜真机观测**：三宠部署版连续采样 450 行（01:52–09:21，60s 间隔，`mem_monitor.py`
   进程外只读采样），外加两份 watchdog 文字记录（见上表）。
4. **本该失败的路径（真机观察到了）**：N3 的体检在**真实缓存文件**上只逐出 1 条 →
   证据报告明确写下「**不要按 2.9MB 认领收益**」，而不是把注入 2000 条死条目的实验当现场。
5. **无法自动验证的能力**：M1 的收益在**整机**上的表现（需要真机三宠长跑对比 Python 堆，
   本批只有单 clip 探针 + 外推）；菜单泄漏在真机上「点开→关闭」的可见内存曲线
   （探针只数 QObject 残留，没有进程外 RSS 采样）。

## 六、测试与验证

| 门 | 命令 | 结果 | 出处 |
|---|---|---|---|
| M 帧表探针 | `... fix-20260928-M1M2/probe-frames.py` | 改前常驻 240 → 改后 1；`_frames` 非 list | `green-probe-frames.txt` |
| M 菜单探针 | `... probe-menu-product-path.py release 15` / `norelease 15` | norelease 分支 = 改前行为被稳定捕获（+255/+1170）；release 分支 0/0 | `green-probe-menu.txt` |
| M 聚焦（含时序列） | `pytest tests/ -k 'frameseq or menu or context_menu or mem_probe' -q -p no:cacheprovider` | **371 passed** | `green-focused-tests.txt` |
| M 关联族 | `test_frame_path_waste` / `test_flight_frame_pacing` / `pet_sprite*` / `sprite_*_tail` / `tick_driver` / `tray_icon_ready` / `overlay_recycle_settings` | 137 passed；`test_overlay_window\|shell\|window_capabilities\|spawn\|architecture` 81 passed；`test_overlay_tray_routing` 26 passed | 证据报告 |
| M 时序列 4×2 轮 | 显式读 exit code、禁管道计时 | **exit=0，41 passed ×8** | 证据报告 |
| N1 | `N1-red-baseline.txt`（把 `pet.agent_link` 换成只读旧基线 `base-2786c15`）：**6 failed / 4 passed** → `N1-green.txt` **10 passed** | 红→绿 | `fix-20260929-N/` |
| N2 | `N2-red.txt` **4 failed** → `N2-green.txt` **5 passed** | 红→绿 | 同上 |
| N3 | `N3-red2.txt`（临时禁用体检调用，验完即恢复）**1 failed** → `N3-green.txt` **19 passed** | 红→绿 | 同上 |
| N 验收聚焦 | `pytest tests/ -k 'agent_link or tailer or self_talk or speech_bubble or webm_clip or meta_cache' -q` | **453 passed, 1 skipped**（连跑 3 次稳定） | `focused-green.txt` |
| N 关联族 | `test_dsh_state/test_architecture/test_speech_bubble/test_overlay_window_capabilities/test_click_self_talk_speech` + `test_webm_*` | 96 passed + 63 passed | 证据报告 |
| ruff | `ruff check --no-cache <改动文件>` | All checks passed | `green-ruff.txt` |
| 全量（本批之前最后记录） | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | **3942 passed / 11 skipped / rc=0**（541.7s） | `full-suite-20260928-b/` |
| 全量（含本批，交接记录） | 同上 | **4158 passed**（`.scratch/HANDOFF-20260929.md:7`）；**2026-10-01 已复跑：4187 passed / 0 failed** | 交接记录，**本次未复跑** |
| **本批新用例（本次补报告现场复跑）** | 11 个批次测试文件合并跑（命令全文见 [`PR-REPORT-GUI-IDLE-JANK-2026-09-29.md`](PR-REPORT-GUI-IDLE-JANK-2026-09-29.md) §六；含本批 `tests/test_menu_tree_release.py`、`tests/test_mem_probe_census.py`、`tests/test_overlay_self_talk_image_cache.py`、`tests/test_webm_meta_cache.py`） | **110 passed in 8.12s（rc=0）** | 本次 |
| 交付证据纪律 | `pytest tests/test_pr_report_discipline.py -q` | **55 passed**（基线 43 passed + 6 份新报告 × 2 条参数化用例） | 本次 |

## 七、已知限制与后续

1. **N1 新引入的取舍**：候选集按 mtime 排，**长期空闲但存活**的会话文件可能被挤出 64 名；
   它下次写入时新 tailer 走 backfill，会跳过「被挤出 → 下一拍」之间写入的事件（≤`scan_interval` 5s）。
   旧实现对它是**永久**读不到，整体仍是改善；彻底消除要「退役 tailer 的 offset 记忆」，本批未做。
2. **N3 的实机前提不可复现**：若坚持 2.9MB / 5497 条的现场，需要拿到当时的缓存文件。
   本条按「防未来累积」计，**不认领收益**。
3. **N2 的已知偏差**：子宠共享缓存按主宠 edge 定尺寸（子宠另有自己的配图大小时 ≤3× 尺寸偏差）；
   直接改屏幕缩放而不触发布局事件时不在当拍重建，下次 refresh 收敛。
4. **`dsh*.jsonl.1`（桥插件一代轮转文件）不被 glob 匹配**，仍会累积——本批未动。
5. **`pet/overlay_window.py:585`** 基类最小集菜单仍不收口（生产不可达，仅 demo/测试路径）。
6. **无界爬升项已不在证据里**：过夜报告列出但**未修**的两项是 node 桥 41.9MB（→ 见
   `PR-REPORT-HARNESS-OWNERSHIP-2026-09-29.md`）与三宠三份素材库（→ 见
   `PR-REPORT-SHARED-MEDIA-LIBRARY-2026-09-29.md`）。
7. **部署版（PID 39276）最后一小时 USS 均值 125.0 / max 186.4**：本批未解释该上升
   （同小时采样点波动可达 ±100MB，无法从 60s 粒度归因）；**登记为观察项**，不当成回归也不排除。

## 八、风险与回滚

- **影响面**：帧表（每段起播路径）、右键菜单收口（legacy + overlay 两条）、桥目录轮询、
  配图缓存、meta 缓存加载。均无配置键变化、无持久化格式变化。
- **回滚**：逐项独立可回滚（M1 恢复 glob 列表、M2 回到「不释放」、N1 回到名字序、N2 回固定 640、N3 去掉体检）。
  回滚后**没有残留落盘状态**（meta 缓存被剔掉的死条目属「本来就该删」）。
- **失败模式**：M1 若 meta 与磁盘帧数不符，行为是**看门狗超时告警 + 空帧等待**（证据报告登记的
  取舍），不再是「空素材目录」报错。
