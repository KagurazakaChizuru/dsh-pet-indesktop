# PR 报告：thrown × 岛静态成员碰撞泵能根修（2026-09-24）

分支：`feature/single-overlay-window`（基于 `990c34b`，一个提交）。
用户可见故障：桌宠碰撞后被击飞、岛（灵动岛静态成员）在场时**永远落不了地**，
抛掷 clip 播完停在最后一帧 = 「碰撞后画面卡住不动」。

---

## 1. 根因链（哪一行 / 哪个公式错了）

三条独立缺陷叠加，缺一条都不会「永不落地」：

### 1.1 静态成员触岛按恢复系数 1.3 反复泵能（`pet/collision.py`）

`pet/collision.py:54` 的 `STATIC_RESTITUTION = 1.3` 是**灵动岛果冻墙的入场
系数**（撞岛像撞弹床），设计意图见 legacy `pet/island_collision.py:410`：

```python
# 非 throw 分支（撞岛进抛掷的那一下）
dv = -(1.0 + collision.STATIC_RESTITUTION) * vn
...
# throw 分支（已经在抛掷中撞墙）
k = (1.0 + physics_mod.RESTITUTION) * vn_pet     # RESTITUTION=0.78 ≤ 1
```

legacy 语义里 1.3 是**一次性入场**：撞岛 → 进抛掷 → 之后岛退化成普通反弹面
（0.78）。但进程内碰撞世界把它当成了**每一次触岛的恢复系数**
（`solve_collision_impulse` 的 `FLAG_STATIC` 分支），且
`SpriteCollisionWorld._member_from_sprite` 从未把 `interaction_state == "thrown"`
写进快照（`FLAG_THROWN` 在 `collision.py:33` 声明后**全树零引用**）。于是：

```
jn = -(1 + e) * vn / (inv_m_a + inv_m_b)      e = STATIC_RESTITUTION = 1.3
出射法向速度 = e * |入射法向速度| = 1.3 * vn  → 每次触岛净吸能
```

实测（`.scratch/thrown-island-fuzz/probe.py`，落体触岛那一次）：
入射 `vy≈455` → 出射 `vy=-447`，法向分量 414 → **538**（e=1.307），
单 tick `dvy=-902.3`。10s 后速率仍 600+～1600+（初速仅 200）。

### 1.2 落在岛上的 thrown 永远满足不了 `is_at_rest`（`pet/sprite_collision.py`）

`pet/physics.py:is_at_rest` 只认屏幕地板（`py >= bottom - 1`）：

```python
if py >= bottom - 1 and abs(vy) < 1 and abs(vx) < REST_VX: return True
return bounced and speed < REST_VY and abs(vy) < 1
```

被岛托住的 sprite 位置永远在地板之上，速度被接触冲量抹平也**永远回不了
normal**——把 1.3 改成 ≤1 之后仍 23/54 在 60s 内永不落定（实测见 §6 表），
单步追踪显示它停在岛顶 `y≈290` 做 20~70px/s 的极限环。

### 1.3 thrown 状态一挂 10~16s，clip 早已播完（`pet/physics.py`）

抛掷地面段长度 ≈ `2·e·(v0-REST_VY)/(g·(1-e))`。`e=0.78 / REST_VY=40` 时，
一次满屏高度的抛掷要 **10.6s / ~12 次地面反弹**才满足 `is_at_rest`
（`legacy_compare.py` 实测），期间 `interaction_state` 一直是 `thrown`、
行为机不重绑 → 抛掷 clip 停在最后一帧。这也是"无岛对照组"在同一 10s
窗口里就有 44/54 判 "stuck" 的原因（§6）。

---

## 2. 修法

