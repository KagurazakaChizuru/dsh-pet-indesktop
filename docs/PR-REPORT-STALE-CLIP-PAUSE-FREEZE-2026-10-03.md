# PR 报告：clip 暂停标记跨绑定滞留致画面永久冻结（拖拽/走路/挂机三症同源）

> **基线**：`6b34114`（feature/single-overlay-window HEAD，PR #215 同树）
> **分支**：`feature/single-overlay-window`　**日期**：2026-10-03
> **范围**：2 个代码/测试文件（实现 1、测试 1）+ 本文档
> **关联**：用户实机报告「拖拽后偶发卡住 / 提起动画变静态图 / 挂机回来三只全冻但还在移动」

## 一、核心特性

用户实机报告三个症状，本刀证明**同源**：

1. 左键按住拖拽（不甩、只挪位置）后桌宠偶发整体卡住；
2. 按住提起桌宠时「拖拽悬空反馈」动画不播，只有一张静态图；
3. 挂机（锁屏/全屏避让）回来，三只宠全部冻在静态帧、**但位置还在移动**
   （漂移/踏步动画同样没了）——行为状态机在跑、画面永远不动。

**根因链**（每一环都有代码/日志实证，见 §五）：clip 级 `_paused` 标记跨绑定滞留。

1. 隐藏/挂起 → `sprite.pause_clip()`：当前 clip 的 `_paused=True`、定时器停；
2. 隐藏期行为链换绑（`bind_clip` 注释明示「隐藏中照常发生」）：旧 clip 只被
   `stop()`，它的 `_paused` **无人清**；
3. 恢复可见：`resume_clip()` 只续**当前** clip，旧 clip 在 `MovieLibrary._movies`
   缓存里永远揣着 `_paused=True`；
4. 日后行为轮转绑回该 clip：`FrameSeqClip.start()` / `WebMClip.start()` 都有
   `if not self._paused: 起定时器`——滞留标记让定时器**永远不起**，clip 冻在
   首帧（帧 0 经 `jumpToFrame(0)` 同步装载，所以用户看到的是一张正常的静态图，
   不是黑屏）；帧不到货 → 预取看门狗也无从告警（它只在 `_advance` 里复查，
   定时器没跑就没有 `_advance`）。

毒化逐个累积：全屏 watcher 在真实桌面每天触发数十次 hide/show（实机日志：
PixPin/Weixin/QQ/锁屏 shell 窗），每次隐藏后的 800ms 降档滞回窗口内行为链
照常换绑，就是一次毒化机会。拖拽池/走路池/待机池逐个中招后，三症齐发。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 修复 | `bind_clip` 在 sprite 未暂停时对新绑 clip 补一次 `resume()`（未暂停 clip 上为 no-op；滞留者清标记 + 起表）——预防 + 进程内自愈一体 |
| 2 | 回归 | 真 `FrameSeqClip` 双 clip 毒化链测试，先红后绿 |

**红线 / 不变量**：「隐藏期零推进」契约不破——sprite 处于暂停时换绑，新 clip
仍立刻 re-pause（既有 `test_rebind_while_paused_stays_paused` 把守，本刀后仍绿）。

## 二、修改文件说明

`git diff --numstat`：`9 0 pet/pet_sprite.py`　`33 0 tests/test_sprite_visibility.py`

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/pet_sprite.py` | +9 / −0 | `bind_clip` 的 `start()` 后分支补 `else`：sprite 未暂停 → 对新绑 clip 调 `resume()`，清掉上一次绑定世代滞留的 `_paused`（resume 内部幂等：未暂停直接 return；滞留者清标记并按 `_running` 起表、补落地帧间隔） |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_sprite_visibility.py` | +33 / −0 | 新增 `test_unbind_while_paused_does_not_poison_clip_for_next_bind`：真 FrameSeqClip×2 走「绑定→暂停→隐藏期换绑→恢复→绑回」全链，断言被滞留的 clip 再绑定时定时器必须激活（修复前 False = 冻首帧，与实机症状逐字对应） |

### 未改动（看起来相关但故意没动）

- `pet/frameseq_clip.py` / `pet/webm_clip.py` 的 `start()`：`if not self._paused`
  分支是给「隐藏中换绑」路径留的语义（调用方随后显式 re-pause），改它会波及
  全部调用方（含 legacy window 的 `_pause_activity`），风险外溢；修在契约持有
  方（sprite）一处即覆盖两种 clip。
- `restart_clip`：不加同款分支。论证——clip 只能经 `bind_clip` 成为当前 clip，
  本刀后绑定时滞留即被清掉，在绑期间只会因 sprite 真暂停而暂停（恢复路径覆盖），
  不存在「在绑且 sprite 未暂停但 clip 滞留暂停」的残态。
- legacy `pet/window.py`：AGENTS.md 划定「只修崩溃」。同理论毒化在 legacy 暂停
  语义下可能存在，但 overlay 拓扑是部署形态，本刀不扩范围。

