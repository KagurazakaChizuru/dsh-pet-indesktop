# PR 报告：输入链路两处残留收口（屏事件 grab 收尾走协议 + 右键进弹弓的判据收紧）

> **基线**：`53d0587`（fix(frameseq): 清理 alpha=1 背景残留并更新素材世代 #292，`origin/main`；
> 本片开工时是 `056dc2a`，冻结内容期间 main 前进了一次，按口径只合 main、只有 `INDEX.md` 一处并集冲突）
> **分支**：`fix/input-grab-release`（worktree `D:/dsh-pet-wt-input-final`，**已 push**）　**日期**：`2026-10-17`
> **范围**：11 个文件（实现 3：`+49 / −13`；测试 5：`+369 / −21`；文档 3：本报告 605 行新增
> + `INDEX.md` `+2 / −1` + 穿透修复报告追加 `+21`）——合计 `+1046 / −35`
> **关联**：本报告收的是 [`PR-REPORT-CURSOR-PASSTHROUGH-2026-10-15.md`](PR-REPORT-CURSOR-PASSTHROUGH-2026-10-15.md)
> §三 列出的两条同族残留（该报告 §七 已回填交叉引用）。另有**一处与本片两条产品改动无关的
> 测试侧收口**（`tests/test_proactive.py` 的前台窗口用例，见 §六之二／§七 第 5、6 条）。

## 一、核心特性

桌面宠的输入链路里有两条**已登记但未修**的残留（来源：穿透卡死修复的三轮审查，
`docs/PR-REPORT-CURSOR-PASSTHROUGH-2026-10-15.md` §三）。两条都不改变正常交互的
观感，改的是"状态机出口是否走完整协议"与"入口判据是否放过了不该放的行"。

| # | 缺陷（用户能感觉到的形态） | 根因 |
|---|---|---|
| 1 | 拔屏 / 换屏的那一刻刚好在拖拽或长按（锁定位）宠：那次会话的收尾只清了一半字段——吸附式穿透轮询停在"拖拽降频"档（10ms→100ms 不再复位）、壳层那笔被 grab 闸住的穿透收敛（`_converge_pending`）永久滞留（窗口可见却点不到）、`_press_click_only`/`_drag_committed` 旗标留在窗上 | `OverlayShell._end_drag` 自己清 `_mouse_grab`/`_press_global` 就返回，不走窗口既有的 `_finish_grab` 收尾协议，也不发壳层收尾通知 |
| 2 | 开了「锁定位置」（或「必须按住 SHIFT 才能拖」）时，在宠身上**按住不动**再点右键：宠被弹弓蓄力"弹"了出去——锁定位/ SHIFT 门当场失效 | `OverlayWindow.mousePressEvent` 的右键分支只看 `_mouse_grab is not None`，不看清这次按下到底有没有拖拽资格 |

改后：

- 两条出口统一走既有协议/既有判据，**没有新增任何兜底路径、没有新状态位**；
- 会话收尾后：旗标清零、穿透轮询档位复位、壳层收尾通知必达（穿透待办当场补做）；
- 右键进弹弓的判据是「**确有拖拽资格**（按下没被锁定位 / SHIFT 门挡下）**或已在瞄准**」：
  点击候选的右键回到 V-13 语义（合成 release + 正经右键菜单），而**已经建立**的
  瞄准会话不受判据约束（右键取消照旧有效）。

**红线 / 不变量**（本刀不许破坏）：

1. 合法按下（含还没过 `DRAG_THRESHOLD` 的点击候选）右键**照旧**能起瞄准；
2. 已建立的瞄准会话的四条退出路径（松左键发射 / Esc / 再点右键取消 / 看门狗）一条不少；
3. `_end_drag(host)` **只**收指定窗口的会话：别的宿主窗上的在途 grab 一个字段都不动；
4. 一次会话只松一次手（`on_release` 不重复）、一次空宿主只回收一次（不重复关窗）；
5. 「锁定位置 / 未按 SHIFT 时点击互动保留」的既有语义不动（本刀只关掉弹弓这一条旁路）。

## 二、修改文件说明

