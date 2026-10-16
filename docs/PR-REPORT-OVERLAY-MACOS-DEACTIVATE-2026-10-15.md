# PR 报告：overlay 合成窗在 macOS 应用失活时被 Cocoa 隐藏

> **基线**：`579b401`（2026-10-15，`main`）
> **分支**：`fix/overlay-macos-deactivate-visibility`　**日期**：2026-10-15
> **范围**：2 个文件（实现 1、测试 1）
> **关联**：[`PR-REPORT-BUBBLE-ON-TOP-2026-10-13.md`](PR-REPORT-BUBBLE-ON-TOP-2026-10-13.md)（其中已登记「`WA_MacAlwaysShowToolWindow` 路径未验；overlay 拓扑行为不变故未验」）、issue #229 同族的 `platform_mac` 平台层、issue [#262](https://github.com/MerZlin/dsh-pet-indesktop/issues/262)（同根因的独立记录，§九 据它加强）、issue [#275](https://github.com/MerZlin/dsh-pet-indesktop/issues/275)（legacy 路径的鼠标缺陷，与本 PR 无关）

## 一、核心特性

**问题**：macOS 上（默认 overlay 拓扑）切到任何其他应用，整只桌宠从桌面消失；点 Dock 图标把应用激活回来，它又出现。用户观感是「桌宠没退出但形象不见了」。

**根因**：`OverlayWindow` 带 `Qt.Tool` 标志，而 Cocoa 会在应用失活（resigns active）时自动把 Tool 窗口 order out。项目**早就知道**这件事，也**早就有修复**——`pet/platform_mac.py::_keep_macos_tool_window_visible()`（设 `WA_MacAlwaysShowToolWindow`），并从 2026-08-18 起在 legacy 的 `PetWindow` 里无条件调用（`pet/window.py:567`、`:1135`）。

**漏点**：overlay 单合成窗新架构 2026-09-23 才落成（`6032c30`），**没有把这条平台补丁移植过来**。全历史核查：

```
$ git log -S "_keep_macos_tool_window_visible" -- pet/overlay_window.py
(空 —— 从未出现)
$ git log -S "WA_MacAlwaysShowToolWindow" -- pet/overlay_window.py
(空 —— 从未出现)
```

又因为**默认拓扑就是 overlay**（`is_overlay_topology()` == `not stream_capture_mode`），绝大多数 macOS 用户走的正是唯一没打补丁的那条路；legacy 用户完全看不到，CI 三平台又都固定 `offscreen`，所以它能活到现在，只在真机暴露。

**用户可见变化**：修后 overlay 桌宠在切到别的应用时**保持可见**（与 legacy 行为一致）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | overlay 桌宠跨应用切换保持可见 | 构造 `OverlayWindow` 时补下发 `WA_MacAlwaysShowToolWindow` |
| 2 | 不改变 z-order / 置顶语义 | 只设 native 属性，不动 flags，不重建原生窗口 |

**红线 / 不变量**：① `OverlayWindow` 的窗口标志（`FramelessWindowHint \| Tool \| WindowStaysOnTopHint \| NoDropShadowWindowHint`）不得被本改动改变；② 非 darwin 平台上不得新增任何行为；③ 不得引入运行时 objc 调用（保持 `platform_mac` 既有的「构造期设属性、不做 native 调用」口径）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/overlay_window.py` | **+8 / −1** | ① import 行补 `_keep_macos_tool_window_visible`（该文件本来就已从同一模块 import `_mac_no_window_shadow_flag`，故只加一个名字）；② `OverlayWindow.__init__` 在 `setAttribute(WA_NoSystemBackground)` 之后调用 `_keep_macos_tool_window_visible(self)`。**为什么放构造处**：`platform_mac._mac_no_window_shadow_flag` 的既有注释已确立「标志只能在 flags 构造处给」的口径；属性同理只在构造期设一次，避免可见窗口上 `setWindowFlag` 触发原生窗口重建（频闪）。**为什么不动 flags**：`WA_MacAlwaysShowToolWindow` 只是 native 属性，不参与 flags 计算，所以不重建窗口。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_overlay_window.py` | **+42 / −0** | ① `test_overlay_tool_window_stays_visible_when_application_deactivates`：darwin 下真实构造 `OverlayWindow()`，断言 `testAttribute(WA_MacAlwaysShowToolWindow) is True`。**用真实窗口断言、不用源码文本**——漏调用时该属性为 False，断言精确红在缺属性那一行（见 §六 红绿证据）。② `test_overlay_window_keeps_qt_tool_flag`：前提守卫——本修复只在窗口仍是 `Qt.Tool` 时才有意义；将来若有人把 overlay 改成普通 `Window`，这条会逼那次改动显式面对它，而不是悄悄绕过。 |