| # | 修法 | 位置 |
|---|---|---|
| ① | 快照带上 `FLAG_THROWN`；`FLAG_STATIC` 分支只在"动态方尚未抛掷"时用 1.3 弹床，已在抛掷中回落到调用方传入的恢复系数（已 clamp ≤1） | `pet/sprite_collision.py::_member_from_sprite`、`pet/collision.py::solve_collision_impulse` |
| ② | 新增「静态成员支撑落定」出口：thrown + 圆链贴住静态成员（间距 ≤2.5px）+ 速度 ≤90px/s，连续 6 tick → 速度归零 + 回 `normal`（落岛 = 落地，与抛掷物理落地动作一致） | `pet/sprite_collision.py::_settle_supported`、`pet/collision.py::circle_chain_min_gap`（新纯数学近邻助手） |
| ③ | 收敛 thrown 地面段：`RESTITUTION 0.78 → 0.68`（地面段 10.6s → 6.7s，目标"≤5s 弹跳段"）+ 新增 `GROUND_BOUNCE_STOP_VY = 120`（落地竖直速度 <120px/s 即判落地，等效弹起高度 5px——原来 40px/s 等效 0.6px，纯亚像素抖动却要多算 3~4 跳） | `pet/physics.py`、`pet/sprite_physics.py` |

① 是根因闸门；② 是"落不了地"的第二半；③ 是让 `thrown` 生命周期落回
验收窗口内。①② 单独上线（地面参数不动）时：**"永不落地"已经消掉**——
54/54 全部会落定（60s 观测窗内 max 2111 tick ≈ 12.7s），但其中 30/54
超出复现脚本的 10s 窗口，所以 ③ 是把 `stuck` 从 30/54 压到 0/54 的必要项
（见 §6.2 的取舍说明）。

---

## 3. 修改文件说明

`git diff --numstat`（不含新增测试文件）：

| 文件 | 增/删 | 改了什么 / 为什么 |
|---|---|---|
| `pet/collision.py` | +52 / −3 | `solve_collision_impulse` 的 `FLAG_STATIC` 分支改成"入场一次性 1.3、抛掷中 ≤1"（对齐 legacy `island_collision._clamp_body` 的两分支）；新增纯数学 `circle_chain_min_gap(circles1, circles2, limit=inf)`（圆链最小间距 + `<=0` 早退，服务支撑落定的近邻判定，不参与冲量求解） |
| `pet/sprite_collision.py` | +81 / −2 | `_member_from_sprite` 补 `FLAG_THROWN`（此前声明未接线）；新增 `_settle_supported` / `_touches_static` 与 `SUPPORT_PROXIMITY=2.5` / `SUPPORT_SETTLE_SPEED=90` / `SUPPORT_SETTLE_TICKS=6`（+ 构造参数）；静止豁免 guard 加 `not self._support_streak`（支撑落定按 tick 计数，不能被整 tick 跳过） |
| `pet/physics.py` | +20 / −4 | `RESTITUTION 0.78→0.68`；新增 `GROUND_BOUNCE_STOP_VY = 120.0`；`throw_step` 多一个 `bounce_stop_vy` 参数（默认新常量，`is_at_rest` 的 `REST_VY=40` 语义不变） |
| `pet/sprite_physics.py` | +3 / −1 | `ThrowPhysicsController.__init__` 多一个 `bounce_stop_vy` 并透传给 `throw_step` |
| `tests/test_thrown_static_member_settle.py` | 新增 278 行 / −0 | 产品化自 `.scratch/thrown-island-fuzz/repro.py`：18 角度 × 3 速度落定矩阵、无岛对照、出手+重力速度上限（无泵能）、抛掷撞岛出射 ≤ 入射、非抛掷入场弹床保留、落岛快速收尾、2~3 sprite + 岛确定性 fuzz（系统能量不增长） |
| `docs/PR-REPORT-THROWN-ISLAND-PUMP-2026-09-24.md` / `docs/INDEX.md` | 新增 / +1 行 | 本报告 + 索引登记（Delivery evidence discipline） |