`git diff --numstat`（本地提交，未 push；不含本报告这份新文件）：

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/overlay_shell.py` | +17 / −4 | ① `_end_drag` 改为 `overlay._finish_grab(QPointF(grab.pos))`——位置仍是"按当前位置松手"的那一个，其余收尾（清 `_press_click_only`/`_drag_committed`、`set_drag_active(False)`、`_sync_follow_now`、壳层通知）全部交给窗口既有协议；进入前的 `grab is None` 早退与包住整段的 `try/except` 日志（屏事件路径不许被一次 release 异常打断）逐位保留。② `_release_host` 补一条"已不在册即返回"的幂等闸：拔屏处置与 grab 收尾的空宿主回收会先后各调一次，第二次若继续走 `self._hosts.index(host)` 会抛 `ValueError`（旧实现不通知壳层，所以这条组合路径以前不存在；证据见 §三）。 |
| `pet/overlay_window.py` | +28 / −9 | ① 右键分支判据由 `self._mouse_grab is not None` 换成 `self.slingshot.aiming or self._grab_drag_qualified()`（新增小判据方法：`_mouse_grab is not None and not _press_click_only`，与 `mouseMoveEvent`/`mouseReleaseEvent` 的点击候选判别同源）。② 模块 docstring 与 `mousePressEvent` 注释、`_check_stale_press` docstring 里"click-only 也能进瞄准"的旧描述改写为现行契约（进入判据收紧 / 看门狗那支是会话侧兜底）。 |
| `pet/sprite_slingshot.py` | +4 / −0 | `maybe_enter_on_right_press` docstring 补一句分工：进入资格由 overlay 事件侧判（`_grab_drag_qualified`），controller 只认"给了 grab + 开关允许"（避免后来者以为资格判据在 controller 里）。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_overlay_window_capabilities.py` | +78 / −0 | 新增 `_RecordingThroughController`（记录 `set_drag_active`）+ 两条：① `_end_drag` 走协议的完整断言（按当前位置松手且**只松一次**、两个旗标清零、`set_drag_active(False)` 恰一次、壳层收敛待办被补做、`mouse_through` 复位）；② 无会话时 `_end_drag` 零副作用（幂等入口）。 |
| `tests/test_overlay_hosts_multiscreen.py` | +102 / −0 | 新增 `_three_screens()` 与两条：① **没有兜底屏可迁**（`_fallback_screen` → None）的拔屏：会话仍走完协议、穿透待办被冲刷（这条路径没有随后的 `show()` 收敛）；② 跨屏拖拽进行中拔掉**输入会话所在**那块屏：会话只松一次手、空宿主只回收一次（少幂等闸即 `ValueError`）、C 窗上另一只在途 grab 全程不被打断。 |
| `tests/test_overlay_screen_migration.py` | +27 / −0 | `_migrate_to_screen` 换窗前收尾在途 grab 的回归（旗标与穿透档位一起复位）——直接钉 `_end_drag` 的第二个调用点。 |
| `tests/test_sprite_slingshot.py` | +107 / −19 | `_mouse` 助手补 `modifiers` 形参（SHIFT 用例需要）；老的 `test_stale_press_watchdog_clears_click_only_grab_and_cancels_aim` 钉的是旧契约（click-only 也能进瞄准），按新契约重写为五条：锁定位不进、SHIFT 未按不进、SHIFT 按住进、**没过阈值**的合法按下照旧进、已瞄准时判据不合格也仍能退出。 |
| `tests/test_proactive.py` | +55 / −2 | **本片独立补的一处测试侧收口**（与本片两条产品改动无关，另起一节讲）：`test_foreground_window_info_real_call_no_shadow_bug` 原先无条件断言"真调用必须返回 dict"，而它其实依赖「桌面上存在可见前台窗口」这件外部事实；改为先独立读一遍真实可见性前置条件，成立才断言。**断言一个字未放宽**，判别力有红/绿双向取证（§六之二）。 |

### 文档

| 文件 | 增删 | 改动 |
|---|---|---|
| `docs/PR-REPORT-CURSOR-PASSTHROUGH-2026-10-15.md` | +16 / −0 | 追加 §七「后续（2026-10-17）：§三 两处同族残留已收」，指向本报告；并登记仍开放项（`hideEvent`/`closeEvent` 不结束在途 grab）与一处已不可达的看门狗分支口径。 |
| `docs/INDEX.md` | 见本报告登记行 | 新文档入场登记（PR 报告存档表），并修订穿透修复那行的"遗留边界"尾注（`_end_drag` 清理不全部已收）。 |

### 未改动（看起来相关但故意没动）

- `pet/window.py`（legacy 单窗拓扑）：两条缺陷都只存在于 overlay 合成窗事件侧；
  legacy 的 `_enter_slingshot` 前置判据本来就要求"正在拖拽"（`_dragging`），无此缺口。
- `_finish_grab` 本体、`_reap_empty_hosts` 判据、看门狗两支的结构：本刀只换调用方，
  不改协议内部（看门狗那支新出现的不可达分支口径见 §七）。
- `hideEvent`/`closeEvent` 不结束在途 grab（既有行为，已登记 BACKLOG）：本片**探针查过**
  它会不会留下用户能感觉到的输入状态，结论是"不能确认"，故不改成产品分支——取证与结论
  见 §七 第 2 条与 §六之二。

## 三、实现要点

**1. 为什么是"统一走 `_finish_grab`"而不是"在 `_end_drag` 里补齐三件事"。**
`_finish_grab` 是窗口侧唯一的会话收尾口（release / 打断 / 看门狗共用），并且
`_notify_grab_finished` 的 docstring 已写明"**任何**清 grab 的出口都必须走到这里"。
在 `_end_drag` 里再补一遍字段与通知等于把这条契约抄成两份，下一个新增字段又会
漏（这正是本次缺陷的成因）。改动后 `pet/` 内清 `_mouse_grab` 的出口只剩三处：
`__init__`、`_finish_grab` 本体、以及 mousePressEvent 里那条**按设计不转发
`on_release`** 的"未命中"分支（它自己走通知，见该分支注释）——`grep "_mouse_grab = "`
可复核。

**2. 幂等闸是被实证逼出来的，不是预防性代码。** 走协议后 `_end_drag` 会触发壳层
收尾通知 → `_reap_empty_hosts`：跨屏拖拽把宠移走后，源窗是"空 sprite 表 + 还握着
grab"的形态，grab 一清它当场就被回收一次；随后 `handle_screen_removed` 的拔屏处置
又对同一宿主调一次 `_release_host`，而它第二行就是 `self._hosts.index(host)`。
实测把闸拿掉后新用例直接抛：

```
E   ValueError: <ScreenHost A bounds=0,0,1920x1040 sprites=0> is not in list
pet/overlay_shell.py:6555: ValueError
```

（`tests/test_overlay_hosts_multiscreen.py::test_screen_removed_finishes_only_that_windows_session`）
故闸保留为 `if host not in self._hosts: return`（三条主机实路径上它只会在这种
"已经回收过"的组合里命中，属幂等语义而非新策略）。

**3. 右键判据为什么读 `_press_click_only` 而不是 `_press_global` / `_drag_committed`。**

- `_press_click_only` 是本文件对"这次按下算不算拖拽候选"的**唯一**旗标
  （`mouseMoveEvent` 不转发移动、`mouseReleaseEvent` 走点击分支、`_finish_grab`
  与看门狗都读它），资格判据与它同源才不会出现两套"算不算拖拽"；