### 未改动（明确说明）

- `pet/window.py`（legacy）：**没动**。**在这条可见性修复上**它一直是对的（一直调用 `_keep_macos_tool_window_visible`），本改动是让 overlay 与它对齐。⚠️ 但不要把这句话读成"legacy 一切都对"——第二轮真机排查发现 **legacy 的鼠标交互在 macOS 上另有独立缺陷**（拖动不生效、点击被误判成拖动导致无气泡、右键菜单需换窗口标志），详见 §九 与另立的 issue。
- `pet/platform_mac.py`：**第一轮没动**（helper 本身正确，问题在调用点缺失）；**第二轮新增** `_mac_set_hides_on_deactivate`（见 §九）。
- `pet/overlay_shell.py`：**没动**。在 `OverlayWindow` 构造处修即可覆盖 shell 的全部创建路径（shell 只 `OverlayWindow(...)` 构造，不自行拼窗口），无需第二处调用。
- `pet/platform_passthrough.py` / `build_window_flags`：**没动**。与穿透、阴影无关。

## 三、实现要点

```python
from .platform_mac import _keep_macos_tool_window_visible, _mac_no_window_shadow_flag
...
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.WindowStaysOnTopHint
                            | _mac_no_window_shadow_flag())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        _keep_macos_tool_window_visible(self)          # ← 新增
```

`_keep_macos_tool_window_visible` 只在 `sys.platform == 'darwin'` 时下发，非 darwin 是空操作；它**不触碰 flags、不调 objc runtime**，所以不触发原生窗口重建，也不受 `WA_MacAlwaysShowToolWindow` 在运行时切换不可靠这一已知限制影响（既有的 `_mac_set_window_level` 才是走 objc 的那条路，本改动不涉及）。

**取舍与备选**：
1. *在 `OverlayShell` 里对 overlay 窗口补设属性* —— 否。窗口的所有权在 `OverlayWindow` 自己（flags/属性都在它的构造处给），放 shell 会造成「构造处与 shell 两处真相」。
2. *把 overlay 改成普通 `Window`* —— 否。那会让桌宠进入窗口列表/Mission Control，且与 legacy 捕获模式的取舍混为一谈。
3. *在 `platform_mac` 里加一个「对所有 Tool 窗口生效」的全局钩子* —— 否。超出本缺陷范围，且会把气泡/灵动岛等已有各自处理的窗口一并卷进来（它们已各自设过该属性：`speech_bubble.py:337/848`、`dynamic_island.py:540`、`desktop_notify.py:39`、`screen_capture/result_panel.py:317`）。

## 四、性能分析

**方法（可复现）**：`QT_QPA_PLATFORM=offscreen .venv/bin/python /tmp/bench_overlay_ctor.py`
**环境**：macOS 27.2 (26B5112a) · Apple Silicon · CPython 3.13.15 · PySide6 6.12.0 · offscreen 平台

