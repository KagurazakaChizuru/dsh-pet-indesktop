# 灵动岛置顶性丢失（岛被盖住后永不回位）修复（ISLAND-TOPMOST）（2026-09-29）

> **基线**：`ebf971e`（fix(collision): 拖拽成员速度通道）+ 工作树未提交 WIP
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-29　　**平台**：Windows（其它平台行为未验证）
> **范围**：2 个产品文件 + 1 个新增测试文件（11 条）
> **关联**：`.scratch/windows-parity-20260926-a/fix-20260929-ISLAND-TOPMOST/REPORT.md`、
> `.scratch/HANDOFF-20260929.md`（「岛顶层性修复（B批）：30s 心跳+点击回顶，已部署」）、
> `PR-REPORT-WINDOWS-PARITY-JANK-2026-09-27.md` §十七（I1/I2 同属灵动岛课题）

## 一、核心特性

**现象**：灵动岛被任何「激活过的顶层窗」盖住之后**永远回不到最上面**（要重启才恢复）。

**根因（Windows 语义）**：岛的旗标是 `Tool|FramelessWindowHint|WindowStaysOnTopHint|WindowDoesNotAcceptFocus`，
实机实测扩展样式 `0x08080088` = `WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST`。
topmost **带内**的先后次序 = **谁最近被激活/显示**；岛带 `NOACTIVATE` **从不激活**，
因此被任何激活的 topmost 窗（本进程的聊天窗/设置窗/岛对话气泡，或第三方置顶工具）盖住后，
Windows **不提供**「你被盖住了」的通知 → 永不回位。Qt 也只在 **flags 变化时**写一次
`WS_EX_TOPMOST`；对已可见窗口 `show()` 是 no-op，所以「设置里保存一次」并不会把它顶回去。

**回归定位（legacy 对照）**：`6ebfd2b`（2026-08-24）曾给 `pet/window.py` 加过
`_win_set_topmost`（`SetWindowPos HWND_TOPMOST`）+ `_win_is_topmost` + `_topmost_watchdog`（5s）+ 点击/拖拽结束
`raise_()`；**`ae6838a`（2026-08-27「modern desktop pet experience with upstream 3.1.1 integration」）把整块删除**
（`git show ae6838a -- pet/window.py` 可见 `-def _win_set_topmost` / `-def _enforce_topmost`）。
只读基线 `2786c15` 同样没有 → **属上游 3.1.1 合并回归，不是 overlay 改造引入**；
灵动岛更新（从未有过这套机制）。全仓 grep 另证：`dynamic_island` / `island_bridge` / `overlay_window` /
`platform_win` 里**既无 `raise_()` 也无 `SetWindowPos`** —— 岛没有任何重申机制
（也不是 `app.py` 的 hide/show 循环导致；`_sync_dynamic_island` 只 hide/show）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 原生置顶重申 | `platform_win._set_windows_topmost(hwnd, on, user32=None)`（`SetWindowPos` + `argtypes` 64 位安全） |
| 2 | 触发点 | `showEvent`（`singleShot(0)` 延后一拍）、`mousePressEvent`（点击回顶）、本进程窗口获得焦点、应用状态变 `Active`、**复用既有 30s 心跳** |
| 3 | 公开入口 | `DynamicIsland.reassert_topmost()`；非 win32 平台走 Qt `raise_()` 兜底 |

**红线 / 不变量**：
- **不新增定时器/线程**，**不改旗标**（`WS_EX_TOPMOST` 本来就在，问题在带内次序）。
- **不抢前台**：外部应用抢前台**不**重申（否则岛会反过来盖住开始菜单/全屏游戏）。
- 普通（非 topmost）窗口本来就盖不住岛；独占全屏由系统接管显示——这两类不在修复范围。

## 二、修改文件说明