- `_drag_committed` 太严：它表达的是"位移过了 `DRAG_THRESHOLD`"，而"按下后原地
  直接点右键"是常见动作，用它会砍掉合法进入（已补用例钉住）；
- `_press_global` 在孤儿 grab（既无锚点也无 click-only 旗标，看门狗负责收的那种
  防御形态）上为 None，用它会把这一类按下误判成"没资格"——语义上它表达的是
  "记没记锚点"，不是"有没有资格"。

**4. 已瞄准的会话不受进入判据约束。** 判据只加在 `mousePressEvent` 的**进入**分支上；
`SlingshotController.maybe_enter_on_right_press` 里"已在瞄准 → 取消"的一支照旧先判
会话再判 config（该口径此前就有，本刀不动）。这样"会话活着而判据说不合格"时右键
仍能退出，不会掉进 V-13 分支（grab 被收、会话留着）。

## 四、性能分析

**方法（可复现）**：`cd <repo> && python /tmp/bench_input_grab_release.py`
（脚本全文见 §四之一；本机 Windows 11 / Python 3.13.7 / PySide6 offscreen 平台
插件 / 真 `OverlayShell` + 假配置目录；n=20000×5 轮取中位）。
环境：**非满载**（后台整套 pytest 已跑完再测；同机无其它重负载）。

| 指标 | 实测（中位） | 归属 |
|---|---|---|
| `_end_drag` 新路径（走 `_finish_grab`，含壳层收尾通知） | **6.067 µs/次** | 新路径，触发频率＝屏拔出/迁移（人手事件，≤几次/会话） |
| `_end_drag` 旧实现等价体（被替换的 5 行：`on_release` + 两个字段） | **2.777 µs/次** | 基线对照（净增 ≈ **3.29 µs/次**，一次性） |
| `_end_drag` 无会话（两边同为首行返回） | **0.777 µs/次** | 稳态（每次拔屏/迁移各一次；新旧逐位相同） |
| `_grab_drag_qualified()`（新增判据，无 grab） | **0.286 µs/次** | 新增路径，频率＝每次非左键 press |
| 旧判据表达式 `self._mouse_grab is not None` | **0.080 µs/次** | 基线对照（净增 ≈ **0.21 µs/次**） |
| `_grab_drag_qualified()`（有 grab 的常态） | **0.655 µs/次** | 同上（两个属性读都在） |

**结论（逐条）**：

1. **稳态开销**：正常拖拽/点击/右键路径的常数没有任何变化——右键分支多一次
   **0.21 µs** 的判据求值（只在"不处于瞄准会话"时才求值），拖拽/释放/看门狗路径
   逐字未动；`_end_drag` 无会话时的首行返回两版相同（0.777 µs，即拔屏/迁移在
   没有在途会话时一分钱不多花）。
2. **新增路径的绝对成本与触发频率**：`_end_drag` 的增量是 **3.29 µs/次**、且只在
   "屏事件撞上在途会话"时发生（人手事件，正常情况下每个会话 0 次；会话内上界＝
   宿主数与屏事件数）。同一个增量换掉的是旧实现留下的永久降频 + 永久穿透滞留。
3. **有无新的系统调用 / 网络 / 磁盘 / 线程**：本刀不新增线程、定时器、网络与磁盘
   访问。唯一可能多出的一次原生调用是 `set_drag_active(False)`（`platform_win` /
   `platform_passthrough` 的同一实现）：**仅当**轮询档位当时确实在"拖拽降频档"
   （100ms）时才 `setInterval` + 一次 `refresh()`（读+写窗口穿透样式），即
   "旧实现漏掉的那次复位"本身；档位本来就在 10ms 时是 no-op。拔屏处置里
   `_reap_empty_hosts` 可能关闭一个空窗（`close()`）——这是既有协议在**每次**正常
   松手时也会做的事，不是本刀新增的语义。
4. **内存与缓存**：零增长。没有新状态位、没有新容器；新增的是一个方法（类字典里
   一条条目，进程内一份）。

### 四之一、基准脚本（`/tmp/bench_input_grab_release.py` 全文）

```python
# -*- coding: utf-8 -*-
"""两条修复的性能探针（n 次取均值 + 中位数）。运行：
    cd <repo> && python /tmp/bench_input_grab_release.py
离屏 QApplication；被测对象是真 OverlayShell / OverlayWindow（假配置目录）。
"""
from __future__ import annotations

import os
import pathlib
import statistics
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())                  # 从仓库根运行：让 tests.* 可导入

from PySide6.QtCore import QPointF                                  # noqa: E402
from PySide6.QtWidgets import QApplication                          # noqa: E402

import tests.test_overlay_window_capabilities as cap                # noqa: E402
from pet.overlay_window import OverlayWindow                        # noqa: E402

app = QApplication.instance() or QApplication([])


class _NoopController:
    def set_drag_active(self, active):
        pass

    def resume(self):
        pass

    def stop(self):
        pass


def bench(label, fn, n=20000, rounds=5):
    for _ in range(200):            # 预热（首轮含分支/缓存预热）
        fn()
    per_round = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        per_round.append((time.perf_counter() - t0) / n)
    per_round.sort()
    print(f"{label:<38} 中位 {per_round[len(per_round) // 2] * 1e6:8.3f} µs/次  "
          f"min {per_round[0] * 1e6:8.3f}  max {per_round[-1] * 1e6:8.3f}  "
          f"(n={n}×{rounds}, 均值 {statistics.fmean(per_round) * 1e6:.3f})")


def old_end_drag_body(overlay):
    """origin/main 的 ``_end_drag`` 等价体：逐字抄回被替换的那 5 行。"""
    grab = getattr(overlay, "_mouse_grab", None)
    if grab is None:
        return
    grab.on_release(QPointF(grab.pos))
    overlay._mouse_grab = None
    overlay._press_global = None


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="dsh-bench-config-"))
    shell = cap._make_shell(tmp, {"mouse_through": False})
    overlay = shell.overlay
    sprite = shell.sprite
    sprite.on_release = lambda pos: None        # 只计协议开销，不计 sprite 内部
    overlay._input_controller = _NoopController()
    print("platform:", app.platformName())

    def armed():
        overlay._mouse_grab = sprite
        overlay._press_click_only = True
        overlay._drag_committed = False
        overlay._press_global = None

    def new_call():
        armed()
        shell._end_drag()

    def old_call():
        armed()
        old_end_drag_body(overlay)

    bench("_end_drag 新（走 _finish_grab 协议）", new_call)
    bench("_end_drag 旧（等价体 5 行）", old_call)
    bench("_end_drag 无会话（两边同首行返回）", lambda: shell._end_drag(), n=200000)

    win = OverlayWindow()
    bench("_grab_drag_qualified()（新增判据）",
          lambda: win._grab_drag_qualified(), n=200000)
    bench("旧判据表达式 `_mouse_grab is not None`",
          lambda: win._mouse_grab is not None, n=200000)

    shell.stop()
    shell._delete_runtime_marker()


main()
```