| 指标 | 实测 | 归属 |
|---|---|---|
| `OverlayWindow()` 构造耗时（**含**修复，N=300 ×5 轮） | 0.055 / 0.047 / 0.045 / 0.047 / 0.048 ms，**中位数 0.047 ms** | 既有热路径（仅在窗口创建时） |
| `OverlayWindow()` 构造耗时（**撤掉**修复，同口径） | 0.056 / 0.049 / 0.043 / 0.048 / 0.049 ms，**中位数 0.049 ms** | 基线 |
| `_keep_macos_tool_window_visible` 单次绝对成本 | **0.414 µs** | 新增 |

**结论（逐条）**：

1. **稳态开销**：**无变化**。本属性只在 `OverlayWindow.__init__` 下发一次，不进入任何 tick/绘制/事件路径；构造耗时中位数 0.047 vs 0.049 ms，**差值的符号都不稳定、落在轮间区间 0.043–0.056 ms 内，属噪声**，故不声称「更快/更慢」。
2. **新增路径的绝对成本与触发频率**：单次 **0.414 µs**（一次性 `setAttribute`）；**触发频率 = 每个 `OverlayWindow` 实例一次**（= 进程启动、或跨拓扑重入时各一次），**不是每帧、不是每 tick**。按 0.414 µs 计，相对 8 ms 帧预算占比 **0.005%**，且不落在帧路径上。
3. **新系统调用 / 网络 / 磁盘 / 线程**：**都没有**。`setAttribute` 是 Qt 进程内属性位；非 darwin 平台该函数为纯空操作。特别地**未引入 objc runtime 调用**（`platform_mac._mac_set_window_level` 那条 ctypes/objc 路径本改动不涉及），因此不存在「offscreen 平台 winId() 非 NSView 导致 SIGSEGV」那类既有风险。
4. **内存与缓存**：**无增长**。不新增容器、不新增缓存、不改 `_dirty` / sprite 结构。

## 五、实机运行记录

**环境**：macOS 27.2（26B5112a）· Apple Silicon · 用户机真机（非 CI、非 mock）· 被测对象为已打包的 `dsh-pet-standalone-webm-chat.app`（PyInstaller onedir，运行 PySide6 6.12 / Qt 6.12 冻结构建）

### 5.1 根因现场复现（overlay 拓扑 —— 缺补丁）

探针：`CGWindowListCopyWindowInfo` 分别取 `OnScreenOnly`(1) 与 `All`(0)，统计 owner 为 `dsh-pet-standalone-webm-chat` 的窗口数。

```
### 前台 ASN:0x0-0x45045（桌宠）
[A. 桌宠为前台] 在屏=2  总计=7
    ON  layer=8  alpha=1.0  1728x1117@0,0     ← 全屏透明合成窗
    ON  layer=8  alpha=1.0  270x61@1186,768
>>> 切到 Finder <<<
### 前台 ASN:0x0-0x13013（Finder）
[B. Finder 为前台] 在屏=0  总计=7            ← 全部被 order out
>>> 切回桌宠 <<<
[C. 切回桌宠后] 在屏=1  总计=7
```

注意 `alpha` 全程 **1.0** —— 窗口不是变透明，是**被移出屏幕**；进程未退出，故 Dock 图标仍在，点它激活应用即 order 回来。**与用户报告的症状逐条吻合**。

### 5.2 机制确认（legacy 拓扑 —— 带补丁），同一台机器、同一套操作

`PET_RENDER_TOPOLOGY=legacy` 启动（该路径调用了 `_keep_macos_tool_window_visible`）。拓扑确认走日志：legacy 独有的一行出现 —— `共享全屏监视线程已启动`（overlay 拓扑刻意不启该共享 watcher）。

```
[A. legacy · 桌宠前台]       在屏=1    ON layer=3 461x281@782,550
[B. legacy · Finder 前台]    在屏=1    ON layer=3 461x281@782,550   ★跨应用仍在屏★
[C. legacy · Sublime 前台]   在屏=1    ON layer=3 461x281@782,550   ★第三个应用仍在屏★
```