时序纪律：新测试全部同步驱动（世界/控制器都是纯 `tick` 函数，无 QTimer、
无线程、无 sleep、无真实时钟），fuzz 用自写线性同余伪随机，不依赖
`random` 实现细节。

---

## 4. 性能分析

环境：Windows 11，Python 3.13（仓库 `.venv`），PySide6，`QT_QPA_PLATFORM=offscreen`，
`dt=0.006`。测量：`time.perf_counter()` 热路径循环 20000~30000 tick，取 5~7 次
中位数（`.scratch/thrown-island-fuzz/bench_tick.py`）。

| 场景（岛已注册） | 修复前 world.tick | 修复后 world.tick | 差 |
|---|---|---|---|
| 1 sprite，normal（**常态稳态**） | 1.715 µs | 1.711 µs | **−0.005 µs（−0.3%，噪声内）** |
| 3 sprite，normal（常态稳态） | 4.470 µs | 4.442 µs | **−0.028 µs（−0.6%，噪声内）** |
| 1 sprite，thrown | 1.728 µs | 1.728 µs | +0.000 µs（0.0%） |
| 3 sprite，thrown | 4.459 µs | 4.525 µs | +0.066 µs（+1.5%） |
| 1 sprite，岛 + thrown（含支撑判定） | 1.705 µs | 1.755 µs | +0.050 µs（+2.9%） |
| 3 sprite，岛 + thrown | 4.596 µs | 4.693 µs | +0.097 µs（+2.1%） |

结论：
- **稳态（normal sprite）零新增开销**：`_settle_supported` 只对 `thrown`
  sprite 做圆链近邻，常态下只多一次「有无静态成员」早退 + 一次状态判断，
  落在测量噪声内。
- **新增路径成本**：thrown 每 tick 每 sprite 一次圆链间距（`circle_chain_min_gap`
  带 `<=0` 早退，岛胶囊圆链 ~19 圆 × sprite 3 圆，最坏 57 次 `hypot`）≈ **0.03~0.1 µs**。
- **触发频率**：只在「岛已注册 + sprite 处于 thrown」时进入；命中接触后连续
  6 tick 即收尾，不长期驻留。
- **新增系统调用 / 网络 / 磁盘 / 线程**：无（纯浮点 + 一次 dict 查询）。
- **内存**：`_support_streak` 只保留当前被托住的 thrown sprite 条目，收尾即
  `del`，其余每 tick 清扫；上界 = thrown sprite 数（实测 fuzz ≤3 条，条目
  数与 sprite 数同阶，无增长）。
- 6ms tick（166Hz）预算下，最坏 4.7 µs/tick ≈ 预算的 **0.08%**。

---

## 5. 实机运行记录与验收真实输出

以下都是本机真实 `.venv` 运行输出（非 CI、非 mock）。

### 5.1 复现脚本（验收 1）

```
D:\dsh-pet-src> set QT_QPA_PLATFORM=offscreen
D:\dsh-pet-src> set PYTHONPATH=D:\dsh-pet-src
D:\dsh-pet-src> ./.venv/Scripts/python.exe .scratch/thrown-island-fuzz/repro.py
stuck: 0 / 54
```

修复前同一脚本（同机同环境）：

```
stuck: 54 / 54
```

落定 tick 分布（`report_numbers.py`，最终代码）：

```
island=True : n=54 min=274 median=1172 max=1559 over_10s_budget=0 contact_range=(0,67)
   有接触(44例): min=274 max=1559
   无接触(10例): min=1169 max=1298
island=False: n=54 min=1003 median=1140 max=1298 over_10s_budget=0
```

单次撞岛出射速度（入射 500px/s 正撞，`restitution_probe`）：

```
NORMAL 入场（1.3 弹床）: 620.7px/s  比值 1.24   ← legacy 果冻墙手感保留
THROWN 触岛（≤1 反弹） : 399.0px/s  比值 0.80   ← 泵能闸门
```

### 5.2 红前验证（先红后绿）