**实测输出（本机，非满载：先等整套全量跑完再测）**：

```
platform: offscreen
_end_drag 新（走 _finish_grab 协议）         中位    6.067 µs/次  min    5.971  max    6.549  (n=20000×5, 均值 6.168)
_end_drag 旧（等价体 5 行）                   中位    2.777 µs/次  min    2.754  max    2.817  (n=20000×5, 均值 2.782)
_end_drag 无会话（两边同首行返回）                 中位    0.777 µs/次  min    0.765  max    0.781  (n=200000×5, 均值 0.775)
_grab_drag_qualified()（新增判据）           中位    0.286 µs/次  min    0.286  max    0.292  (n=200000×5, 均值 0.288)
旧判据表达式 `_mouse_grab is not None`       中位    0.080 µs/次  min    0.079  max    0.081  (n=200000×5, 均值 0.080)
_grab_drag_qualified()（有 grab 的常态）     中位    0.655 µs/次  min    0.649  max    0.702  (n=20000×5, 均值 0.665)
```

（脚本里 `_end_drag` 的"旧实现等价体"是把 `origin/main` 被替换掉的那 5 行逐字抄成
函数的对照实现——同一进程、同一状态、同一轮内先测新后测旧。）

**不计入的部分（如实说明）**：脚本给 overlay 装的是 `_NoopController`，所以
"生产里 `set_drag_active(False)` 真控制器那次 `refresh()`"的开销不在上面数字里
（它是一次原生样式读写，且只发生在档位确实需要复位的场景，见结论 3）；
`_end_drag` 里 sprite 的 `on_release` 也被换成 no-op（sprite 内部代价与本刀无关，
两栏同口径可比）。

## 五、实机运行记录

本机 Windows 11（真 `windows` 平台插件）跑了两件事：真窗口的输入链路探针
（§5.1）与源码态启动冒烟（§5.2）。**配置目录一律隔离在临时目录**
（`APPDATA=<tmp>`，不读真实配置）：

### 5.1 真平台插件的输入链路探针

`cd <repo> && python /tmp/probe_input_grab_release.py`（脚本被调用的产品代码：
真 `OverlayWindow` + 真 `PetSprite` + 真 `ShellOverlayWindow`，`winId()` 真创建
原生窗口，事件走 `QApplication.sendEvent` 的真实分发；脚本如下，去掉模块
docstring 与行内注释）：

```python
import os
import pathlib
import sys
import tempfile

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="dsh-probe-appdata-")
sys.path.insert(0, os.getcwd())

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
print("platform plugin :", app.platformName())
print("screens         :", [(s.name(), s.geometry().getRect()) for s in app.screens()])

import tests.test_overlay_window_capabilities as cap
import tests.test_sprite_slingshot as sling
from pet.overlay_shell import OverlayShell


def mouse(etype, pos, button=Qt.MouseButton.LeftButton, buttons=None,
          modifiers=Qt.KeyboardModifier.NoModifier):
    point = QPointF(pos)
    return QMouseEvent(etype, point, point, button,
                       button if buttons is None else buttons, modifiers)


def right_press(pos):
    return mouse(QEvent.Type.MouseButtonPress, pos, Qt.MouseButton.RightButton,
                 Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)


def probe_right_press_criterion():
    overlay = sling.OverlayWindow()
    native = int(overlay.winId())
    print(f"[criterion] native window id = {native:#x}")
    sprite = sling._make_sprite(pos=(300, 300))
    overlay.add_sprite(sprite)
    hit = sling._hit_point(sprite)

    overlay.lock_position = True
    QApplication.sendEvent(overlay, mouse(QEvent.Type.MouseButtonPress, hit))
    print("[criterion] 锁定位按下: grab =", overlay._mouse_grab is sprite,
          "click_only =", overlay._press_click_only)
    QApplication.sendEvent(overlay, right_press(hit))
    print("[criterion] 锁定位 + 右键: aiming =", overlay.slingshot.aiming,
          "| grab =", overlay._mouse_grab,
          "| 右键菜单被吞 =", overlay._context_menu_blocked(),
          "| sprite 状态 =", sprite.interaction_state)
    QApplication.sendEvent(overlay, mouse(QEvent.Type.MouseButtonRelease, hit))

    overlay.lock_position = False
    QApplication.sendEvent(overlay, mouse(QEvent.Type.MouseButtonPress, hit))
    QApplication.sendEvent(overlay, right_press(hit))
    print("[criterion] 合法按下 + 右键: aiming =", overlay.slingshot.aiming,
          "| grab 仍在 =", overlay._mouse_grab is sprite,
          "| sprite 状态 =", sprite.interaction_state)
    overlay.slingshot.cancel(resume_drag=False)
    QApplication.sendEvent(overlay, mouse(QEvent.Type.MouseButtonRelease, hit))
    overlay.close()


def probe_end_drag_on_real_windows():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="dsh-probe-config-"))
    shell = cap._make_shell(tmp, {"mouse_through": False})
    try:
        overlay = shell.overlay
        native = int(overlay.winId())
        print(f"[end_drag] native window id = {native:#x}")
        released: list = []
        shell.sprite.on_release = released.append
        shell._on_cursor_visibility_changed("HIDDEN")
        before = (overlay.mouse_through, shell._auto_cursor_hidden)
        overlay._mouse_grab = shell.sprite
        overlay._press_click_only = True
        shell._converge_auto_cursor_hidden()
        print("[end_drag] 收尾前: mouse_through/auto_hidden =", before,
              "| 收敛待办 =", shell._converge_pending)

        shell._end_drag()

        print("[end_drag] 收尾后: release 次数 =", len(released),
              "| grab =", overlay._mouse_grab,
              "| click_only =", overlay._press_click_only,
              "| 收敛待办 =", shell._converge_pending,
              "| mouse_through =", overlay.mouse_through)
    finally:
        shell._delete_runtime_marker()
        overlay.close()


probe_right_press_criterion()
probe_end_drag_on_real_windows()
print("probe done")
```