**这是本 PR 最关键的证据**：同一台 macOS 27.2 + Qt 6.12 上，**带该属性的路径跨应用切换保持可见，不带该属性的路径全部被 order out**。因此「补这一条属性即可修复」不是推断，而是同机 A/B 的直接结论。

### 5.3 用户可见行为确认

修复前（overlay）：用户报「一切换到别的应用桌宠形象就不见，点 Dock 栏选回去才显示」。本地探针在 5.1 完整复现该现象。修复后（legacy 实测）：切到 Finder / Sublime Text 后桌宠仍在屏。**修复后的 overlay 构建本体未在真机运行**（见 §七 限制 1），但 5.2 已证明差量正是该属性。

### 5.4 边界与「本该失败」路径

- **非 darwin**：`_keep_macos_tool_window_visible` 为空操作，属性不下发；由 `test_overlay_window_keeps_qt_tool_flag` 守卫「窗口仍是 Qt.Tool」这一前提，避免将来改成普通 Window 后本修复变成无声的摆设。
- **全屏应用自动隐藏**：用户配置里 `auto_hide_fullscreen=true` 是**另一条**独立机制。诊断时把它临时置 false 复测，**现象不变**（Finder 前台仍在屏 0），据此排除它；随后已还原为 `true`。
- **Stage Manager**：`defaults read com.apple.WindowManager` → `GloballyEnabled = 0`，排除。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `.venv/bin/python -m ruff check pet tests scripts` | **All checks passed!** |
| 聚焦（本文件全量） | `QT_QPA_PLATFORM=offscreen pytest -q tests/test_overlay_window.py` | **19 passed, 1 skipped** |
| 新增两条用例 | `pytest -q tests/test_overlay_window.py -k "deactivates or qt_tool_flag"` | **2 passed, 18 deselected** |
| 断言有效性（红→绿） | `git stash push pet/overlay_window.py` 后重跑上面的 `-k deactivates` | **1 failed** —— `AssertionError: assert False is True`（`testAttribute(WA_MacAlwaysShowToolWindow)` 为 False），精确红在缺属性那一行 |
| 既有 legacy 用例未被影响 | `pytest -q tests/test_desktop_pet_features.py -k macos_tool_window` | **1 passed** |
| 全量 | `python -m pytest -q` | **第一轮未跑**（见下）；**第二轮已补跑 → 1 failed / 7456 passed / 69 skipped**，唯一失败经基线对照证实与本 PR 无关（§九） |

**关于「未跑全量」的诚实登记**：本机只建了最小复现环境（`.venv` 内仅 `PySide6==6.12.0` + `pytest` + `ruff`），用于跑上面的聚焦门；`requirements.txt` 里的 `numpy / rapidocr / onnxruntime / opencv` 等未安装，全量套件在本机跑不起来。本改动是构造期一行属性下发、不触及数据模型/配置迁移/生命周期/线程/平台分派以外的分支，按 `AGENTS.md`「聚焦加相关测试」口径提交，**全量门交由 CI 执行**。

> **后续（第二轮）已补全**：装上 `requirements.txt` 全量依赖后跑完整套件，结果为 1 failed / 7456 passed / 69 skipped；唯一失败在 pristine `main` 上同样复现，属基线既有。详见 §九「第二轮的完整套件结果」。

## 七、已知限制与后续

1. **修复后的 overlay 冻结构建未在真机运行** —— 无法直接验证「打了补丁的 overlay 窗口在真机失活时保持可见」。不能自动验证的原因：用户手上是 PyInstaller 冻结的 `.app`（`Contents/Resources/base_library.zip` + 内嵌 PYZ），改字节码会破坏 ad-hoc 代码签名、需重新签名，不适合作为取证手段。**替代证据**是本机同机 A/B（§5.1 vs §5.2）：两条路径唯一相关的差量就是该属性，且结果与预期方向一致。合入后在真机重跑 `CGWindowListCopyWindowInfo` 探针即可闭环。
2. **未验证 macOS 26 及更早版本** —— 本机只有 macOS 27.2。该属性是 Qt 的公开 macOS 属性（`Qt::WA_MacAlwaysShowToolWindow`），行为在 Qt 6.x 稳定，但更早系统未实测。
3. **未覆盖 overlay 的其它子窗** —— 气泡 / 灵动岛 / 桌面通知 / 截图结果浮层已各自设过该属性（见 §三 备选 3 的清单），本 PR 不动它们。若后续出现「overlay 主窗可见但某个子窗仍消失」，按同一 helper 补即可。
4. **不影响 topology 判定** —— 本修复不能替代「overlay 为何是默认拓扑」的设计讨论；它只让默认拓扑在 macOS 上行为正确。