`.scratch/thrown-island-fuzz/red_before.py` 把三个修复点逐个退回修复前，
用新测试文件断言（`[RED]` = 新测试抓到）：

```
== 修复前（FLAG_THROWN 不传 + 无支撑落定 + 地面 e=0.78 + 小跳截止 40）==
  [RED  ] 矩阵落定: thrown 未落定（岛在场）：[(0,200.0),(0,500.0),...]      ← 54/54
  [RED  ] 峰值速度上限: 峰值速度越过物理上限（泵能）：[(0,200.0,1785.7,1757.6),...]
  [RED  ] 抛掷撞岛不放大:
  [RED  ] 落岛快速收尾:
  [RED  ] 多 sprite fuzz: 系统能量增长 n=2 seed=1: peak=3190438 budget=3126493
== 只恢复 FLAG_THROWN（其余仍修复前）==
  [RED  ] 矩阵落定        ← 泵能已修，但"落岛无出口"仍在
  [GREEN] 峰值速度上限     ← 泵能闸门生效
  [GREEN] 抛掷撞岛不放大
  [RED  ] 落岛快速收尾
  [RED  ] 多 sprite fuzz
```

### 5.3 测试与静态检查（验收 2 / 3）

```
D:\dsh-pet-src> set QT_QPA_PLATFORM=offscreen
D:\dsh-pet-src> ./.venv/Scripts/python.exe -m pytest tests/ -q -k "collision or physics or sprite or island or thrown"
446 passed, 2868 deselected, 7 warnings in 12.71s

D:\dsh-pet-src> ./.venv/Scripts/python.exe -m pytest tests/ -q
3303 passed, 11 skipped, 269 warnings in 280.83s (0:04:40)

D:\dsh-pet-src> ./.venv/Scripts/python.exe -m ruff check pet/collision.py pet/sprite_collision.py pet/physics.py pet/sprite_physics.py tests/test_thrown_static_member_settle.py
All checks passed!
```

### 5.4 用户可见行为

同一 `SpriteCollisionWorld` + `ThrowPhysicsController`（overlay 主路径的真实
组件，`overlay_shell.py:487-488` 的装配）下：碰撞 → `thrown` → 触岛反弹 →
落岛/落地 → `interaction_state` 回 `normal` → 行为机重绑、clip 不再停在最后
一帧。修复前该链路在有岛时 100% 卡死（54/54）。

---

## 6. legacy 对照论证

改动落在两处，分别论证：

### 6.1 `pet/collision.py`（T7 共享纯数学）：legacy 生产路径**逐位不变**

- `solve_collision_impulse` / `solve_multi_body_collision` 的**生产调用方只有
  `SpriteCollisionWorld`**（`grep` 确认：`pet/sprite_collision.py:235`；
  其余全是 `tests/`）。4.4b 之后旧的 collision 协调者已删除。
- legacy `pet/island_collision.py` 只消费 `collision.STATIC_RESTITUTION`
  （`:410`，**常量未动 = 1.3**）与 `collision.IMPULSE_MIN_APPROACH_SPEED`
  （`:378`，未动）——两条都不经过本次修改的分支。
- 新增的 `circle_chain_min_gap` 是**新函数**，legacy 无调用方。
- 因此 `island_collision` 的「非抛掷真撞 → `dv=-(1+1.3)·vn` → 进抛掷」与
  「抛掷中撞墙 → `k=(1+RESTITUTION)·vn_pet` 反射」两条业务链在结构上不变；
  `tests/test_island_collision.py` 全绿（含 `:399` 的反射系数断言、`:420`
  的弹床业务链断言）。

### 6.2 `pet/physics.py`（T7 共享纯数学）：**行为有意的定量变化**（需主人确认的口味项）

`RESTITUTION` / `GROUND_BOUNCE_STOP_VY` 被 legacy `PetWindow._tick_throw_physics`
与 `island_collision` 的抛掷撞墙反射共用，所以**这一条会改 legacy 手感**。
复刻 `window.py:4300-4345` 循环实测（`.scratch/thrown-island-fuzz/legacy_compare.py`）：