实测输出：
platform plugin : windows
screens         : [('H27T22S', (0, 0, 2560, 1440))]
[criterion] native window id = 0x420d78
[criterion] 锁定位按下: grab = True click_only = True
[criterion] 锁定位 + 右键: aiming = False | grab = None | 右键菜单被吞 = False | sprite 状态 = normal
[criterion] 合法按下 + 右键: aiming = True | grab 仍在 = True | sprite 状态 = drag
[end_drag] native window id = 0x1511f0
[end_drag] 收尾前: mouse_through/auto_hidden = (True, True) | 收敛待办 = True
[end_drag] 收尾后: release 次数 = 1 | grab = None | click_only = False | 收敛待办 = False | mouse_through = False
probe done
```

读数对应两条缺陷的**用户可见结果**：

- **负向路径（本该不发生的事）**：锁定位的右键不进瞄准（`aiming = False`）、
  偷不走宠（`grab = None`、sprite 回到 `normal`）、右键菜单没被弹弓吞
  （`右键菜单被吞 = False`）；
- **正向路径（不该被误伤的事）**：合法按下的右键照旧进瞄准（`aiming = True`、
  grab 仍在、sprite 停在 drag 等价态）；
- **收尾协议**：`_end_drag` 收尾后 release **恰一次**、两个旗标清零、
  穿透待办被冲刷（`收敛待办 True → False`）、`mouse_through` 复位。

### 5.2 源码态启动（`python -m pet`，overlay 拓扑）

`PET_RENDER_TOPOLOGY=overlay APPDATA=<tmp> python -m pet`（`timeout 14` 收工），
应用自己的日志（写在隔离目录里）：

```
2026-10-17 03:37:19 acquired pid=26792 lock=<tmp>\dsh-pet-standalone\overlay-instance.lock
2026-10-17 03:37:20,009 INFO dsh-pet-standalone 启动 (slot: 0, instance: )
2026-10-17 03:37:20,065 INFO 当前形象: shenshen
2026-10-17 03:37:20,107 INFO 渲染拓扑: overlay(单合成窗)
2026-10-17 03:37:20,171 INFO 素材加载完成：shenshen 106 段动画
2026-10-17 03:37:21,195 INFO 进入事件循环
2026-10-17 03:37:21,213 INFO ffmpeg 孤儿防护已就绪：Job Object（KILL_ON_JOB_CLOSE）…
2026-10-17 03:37:22,005 INFO tick 档位 T0→T1 触发因=animating interval=6ms（满速）
2026-10-17 03:37:32,117 INFO webm 圈边界宽限期满未续圈，reader 退出: …\videos\idle\待机呼吸休闲.webm
```

- **用户可见行为**：真桌面上出现桌宠窗口并在动画（日志里 tick 空转档位升到满速、
  webm 帧真在推进、读帧 reader 在宽限期后退出）。收工时由 `timeout` 结束进程
  （**非优雅退出**，exit 124）——优雅退出路径与本刀无关，未再单独验。
- **配置隔离自证**：本次运行的全部产物都落在 `<tmp>/dsh-pet-standalone/`
  （`config-slot-0.json` / `pet-runtime-v2-26792-slot-0.json` / `overlay-instance.lock`
  / 上面两份日志），而真实 `%APPDATA%\dsh-pet-standalone` 里最新的文件仍是
  **10-16 14:07**（本次运行 10-17 03:37）——没有读也没有写真实配置。

### 5.3 做实机验证的边界（为什么不写更多）

- **真·拔显示器**：本机 Qt 口径只有一块活动屏（探针 §5.1 第一行打印的
  `screens` 即证据），物理拔屏无法自动化，也不可能在无人值守下做——拔屏链路的
  验证由"真壳 + 假屏信号"的多屏夹具承担（`handle_screen_removed` 是产品真入口）。
- **真鼠标右键序列**：本会话不含桌面操控（CU）授权，也没有用 `SendInput` 合成
  真实输入（会把用户的真实光标拖走）。故"真手点"这一层依赖用户侧确认；本刀给出
  的替代证据是 §5.1 的真平台事件分发 + offscreen 全套用例。
- **长期观察项**：`_end_drag` 修复的效果是"不再滞留"，只有"下次真的拔屏/换屏时
  在拖拽中"才会被感知，无法在一次会话内造出（需要物理拔屏）。如实登记。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet tests scripts` | **All checks passed** |