> 归因依据 = 证据报告逐文件给出的本批行数（`pet/platform_win.py` +39/−0、
> `pet/dynamic_island.py` +84/−0）；下表累计列是 `git diff --numstat` 相对 HEAD 的值，
> 两者不可互相替代（`dynamic_island.py` 同时含 §十七 的 I1、09-28 的 I3 两批改动）。

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/platform_win.py` | **+39 / −0**（本批）；累计 +108 / −1 | 新增 `_set_windows_topmost(hwnd, on, user32=None)`：`SetWindowPos` + `argtypes`（64 位安全，避免 HWND 被截断）+ 6 个 HWND/SWP 常量。放在 `platform_win` 是因为它是本项目**已存在**的 win32 隔离层，测试可注入 `user32` 替身 |
| `pet/dynamic_island.py` | **+84 / −0**（本批）；累计 +150 / −10 | 新增模块级 `_native_reassert_topmost`（win32 原生路径，其它平台 False）；`DynamicIsland.reassert_topmost()` 公开入口 + `_on_own_window_focused`（焦点为本进程窗口）+ `_on_application_state_changed`（仅 `Active`）；接线：`_refresh`（复用既有 30s 心跳，**无新定时器**）、`showEvent`（`singleShot(0)` 延后一拍）、`mousePressEvent` |

### 测试

| 文件 | 行数 | 覆盖 |
|---|---|---|
| `tests/test_island_topmost.py` | 新增 **245** 行（未跟踪，11 条 = 9 条红→绿 + 2 条守卫） | 触发点接线（show/点击/焦点/激活）、非 win32 走 `raise_()` 兜底、外部抢前台不重申、不新增定时器、`SetWindowPos` 参数与 `argtypes` |

### 未改动（故意）

`pet/overlay_shell.py` / `pet/sprite_menu_facade.py`（overlay 本体也是 topmost，
`set_on_top` / 换屏重建时 `overlay.show()` 会把整屏合成窗插到岛上面——**本批文件范围外**，
由 ≤30s 心跳回位）；`pet/window.py`（legacy 路径未动，其 watchdog 也不必恢复）。

## 三、实现要点

1. **为什么不挂常驻 watchdog**：legacy 的 5s 轮询在 09-28 的降载批次里刚被削掉一半
   （隐藏/锁屏只降档）。本批复用岛**既有的 30s 心跳**（`_refresh`）——代价是最坏 30s 才回位，
   换「零新增 timer / 零新增线程」。
2. **为什么触发点要分四类**：
   - `showEvent` + `singleShot(0)`：显示瞬间 `SetWindowPos` 可能早于窗口真正上屏，延后一拍落定；
   - `mousePressEvent`：用户点岛就是「我要看它」的最强信号，当拍回顶；
   - 本进程窗口获得焦点 / 应用 `Active`：**盖住岛的元凶基本都在本进程内**（聊天窗/设置窗），
     这两条能把「本进程自己盖自己」的窗口及时纠正；
   - 30s 心跳：兜第三方置顶工具与「本进程非前台」的场景（≤30s）。
3. **为什么不对外部抢前台直接重申**：那会让岛盖住开始菜单、全屏游戏、任务切换器——
   这是明确写入证据报告的**产品红线**。

## 四、性能分析

**方法（可复现）**：本批的置顶探针
`.scratch/windows-parity-20260926-a/fix-20260929-ISLAND-TOPMOST/probe_topmost_zorder.py`
（**真桌面、真 HWND**，枚举 Z 序索引与 `WS_EX_*` 位）；证据输出 `real-machine-probe.txt`。

| 指标 | 实测 | 归属 |
|---|---|---|
| 岛窗口扩展样式 | `0x08080088`（含 `WS_EX_TOPMOST` + `WS_EX_NOACTIVATE`） | 既有事实 |
| 覆盖窗 `raise_()` 后 Z 序索引 | cover **7** < island **8**（索引越小越靠前 → **岛被盖住**） | 缺陷复现 |
| `reassert_topmost()` 后 Z 序索引 | island **7** < cover **8**（**岛上位**） | 新增路径生效 |
| 重申返回值 / 前台 | `_set_windows_topmost(...) = True`；**前台窗口未被岛抢走** | 新增路径 |
| 重申后 `WS_EX_TOPMOST` | 仍在 `True` | 不变量 |

**结论（逐条回答模板四问）**

1. **稳态开销**：**零新增常驻成本**——没有新定时器、没有新线程、没有轮询；
   只有既有 30s 心跳里多一次「枚举/重申」判断。
2. **新增路径的绝对成本与触发频率**：每次重申 = **一次 `SetWindowPos`**（win32 调用）。
   触发频率：岛显示一次、每次点击岛、本进程窗口焦点变化 / 应用激活、以及 30s 心跳一次。
   **没有单次耗时的计时实测**（证据报告未提供，本次补报告未重跑）——**登记为未验证**，
   不用「可忽略」代替数字。
3. **新系统调用 / 网络 / 磁盘 / 线程**：新增一次 `SetWindowPos` 系统调用（仅上述触发点）；
   **无网络、无磁盘、无新线程**。`raise_()` 兜底只在非 win32 平台走。
4. **内存与缓存增长**：零（不新增容器；焦点/激活回调只读既有对象）。

## 五、实机运行记录

1. **真机探针（本机真桌面、真 HWND，不是 offscreen）** —— `real-machine-probe.txt` 全文要点：

```
island hwnd=0x2d0d62 exstyle=0x08080088
  WS_EX_TOPMOST   = True
  WS_EX_NOACTIVATE= True
cover  hwnd=0x261364 exstyle=0x08080088