| 场景 | 旧(0.78/40) | 新(0.68/120) |
|---|---|---|
| 满屏高度垂直甩下 900 | 落地收敛 10.62s / 12 次地面反弹 / 首跳高 928px | **6.67s / 6 次 / 首跳高 705px** |
| 斜甩 900 | 10.95s / 12 次 / 首跳 284px | 7.30s / 4 次 / 首跳 128px |
| 贴地轻抛 300 | 4.92s / 10 次 / 首跳 144px | 3.40s / 3 次 / 首跳 110px |
| 高速撞右墙 3000 | 9.03s / 16 次 / 首跳 460px | 6.40s / 4 次 / 首跳 349px |

- **不变**：投掷弧线前半段、峰值速度（实测 2043.3 / 2018.6 / 848.2 / 3024.4
  逐位相同）、出手判定、落定判据语义（`is_at_rest` 与 `REST_VY=40` 未动）。
- **变了**：落地后的每次反弹少留 10 个百分点能量 → 首跳高度降到 76%/45%，
  地面段缩短 ~37%。这是为了让 `thrown` 生命周期落回 10s 观测预算、消除
  「clip 播完还挂着 thrown」的冻结观感；同一改动对两种拓扑一致（不做拓扑
  分叉，T7 保留的是"共享纯数学"本身）。
- island 抛掷撞墙反射：法向入射 −600 → 旧出射 468 / 新 408（比值 0.78→0.68）；
  −1500 → 旧 1170 / 新 1020。仍是"反射 + 衰减"，不是穿透或钉住。
- **若主人要求保留原弹跳口味**：回退 ③（`RESTITUTION=0.78`、小跳截止回
  40px/s）即可——①②仍会把"永不落地"降到 0/54（60s 窗内全部落定，
  max 12.7s），但复现脚本 10s 窗口下是 30/54；把复现窗口放到 13s 则 0/54。
  这是一次明确的取舍，写在未完成项里。

---

## 7. 未完成项 / 边界

1. **真机 GUI 未见**：本次全部证据来自真实组件（`SpriteCollisionWorld` /
   `ThrowPhysicsController`）的进程内同步驱动 + offscreen Qt，没有在真实
   桌面会话里肉眼看抛掷落地动画。原因：本机当前没有可交互的桌面会话做
   实拍回归（`QT_QPA_PLATFORM=offscreen`），offscreen 下无法观察 clip 播放。
   建议合并前用 overlay demo 实拍一次"碰撞 → 落地 → 重绑 idle"。
2. **静置在岛顶之后的走向**：收尾回 `normal` 后由行为控制器接管，宠会按
   既有 `normal` 语义（水平游走）行动，x 方向可能走出岛顶后继续"空中行走"
   ——这是 `normal` 状态既有的口径（宠物只在自己所在高度左右走），不是本次
   引入的；若要"从岛顶掉下去"需要额外的悬空重力，属新特性。
3. **口味取舍待确认**：§6.2 的 `RESTITUTION 0.78→0.68` 换来的是验收 1 的
   `stuck: 0/54`；若主人判定首跳高度不可动，改法是回退该常量 + 放宽复现
   窗口到 13s（①②已让"永不落地"归零，剩下的是地面段收敛速度）。
4. **多 sprite fuzz 的规模**：2~3 只（主人要求）；更大规模（≥5 只同时挤在
   岛上）没有扫，`_settle_supported` 的成本随 thrown sprite 数线性增长
   （已给出 1/3 只的 µs 级实测）。
5. 本次未触碰禁止区文件（`overlay_shell.py` / `overlay_window.py` /
   `pet_sprite.py` / `tick_driver.py` / `frameseq_clip.py` / `library.py` /
   `app.py` / `window.py`）。