| 先红后绿（聚焦，产品改动前） | `pytest -q tests/test_sprite_slingshot.py -k "right_press or aiming_exit"` | 改动前 **2 failed, 7 passed, 20 deselected**（两条"不该进瞄准"的红：锁定位 / SHIFT 未按），改动后全绿 |
| 先红后绿（聚焦，产品改动前） | `pytest -q tests/test_overlay_window_capabilities.py -k end_drag` | 改动前 **1 failed, 1 passed, 19 deselected**（`_press_click_only` 未清） |
| 先红后绿（聚焦，产品改动前） | `pytest -q tests/test_overlay_hosts_multiscreen.py -k "without_any_fallback or finishes_only_that_windows"` | 改动前 **2 failed, 20 deselected**（会话未收 + `_drag_committed` 未清） |
| 先红后绿（聚焦，产品改动前） | `pytest -q tests/test_overlay_screen_migration.py -k inflight` | 改动前 **1 failed, 7 deselected** |
| 幂等闸有效性（临时撤掉再跑） | 同上多屏用例 | 撤掉闸即 `ValueError: <ScreenHost A …> is not in list`（见 §三） |
| 相关族 | `pytest -q tests/test_overlay_window.py tests/test_overlay_window_capabilities.py tests/test_overlay_hardening.py tests/test_overlay_dead_switches.py tests/test_sprite_slingshot.py tests/test_overlay_screen_migration.py tests/test_overlay_shell.py tests/test_overlay_hosts_multiscreen.py tests/test_overlay_cross_screen_switch.py tests/test_overlay_independent_screens.py tests/test_multi_screen_interaction.py tests/test_overlay_seam_passage.py` | **209 passed**（14.21s） |
| 全量（首次，03:35 起） | `python -m pytest -q` | **7954 passed, 15 skipped, 0 failed** in 1440.95s (0:24:00) |
| 全量（复跑，冻结内容 04:09 起） | `python -m pytest -q` | **7955 passed, 15 skipped, 1 failed** in 1430.88s (0:23:50)——唯一那条红是环境依赖的既有用例，见下（两次相差 2 例＝复跑时本报告已在盘上，`test_pr_report_discipline` 的两条参数化多出来） |
| 架构红线 | `tests/test_architecture.py`（在全量内，本刀未新增/恢复任何被退役模块） | 随全量绿 |
| 交付证据纪律 | `pytest -q tests/test_pr_report_discipline.py` | **171 passed**（本报告已登记入 INDEX，四节标题齐备） |
| 换目录复跑 | `cd /tmp && pytest -q <绝对路径的 3 个聚焦文件>` | **58 passed**（无路径硬编码依赖） |
| 静态检查（合 `origin/main` `53d0587` **后**复跑，含本片新增的测试改动） | `python -m ruff check pet tests scripts` | **All checks passed** |
| 本片聚焦（合 main 后复跑） | `pytest -q tests/test_sprite_slingshot.py tests/test_overlay_window_capabilities.py tests/test_overlay_hosts_multiscreen.py tests/test_overlay_screen_migration.py` | **80 passed**（5.56s） |
| 相关族（合 main 后复跑，12 个文件＝上表那条同一份命令） | 见上 | **209 passed**（11.97s） |
| 前台窗口用例 + 文档纪律（合 main 后） | `pytest -q tests/test_proactive.py tests/test_pr_report_discipline.py -rs` | **241 passed / 1 skipped**（跳过的那条＝§六之二 的前置条件闸；本报告改过，纪律门必须重跑） |
| 全量四分片（合 main 后，`53d0587`→合并后树） | `python scripts/ci_shards.py` | **7898 passed / 16 skipped / 0 failed**，`EXIT=0`（分片明细 1769+2084+1991+2054 passed、6+4+4+2 skipped；`ci_shards.py` 按 CI 口径忽略 4 个 webm 生命周期文件，CI 里另跑——所以这个数比早期整跑全量的 7954/7955 少那几十条）。日志：`.scratch/full-suite-shards-merged.log` |

**合 main 的事**：`origin/main` 在本片冻结内容期间前进了一次（`056dc2a` → `53d0587`，后者是
#292 frameseq 档位），按任务口径只合 main：`git merge origin/main` 只有 `docs/INDEX.md`
一处冲突（两行索引争同一插入点），按仓库惯例取**并集**（两行都留），其余文件自动合入。
上表的聚焦/相关族/纪律门都是**合并后**在合并后的树上复跑的。

**那条与本刀无关的红已经收了（测试侧，本片一并带上）**：复跑时
`tests/test_proactive.py::TestVisionAndWatcherPhase2::test_foreground_window_info_real_call_no_shadow_bug`
失败（`vision.foreground_window_info()` 返回 None）。判定为**环境依赖的既有用例**，
证据三条（上一版文字在提交 `4b91eb6` 里可查，结论不变）：

1. **未改动的基线同样红**：在 `origin/main` 的干净检出上单独跑同一条用例，同样
   `1 failed`（当时建了临时 detached worktree 取证，取完删除）；
2. **现场根因可指名**：探针显示 `GetForegroundWindow()` 返回 `WeChatAppEx.exe`
   （微信小程序宿主，class `Chrome_WidgetWin_0`）的一个**不可见**窗口
   （`IsWindowVisible=False`、无标题、未 cloaked、rect 930,376–1630,1016），而
   `foreground_window_info()` 按自身契约对不可见窗口返回 None——用例断言的其实是
   "当前桌面存在一个可见的前台窗口"；
3. **同一份代码此前是绿的**：首次全量（03:35）该用例通过，说明它是随桌面状态翻转的
   真调用用例，不是本刀引入（本刀未触碰 `pet/vision.py` / `pet/proactive*`）。

本片把它改成**按真实可见性前置条件断言**（`tests/test_proactive.py` `+55 / −2`，
详见 §六之二），此后本机跑它是 `1 skipped` 而不是红。