## 三、实现要点

暂停契约的所有者是 **sprite**（`_clip_paused` 字段 + bind/restart 时的显式
re-pause），clip 的 `_paused` 只是下推状态。缺陷本质是「下推状态的生命周期
超过了契约世代」：换绑 = 新世代开始，旧世代下推的暂停没人收回。修法不是给
clip 加世代概念，而是在唯一入口（`bind_clip`）按契约持有方的当前状态强制
对齐：sprite 说没暂停，clip 就不许揣着暂停——`resume()` 恰好是这个对齐原语
（幂等、自带 `_running` 判断、顺带补 `_set_interval_now`）。

备选「`start()` 无条件清 `_paused`」被否：改变全部调用方语义，legacy window
可能依赖 `start()` 尊重既有暂停，评审面不可控。

## 四、性能分析

- **新增路径**：`bind_clip` 尾段一次 `getattr(clip, "resume", None)` + `callable`
  判断 + `resume()` no-op（未暂停时第一行就 return）。
- **实测成本**：真 `FrameSeqClip`（已 `start()`、未暂停）上 timeit 100,000 次
  合计 29.9ms → **0.299 µs/次**（Windows 本机，venv Python，offscreen）。
- **触发频率**：动画换绑 = 秒级事件（实机日志档位/动画切换间隔 5–30s），
  摊到稳态 ≈ 每 10s 付 0.3µs，**可测但无意义地小**。
- **系统调用 / 网络 / 磁盘 / 线程**：零新增（纯内存字段判断）。
- **内存**：零增长（不写任何字段、不建对象）。
- **附带收益**：被毒化的 clip 不再「占着库缓存却永远不播」；帧不到货的
  sprite 不再每天数十次空转脏矩形上报（冻结期 `_on_frame_changed` 不触发，
  该路本就静默，收益仅为消除异常态本身）。

## 五、实机运行记录

**取证（部署进程 pid 7556，`%APPDATA%/dsh-pet-standalone-webm-chat/pet-7556.log`
全时间线脚本扫描）**：

- tick 健康：`p50=6.0ms p99≤10.9ms`（标称 6ms），进程 `Responding=True`——
  不是 GUI 线程卡死；
- **全程零条** `frameseq 预取超时` WARNING——排除预取失能（看门狗 2026-09-23
  那版的根因），指向「定时器根本没跑」；
- 全屏 watcher hide/show 每天数十次（`why=` PixPin.exe / Weixin.exe / QQ.exe /
  锁屏 shell `Windows.UI.Core.CoreWindow`）——毒化机会的实机频率证据；
- 出现 `T1→T2 触发因=quiet` 降档——帧到达停止（`animating` 信号消失）的指纹，
  与「clip 全冻」互证；
- 素材排除：drag 帧序列目录 241 个 webp + `meta.json`（fps=24, frames=241）
  完好——排除素材损坏。

**回归链**：

- 红：修复前新测试 FAIL，`clip_a._timer.isActive() == False`（冻在首帧，
  与实机静态图逐字对应）；
- 绿：修复后 PASS；
- 聚焦族：`test_sprite_visibility.py + test_frameseq_clip.py +
  test_session_lock_suspend.py + test_tick_driver.py` = **87 passed, 1 skipped**；
- ruff：两文件全过；
- 全量主套件（deselect 既有肇事单条）：**4193 passed, 12 skipped, 1 deselected**（492.3s，exit=0）。

**边界（诚实登记）**：

- 部署 exe（`D:\dsh-pet`，2026-09-29 构建）**不含**本修复；构建脚本会强杀
  正在运行的桌宠，重建部署等用户点头，未做。
- 本修复对**进程内已毒化**的 clip 同样有效（下次绑定时 `resume()` 清滞留即
  自愈），但对正在运行的旧进程无回溯——用户当前桌宠要重启/重建后才能吃到。
- 「真人在桌面拖拽后不再卡」属于真人手动场景，未实机复演；替代证据 =
  毒化链全程真实 Qt 对象（真 FrameSeqClip/真 QTimer/真 webp 帧）的红绿对照
  + 线上日志指纹对齐。

## 六、本地 PR 说明草稿

> **修什么**：拖拽后偶发卡住 / 提起动画变静态 / 挂机回来三只全冻但还在移动——
> 三症同源于「clip 暂停标记跨绑定滞留」：隐藏期换绑只 stop 旧 clip 不清它的
> `_paused`，恢复只续当前 clip，旧 clip 下次起播看到滞留标记不起定时器，
> 画面永久冻在首帧。
> **怎么修**：`bind_clip` 在 sprite 未暂停时对新绑 clip 补一次幂等 `resume()`
> （+9 行），契约持有方对齐下推状态；新增真 FrameSeqClip 毒化链回归（+33 行）。
> **成本**：0.299µs/次换绑（实测），零系统调用零内存增长；隐藏期零推进契约
> 不变（既有测试把守）。