## 八、风险与回滚

- **影响面**：仅 `OverlayWindow` 构造期多一次属性下发；对 Windows / Linux 是空操作。不改 flags、不改 z-order、不改输入穿透、不改脏矩形。
- **开关**：无。没有新增配置键，**无配置迁移**。
- **回滚**：`git revert` 即可，无落盘残留状态（不写文件、不写配置）。回滚后 overlay 桌宠恢复「切应用即被 Cocoa 隐藏」的既有行为，legacy 不受影响。
- **签名 / 打包**：不涉及构建脚本、不改 `packaging/`、不新增随包二进制。

-----

## 九、第二轮改进（对齐 issue #262：补原生 `setHidesOnDeactivate:NO`）

**触发**：提交后排查「按本 PR 思路切 legacy 拓扑绕过时，桌宠拖不动 / 点击无气泡 / 右键无菜单」的过程中，检索到仓库里已有的 [`#262 mac 焦点问题 && pet 隐藏问题 修复记录`](https://github.com/MerZlin/dsh-pet-indesktop/issues/262)（miku19960917，2026-10-13，macOS 26.2 真机）。该记录**独立报告了与本 PR 完全相同的根因**（"macOS 的 Cocoa 在 `Qt.Tool` 窗口所属应用失去焦点时自动隐藏它"），但多给出一条对本 PR 直接致命的实测结论：

> **`WA_MacAlwaysShowToolWindow` 属性在 macOS 26 上不再生效**，`[NSWindow hidesOnDeactivate]` 默认返回 YES。

#262 给出的修法是走原生：`[window setHidesOnDeactivate:NO]`（外加 `setCollectionBehavior`），且调用点在 `pet/window.py` **和** `pet/overlay_window.py` 的 `showEvent`。

**为什么必须跟进**：本 PR 第一轮只补了 Qt 属性这一条路。若 #262 的结论成立（macOS 26 上属性不生效），那么本 PR 对 macOS 26 用户**等于没修**——而这正是本 PR 要解决的报障面。因此改为**两条路并存**，不替换：

| 路径 | 生效条件 | 本机实测 |
|---|---|---|
| Qt 属性 `WA_MacAlwaysShowToolWindow`（第一轮，构造期） | 依赖 Qt 版本对该属性的实现 | macOS 27.2 上**有效**（legacy 拓扑带它 → 失活仍在屏；overlay 不带 → 在屏 2→0） |
| 原生 `-[NSWindow setHidesOnDeactivate:] = NO`（第二轮，`showEvent`） | 与 Qt 版本无关，直写 Cocoa 真正的判据 | 真 cocoa 实测**下发返回 True**，且注入版 overlay 失活不再隐藏 |

两条都留着：任一条在某个系统版本上失效，另一条仍然兜住。

### 第二轮修改文件说明

| 文件 | 增删（相对 `main` 累计） | 改动意图 |
|---|---|---|
| `pet/platform_mac.py` | **+58 / −0** | 新增 `_mac_set_hides_on_deactivate(view_id)`：照既有 `_mac_set_window_level` 的 ctypes/objc 口径（`sel_registerName` 必须声明 `restype=c_void_p` 以免截断 SEL 段错误；`BOOL` 必须用 `ctypes.c_bool` 而非 `c_long`），把 `-[NSWindow setHidesOnDeactivate:]` 置 NO。与既有 helper 同口径地**先判平台**：非 darwin 或非 cocoa 直接返回 False，绝不碰 objc（offscreen 下 `winId()` 不是 NSView 指针，objc_msgSend 会 SIGSEGV 且捕不到）。 |
| `pet/overlay_window.py` | **+18 / −1**（含第一轮） | ① 第一轮：`__init__` 补 `_keep_macos_tool_window_visible(self)`；② 第二轮：`showEvent` 补 `_mac_set_hides_on_deactivate(int(self.winId()))` —— 必须在 `showEvent` 而非构造期，因为构造期 `winId()` 不指向就绪的 NSView。调用点**无条件调用**（不写 `if sys.platform=='darwin'`）：helper 在非 cocoa 平台本身就是安全 no-op，这样测试不必 patch 全进程级的 `sys.platform`。 |
| `tests/test_overlay_window.py` | **+81 / −0** | 在第一轮 2 条之上新增 2 条：③ `test_overlay_show_event_pushes_native_hides_on_deactivate`（替换 helper 后断言 `show()` 确实调到它）；④ `test_mac_set_hides_on_deactivate_is_safe_off_cocoa`（offscreen 下必须返回 False 且不碰 objc —— 这条是防 SIGSEGV 的守卫，将来有人删掉平台判定会以**进程崩溃**而非断言失败的形式暴露）。 |

### 第二轮性能分析

**方法**：`QT_QPA_PLATFORM` 清空走真 cocoa，`QWidget` 上 `setWindowFlag(Tool)` 后 `show()` 取 `winId()`，循环调用取均值（N=20000）。环境：macOS 27.2 · Apple Silicon · CPython 3.13.15 · PySide6 6.12.0 · **platformName=cocoa**。

| 指标 | 实测 | 归属 |
|---|---|---|
| 真 cocoa 下发是否成功 | `_mac_set_hides_on_deactivate(winId) -> True` | 新增（正确性） |
| 单次成本 | **57.5 µs** | 新增 |
| 触发频率 | **每次 `showEvent` 一次**（显示/重新显示时），非每帧、非每 tick | 新增 |

**结论（逐条）**：

1. **稳态开销**：无。不进入 tick/绘制路径。
2. **新增路径绝对成本与频率**：57.5 µs / 次。注意这 **57.5 µs 里绝大部分不是 objc 调用本身，而是每次调用都重做 `ctypes.util.find_library('objc')` + `ctypes.cdll.LoadLibrary()`**——这与既有 `_mac_set_window_level` 的写法逐字一致（刻意不引入进程级缓存，免得又多一份全局状态）。按一次 show 计，相对 8 ms 帧预算 0.7%，且不在帧路径上。
3. **新系统调用 / 网络 / 磁盘 / 线程**：无网络、无磁盘、无线程；多一次 `dlopen` 查找（库已加载，走缓存路径）。**刻意不新增 objc 线程或常驻缓存。**
4. **内存与缓存**：无增长（无新增容器/缓存）。

### 第二轮测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `ruff check pet tests scripts` | **All checks passed!** |
| 聚焦 | `pytest -q tests/test_overlay_window.py` | **21 passed, 1 skipped**（第一轮 19+1，本轮 +2） |
| 红→绿（本轮改动） | 只删掉 `showEvent` 里那一行调用后重跑 `-k pushes_native` | **1 failed —— 断言失败**（"showEvent 没有下发原生 setHidesOnDeactivate:NO"），恢复后 1 passed |
| 真 cocoa 正确性 | 见上表 | 下发返回 **True** |
| 全量 | `python -m pytest -q` | **已跑 → 见本节末「第二轮的完整套件结果」**：1 failed / 7456 passed / 69 skipped |

### 第二轮的一处自我更正

第一轮报告 §二「未改动」里写过 `pet/window.py`（legacy）「它一直是对的」。这句话**只对"可见性修复"这一件事成立**，容易被读成 legacy 整体无恙。第二轮真机排查确认：**legacy 的鼠标交互在 macOS 上有独立缺陷**（拖动不生效；点击被 `DRAG_THRESHOLD(5)×scale(0.72)=3.6px` 的阈值误判成拖动，进而被 `_on_click()` 开头的 `if self._just_dragged: return` 吞掉点击动画与气泡；右键菜单还依赖窗口标志不是 `Tool`）。已把该表述就地改为限定语，并将这三个缺陷**另立 issue [#275](https://github.com/MerZlin/dsh-pet-indesktop/issues/275)**（不混进本 PR：它们与本 PR 要修的是两条不同路径上的两族问题，且改动面在 `pet/window.py`，与本 PR 无交集）。这也解释了为什么"按本 PR 思路切 legacy 绕过"是错的方向。

### 第二轮的完整套件结果（补齐 AGENTS.md 的 platform-branches 门）

`AGENTS.md` 的 Change discipline 把 **platform branches** 列为"必须跑全量"的类别，本改动正是 darwin 分支。故第二轮补跑全量：

**方法**：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
**环境**：macOS 27.2 (26B5112a) · Apple Silicon · CPython 3.13.15 · PySide6 6.12.0

| 项 | 结果 |
|---|---|
| 全量 | **1 failed, 7456 passed, 69 skipped**，耗时 754.38s（12:34） |
| 唯一失败 | `tests/test_island_bevel_fade.py::test_sample_value_change_never_fades` |

**该失败与本 PR 无关，且是上游基线上就存在的（已实证，不是推断）**：

1. 单独复跑 3 次 —— **3/3 确定性失败**（不是 flaky）
2. 在 **pristine `main`（`579b401`）的独立 worktree** 上跑同一条 —— **同样失败**；并在该 worktree 上确认 `pet/overlay_window.py` 与 `pet/platform_mac.py` 里本 PR 的新符号出现次数均为 **0**（即跑的确实是无本改动的基线代码）
3. 失败原因与平台字体/文本度量有关，与窗口属性无因果关系：
   ```
   E   AssertionError: 取样点太少（36）
   E   assert 36 >= 60
   ```
   该用例断言"换字前后渲染帧的差异像素数 ≥ 60"（`set_balance_info("峰谷", "余额 ¥88888.88")` → `"余额 ¥1.00"`）。差异点数是字体的函数，本机渲染出 36 个取样点。**属既有的环境敏感脆弱断言**，跨平台/跨字体不成立。

**关于 CI**：本机是 Python 3.13.15，而本仓 CI 跑 Python 3.11（`.github/workflows/pr-test.yml`）——同一个用例在 3.11 + CI 字体环境下是否也红，需要 CI 侧的结论；无论哪种，与本 PR 的改动无关。

**关于「受影响时序族满载 3 遍」**：本 PR 不涉及时序——改动只有"构造期一次 `setAttribute`"与"每次 `showEvent` 一次 objc 调用"，**不新增线程、定时器、队列或跨线程信号**，也没有任何受时序影响的路径，故该门不适用（如实登记，而非省略）。

**rebase 到最新上游后复跑（2026-10-15）**：上游在此期间合入了 `ed84359`（#274 主宠设置会话路由），本分支已 rebase 到其上（`docs/INDEX.md` 两行报告登记冲突按"两行都留"解决）。在 rebase 后的分支上重跑全量：

| 项 | 结果 |
|---|---|
| 全量 | **1 failed, 7462 passed, 69 skipped**，耗时 707.48s（11:47） |
| 唯一失败 | 同一条 `test_island_bevel_fade.py::test_sample_value_change_never_fades`（既有，非本 PR 引入） |
| 相对 rebase 前 | passed 7456 → **7462**（+6，来自上游 #274 新增用例），失败集合不变 |

即：rebase **没有引入任何新增失败**，且唯一失败与 rebase 前逐条一致。