#### §六之二、前台窗口用例的前置条件闸（本片测试侧收口，与本片两条产品改动无关）

改法（一句话）：**先独立读一遍 Win32 判据**（`GetForegroundWindow()` 非零 /
`IsWindowVisible` / 非 `IsIconic` / 未被 `DwmGetWindowAttribute(…,14,…)` cloak /
`GetWindowRect` 尺寸为正），**不经过产品函数**；成立才执行原来的两条断言，不成立则
`pytest.skip` 并写明原因。产品契约一个字没动，断言一个字没放宽，也没有 `-k` 掉它。

**判别力取证（红/绿双向，脚本 `.scratch/verify_precondition_gate.py`，未入库）**：本机桌面
此刻恰好**没有**可见前台窗口（判据 `False`），所以取证把"可见"这一条用桩置真，让前置条件
成立，然后在同一前置条件下跑两条：

| 被试 | 结果 | 说明 |
|---|---|---|
| 真产品（`pet/vision.py` 原样） | **用例通过** | 置桩后产品返回 `{'hwnd': 27987436, 'pid': 11008, 'process': 'WeChatAppEx.exe', 'title': '', 'rect': (937, 376, 686, 633)}`——证明闸不是"恒跳过"，断言在成立时确实被执行 |
| 把历史 shadow bug **原样放回**的变体（函数体内 `import ctypes.wintypes` 造成局部名 → `UnboundLocalError` 被吞 → 恒返回 None） | **用例红**（`AssertionError`） | 证明同一前置条件下 bug 仍然被抓住——这正是"不放松产品契约"的可执行证据 |

**为什么不去"造"一个可见前台窗口当锚点**：实测过（同脚本更早一版）：自建 `QWidget`
`show()+activateWindow()+raise_()` 在 `windows` 插件下确实是真可见 HWND
（`IsWindowVisible=True`），但**抢不到前台**（有界等待 5 s，`GetForegroundWindow()`
始终不是它，Windows 的前台锁规则），在 `offscreen` 插件下 `winId()` 干脆是 `1`。
故"确定性前置条件"在本机不可得，只有"按真实状态判定 + 不成立则跳过"这一条路。

**断言有效性**：两条缺陷都做了"产品改动前必须红"的取证（见上表逐条数字），且每一条
新用例都能指出它钉的是哪一行产品代码；`_release_host` 幂等闸用"撤掉即抛"直接证明
断言能区分新旧实现。本刀**未**跑"受影响时序族满载 3 遍"：它要求本地 CPU 打满跑 3
轮（AGENTS 的 CI 成本纪律），而本轮的任务边界明确排除了 CPU 满载（全量已连跑两遍、
相关族 209 例绿、聚焦用例换目录复跑绿）。

## 七、已知限制与后续

1. **`_migrate_to_screen` 里"主宿主已被回收"的分支不可达、也未加护栏**：走协议后
   `_end_drag` 的收尾通知会顺手回收空宿主（`_reap_empty_hosts`），`_migrate_to_screen`
   若在"宿主已被收走"的状态下继续重建窗口，新窗会不在宿主表里（宠上不了屏）。触发
   需要同时满足：运行期 slot0 恢复且记忆屏 ≠ 主宿主屏 **且** 主宿主空着 **且** 主宿主
   还握着 grab **且** 宿主数 ≥2——鼠标被 Qt 隐式 grab 独占时点不到托盘菜单，运行期
   slot0 恢复只能由鼠标手势触发，故这条组合在生产上不可达；**没有为不可达状态加
   无测试覆盖的分支**（AGENTS §15 口径：宁可如实登记，不留死开关）。若将来出现
   键盘/外部指令触发的 slot0 恢复，这里需要补一条"宿主已不在册则在新屏现建宿主"。
2. **看门狗 click-only 分支里"先收瞄准会话"那一句已不可达**：新判据下
   click-only 的按下再也起不了瞄准会话，故"`_press_global` 为空 + 持有 grab + 正在
   瞄准"这一形态不再出现（该分支保留为会话侧兜底，删除属另一刀的范围，口径已写进
   `_check_stale_press` docstring 与穿透修复报告 §七）。同族仍开放的一项见第 6 条。
3. **拔屏时若正开在瞄准会话上**：会话不被 `_end_drag` 取消（与改动前一致），但它在
   新的承载窗上仍有退出路径（松左键 → `_fire_slingshot` / Esc / 看门狗），不会卡死；
   未做端到端实机复现（需要物理拔屏）。
4. **真双屏 / 异 DPI 未验**（本机只有一块活动屏）：多屏链路的验证止于真壳 + 假屏
   信号，与 `PR-REPORT-PER-PET-MULTISCREEN-2026-10-16.md` 登记的同一局限。
5. **本机那条环境依赖用例已收（测试侧，见 §六之二）**：`test_proactive.py` 的
   `test_foreground_window_info_real_call_no_shadow_bug` 原先无条件断言"当前存在可见前台
   窗口"，隐形宿主窗当前台时必红；现在按真实可见性前置条件断言，本机跑成 `1 skipped`，
   断言未放宽（红/绿双向取证在 §六之二）。