[复现] cover.raise_() 后：cover idx=7 island idx=8 (index 越小越靠前)
[重申] island.reassert_topmost()=True (platform_win._set_windows_topmost 返回 True)
[结果] 重申后：island idx=7 cover idx=8
[判定] 重申前被盖住=True；重申后岛上位=True
[判定] 重申后 WS_EX_TOPMOST 仍在=True
[判定] 前台窗口未被岛抢走=True
```

   —— 这同时是「缺陷真实存在」「修复真的改变 Z 序」「没有副作用（前台未被抢、旗标未丢）」三件事的直接证据。
2. **红 → 绿（隔离临时树，仓库未动）**：最终版测试文件 vs **还原本批改动后的产品码**：
   **9 failed, 2 passed**；挂上真实现后 **11 passed**。
3. **回归回归（25 个关联文件）**：`island*` / `dynamic_island*` / `overlay*` / `platform_win` / `app` / `window`
   等 → **230 passed** + **88 passed** + **636 passed, 2 skipped**；聚焦精选 **222 passed / 3913 deselected**；
   `ruff` + `compileall` 全过。
4. **部署（用户已验收这条修复的存在性）**：`.scratch/HANDOFF-20260929.md` 记「岛顶层性修复（B批）：
   30s 心跳+点击回顶，**已部署**」；部署包 exe mtime **09-29 15:52**、进程 PID **39276** 在跑
   （`CreationDate 2026/9/29 16:06:51`）——晚于本批收口（11:54）。
   **边界**：PyInstaller 把 `pet/**` 编进 PYZ，包内无 `.pyc` 可比对，属**时间序推断**，非字节级验证。
5. **本该失败 / 本该不动的路径（设计层面已锁，实机未逐一走）**：① 外部应用抢前台时岛**不**重申
   （否则会盖住开始菜单/全屏游戏）；② 非 win32 平台走 `raise_()` 兜底。
6. **无法自动验证的能力**：
   - **macOS/Linux 完全未验证**（`NSWindow` level 与 Windows topmost 带语义不同）；
   - **第三方 topmost 工具**在「本进程非前台」时抢走带顶，只能由既有 30s 心跳兜回（≤30s）；
   - **`focusWindowChanged` 在真机上的触发时机**未实机验证（offscreen 只能验接线）；
   - **overlay 本体也是 topmost**：`set_on_top` / 换屏重建时 `overlay.show()` 会把整屏合成窗插到岛上面
     （鱼可压住岛），同样只能由 ≤30s 心跳回位。

## 六、测试与验证

| 门 | 命令 | 红（改前） | 绿（改后） |
|---|---|---|---|
| 新增测试（隔离临时树对照） | `pytest -q tests/test_island_topmost.py` | **9 failed, 2 passed** | **11 passed** |
| 聚焦精选 | `pytest tests/ -k '<island/topmost 相关>' -q` | — | **222 passed, 3913 deselected** |
| 关联族（25 文件） | `pytest -q <island*/dynamic_island*/overlay*/platform_win/app/window 等>` | — | **230 passed** + **88 passed** + **636 passed, 2 skipped** |
| 静态 | `ruff check` + `compileall` | — | 全过（`green-ruff.txt`） |
| 全量（含本批，交接记录） | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | — | **4158 passed**（`.scratch/HANDOFF-20260929.md:7`，**本次未复跑**）；**2026-10-01 已复跑：4187 passed / 0 failed** |
| **本批新用例（本次补报告现场复跑）** | 11 个批次测试文件合并跑（命令全文见 [`PR-REPORT-GUI-IDLE-JANK-2026-09-29.md`](PR-REPORT-GUI-IDLE-JANK-2026-09-29.md) §六；含本批 `tests/test_island_topmost.py` 11 条） | — | **110 passed in 8.12s（rc=0）** |
| 交付证据纪律 | `pytest tests/test_pr_report_discipline.py -q` | — | **55 passed**（补报告前基线 43 passed） |

## 七、已知限制与后续

1. **macOS/Linux 未验证**：`reassert_topmost` 在非 win32 走 Qt `raise_()` 兜底，
   但 `NSWindow` level 与 Windows topmost 带语义不同，**不得外推**。
2. **第三方 topmost 工具**在「本进程非前台」时抢走带顶 → 最坏 ≤30s 回位；不新增轮询是批纪律。
3. **overlay 本体压岛**：`set_on_top` / 换屏重建时 `overlay.show()` 会把整屏合成窗插到岛上面，
   同样由 ≤30s 心跳回位——根治要改 `overlay_shell` / `sprite_menu_facade`（本批文件范围外）。
4. **岛自己始终重申带顶** ⇒ 本进程的瞬时气泡（语音气泡等）**不再长期压住岛**
   （岛对话气泡与岛有 8px 间隔，无重叠）——这是行为变化，登记为设计结果。
5. **单次 `SetWindowPos` 耗时未测**（见「性能分析」第 2 条）。

## 八、风险与回滚

- **影响面**：灵动岛窗口 Z 序（Windows）。无配置键变化、无落盘状态、不影响 overlay 与 sprite 世界。
- **回滚**：两个文件的改动可独立回滚；回滚后行为退回「被盖住后不再自动回位」——
  **无残留状态**（没有新增标记文件或持久化数据）。
- **失败模式**：① 若在错误时机（例如外部应用刚获得前台）重申，会抢走别人的置顶 —— 已用
  「外部抢前台不重申」这条红线挡住；② `SetWindowPos` 在某些 UAC/受保护窗口场景会被系统忽略，
  此时行为退回改动前（不崩、不报错）。