6. **`hideEvent`/`closeEvent` 不结束在途 grab：探针查过，不确认"会留用户能感觉到的输入
   状态"，故不改产品代码**（既有行为，仍留在 BACKLOG）。取证用隔离的真实 Qt 探针
   （`.scratch/probe_hide_close_grab.py`：真 `OverlayWindow` + 真 `PetSprite`，不 sleep
   赌时序），事件注入走 **`QWindow` 重载**的 `QTest`——widget 重载是**直接投递给指定
   widget**、不模拟真实路由（对照取证 `.scratch/probe_qtest_routing.py`：把 release 发给
   B 的 widget，B 收到了；改发给 B 的 `windowHandle()`，按隐式 grab 路由落到了按下窗 A）。
   逐条实测（`场景 → 观测`）：

   | 场景 | 实测 | 读法 |
   |---|---|---|
   | A 拖拽中 `hide()` | hide 本身**不动**任何 grab 字段：`grab=True`/`_press_global` 在/`committed=True`/轮询停表（`timer_active=False`） | hide 不是收尾口（代码层也没有任何 hide 分支碰 grab） |
   | E hide 之后**窗口系统仍送来 release** | 按钮态归零（`qt_buttons=0`）但隐藏窗**收不到**这次 release（grab 仍在、sprite 仍 `drag`）——Qt 的派发在隐藏控件上到此为止 | "事件到了本进程却到不了窗口"是真实可能的一支 |
   | E 续：`show()` 后**下一拍 tick 看门狗** | `grab=None`、`_press_global=None`、旗标清零、sprite 回 `normal`、轮询档位回 10ms——**当场收干净** | 这一支没有残留：应用一旦知道按钮已抬起，既有看门狗就收掉它 |
   | B hide 后**release 根本没到本进程** | `show()` 回来状态**依然陈旧**：`grab=True`、sprite 停在 `drag` 姿态、轮询停在 100ms 降频档；按钮态一直报按下，**轮询与 tick 两条看门狗都不动它** | 唯一会"看见残留"的一支（但本机造不出它，见下） |
   | C 锁定位 click-only 按住中 hide | 同 B（`click_only=True`、`grab=True` 一路留着） | 同上 |
   | F 陈旧态下用户再点一下宠 | 真 press + 真 release 后**全部收干净**（`grab=None`、sprite 回 `normal`）；重按那一下会把 `_drag_committed` 复位 | 恢复路径＝用户下一次点击 |
   | D 拖拽中 `close()` | close 本身也不清（`controller=None`、`grab=True`、sprite 仍 `drag`）；release 到了也到不了已关闭的窗 | 关窗这条路代码层另有闸，见下 |

   **顺带查实的两条代码层事实**（不是推测，`grep` 可复核）：
   - 拖拽期的看门狗**只能靠 tick 路径**：两个控制器都在 `_press_global` 非空时短路、
     不做命中判定（`pet/platform_win.py:156`；非 Windows 的 `pet/platform_passthrough.py:134`
     同口径），于是走不到 `_is_transparent_at` → `_check_stale_press`；真正每拍兜底的是
     `pet/tick_driver.py:592` 那一句（`_check_stale_press` 的 docstring 写的是"穿透轮询与
     tick 路径兜底"，对 click-only 分支成立、对拖拽分支只有后一半）；
   - "关窗时还握着 grab"不可达：`_reap_empty_hosts` 明确跳过持有 grab 的空宿主（注释写着
     "按着不放的宿主不拆"），屏事件的两条关窗路径（`handle_screen_removed` /
     `_migrate_to_screen`）都在前面走 `_end_drag`。

   **不能确认的那一半（为什么不臆造产品分支）**：真机 Windows 在窗口隐藏时会释放 capture，
   松手事件**落进别的进程**这一支，在离屏隔离测试里**造不出来**（探针只能"注入"，注入即
   假设事件到达）；平台插件是否在下一次真实移动里把按键态校正为 0，属 `QWindowsMouseHandler`
   对 `WM_MOUSEMOVE` 的 `wParam` 处理，同样不在本机可测范围。也就是说：B/C 那一支会不会在
   真机上出现、以及若出现是否在用户下一次点击前就被抹平，只有**实机**（真鼠标 + 真 hide
   触发路径，例如「按住宠时全屏避让触发」）才能定。**照任务口径：不确认就不加产品分支。**

   **下一轮若要收（先实机确认再动）**：最省的形状是在 `hideEvent`/`closeEvent` 里按既有
   `_finish_grab` 协议收尾（`if self._mouse_grab is not None` 一句，位置取按当前光标松手），
   不新增防御框架；要留意重入——`_finish_grab` → `_notify_grab_finished` → 壳层收敛/空宿主
   回收会再触发一次可见性动作，落在 hide/close 回调里就是重入，`closeEvent` 里还得排在
   `_input_controller = None` 之前（协议里有 `set_drag_active(False)`）。

## 八、风险与回滚

- **影响面**：`pet/overlay_window.py` 的右键分支（每次非左键 press 多一次判据求值）、
  `pet/overlay_shell.py` 的屏事件收尾链（拔屏 / 换屏 / 运行期 slot0 恢复）。
  拖拽、点击、发射、看门狗、穿透收敛的既有路径逐字未动。
- **开关 / 配置迁移**：无新增设置键、无新增环境变量、无落盘格式变化（不需要迁移；
  回滚后也没有残留状态——本刀不写任何持久化字段）。
- **测试侧改动（`tests/test_proactive.py`，与本片两条产品改动无关）**：只加了一次
  Win32 前置条件读取与一条跳过分支，不进入任何产品路径，也不改变被断言契约；回滚
  ＝revert 该提交，行为回到"桌面前台是隐形窗时红"。它带来的唯一新成本是测试进程里一次
  同步 Win32 读取（首次调用即测，量级 µs～ms 级，且只在 Windows 上跑）。
- **回滚步骤**：`git revert` 本提交即可。回滚后旧行为（`_end_drag` 半清、
  click-only 可进弹弓）恢复，不产生残留数据；唯一需要留意的是"回滚后
  `handle_screen_removed` 不再可能二次回收宿主"，幂等闸留着也无害（它只在
  `host not in self._hosts` 时早退，正常路径不命中）。
- **风险等级**：中（输入链路 + 屏事件链，但改动是"换调用口"与"收紧一个入口判据"，
  且两条都有先红后绿的聚焦回归 + 全量套件背书）。
