# PR 报告：同分辨率切刷新率 tick 不重读（refreshRateChanged 接线）

> **基线**：`ebf971e`（fix(collision): 拖拽成员速度通道）
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-30
> **范围**：2 个文件（实现 1、测试 1）
> **关联**：任务A「Windows 偶发卡顿」有界定位的实锤缺口收尾；探针两重假象修复记录见 `.scratch/HANDOFF-20260929.md`

## 一、核心特性

高刷新率屏（165Hz）上，Windows 显示设置在**同分辨率下**切换刷新率（60↔165Hz）时，
`QScreen` 只发 `refreshRateChanged`，不发 `geometryChanged`。overlay 此前只接后者，
运行中的桌宠 tick 间隔不会重读刷新率——从 165Hz 切到 60Hz 后仍以 ~6ms 满速空转
（或反向卡在 16ms 低速档），直到重启。本改动把 `refreshRateChanged` 接入既有的
几何信号槽（`_on_screen_geometry_changed`），切换瞬间 tick 档位即按新刷新率重算。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 同分辨率刷新率切换即时生效 | `refreshRateChanged` → `_on_screen_geometry_changed` → TickDriver 重读刷新率重设间隔 |

**红线 / 不变量**：`geometryChanged`/`availableGeometryChanged` 既有行为零变化
（同一槽函数只多一个信号源）；换屏/断连必须对称（旧屏的 refreshRateChanged 连接
随 `_disconnect_screen_signals` 一并摘除，不残留）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/overlay_window.py` | +133 / −8（**其中本改动仅 2 处 hunk**：`_wire_screen_dpi_signals` / `_disconnect_screen_signals` 的信号元组各 +1 项及 docstring 一行；该文件其余 ~110 行是并行会话的存活守卫/O2 外设停表 WIP，**不属于本报告范围**） | 把 `"refreshRateChanged"` 加入几何族信号元组（接 `_on_screen_geometry_changed`），断连侧对称加入；docstring 注明 Qt 6.11 信号族分工 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_overlay_window_capabilities.py` | +22 / −0 | `FakeScreen` 增加 `refreshRateChanged` 信号与 `set_refresh()`（同分辨率切刷新率的假屏驱动）；新增 `test_refresh_rate_change_rewires_tick_interval`：60→180Hz 切换后断言 tick 间隔立即重读（**先红后绿**：未接线时断言失败） |

### 未改动

- `pet/pet_window.py`（PetWindow 同族 DPR/几何接线）：按 AGENTS.md 定位，PetWindow
  只保留给 capture-mode/单宠遗留路径，「fix crashes there only」；overlay 拓扑是唯一
  被驱动的多宠面，缺口只在这里修。
- `_on_screen_geometry_changed` 本体：刷新率重读与档位重设逻辑此前已存在且正确
  （任务A 实机实证：165Hz 机上部署宠日志 `interval=6ms（满速）`），缺的只是信号源。

## 三、实现要点

信号族分工（Qt 6.11）：`logical/physicalDotsPerInchChanged` 报显示缩放，
`geometryChanged` 报分辨率/模式切换，`refreshRateChanged` 报同分辨率刷新率切换。
三类都可能导致 tick 档位依据过期，故汇入同一槽。接线助手
`_connect_screen_signal` 按名 `getattr` 连接，假屏/旧 Qt 缺该信号时**静默跳过**
（不改既有平台行为）；断连助手对 `TypeError/RuntimeError` 容错，换屏重挂对称。

## 四、性能分析

**方法（可复现）**：`QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_overlay_window_capabilities.py -q -p no:cacheprovider`
环境：Windows 11 / Python 3.13 / PySide6（项目 .venv）

| 指标 | 实测 | 归属 |
|---|---|---|
| 稳态信号连接数 | 每屏几何族 2→3 个（+1 次 `QMetaObject::connect`，一次性） | 新增 |
| `refreshRateChanged` 触发频率 | 0 次/稳态；仅在用户切换系统刷新率时触发（手动、罕见） | 新增 |
| 槽函数单次成本 | 与既有 `geometryChanged` 路径同价（重读刷新率 + 重设 QTimer 间隔，µs 级） | 既有 |
| 聚焦套件 | 12 passed in 2.38s | 既有+新增 1 例 |

**结论**：① 稳态开销零变化（多一个空闲连接，无定时器、无线程、无轮询）；
② 新增路径成本 = 一次槽调用，触发频率为用户手动切刷新率（可视为零）；
③ 无新系统调用/网络/磁盘/线程；④ 内存无增长（一个信号连接簿记项）。
无独立基准脚本——本改动不产生可测的热路径。

## 五、实机运行记录

- **根因/前提的现场复现**：任务A 探针已实证产品逻辑在真高刷屏正常——部署宠
  （D:\dsh-pet，PID 22548 时段）日志逐行可见 `tick 档位 T2→T1 触发因=animating
  interval=6ms（满速）` 与 `T1→T2 触发因=quiet interval=250ms（降载）` 交替，
  即 165Hz 机上满速/降载档均按刷新率正确计算。缺口只剩「同分辨率切换不重读」
  这一信号源缺失。
- **探针假象澄清**：任务A 早期探针曾误报「真机也卡 16ms」，定位为两重假象——
  cap 测试模块 `os.environ.setdefault("QT_QPA_PLATFORM","offscreen")` 污染了
  进程平台 + FakeScreen 默认 refresh=60；已修（flight_probe.py 改 screen=None，
  启动须 `QT_QPA_PLATFORM=windows`）。记录见 `.scratch/HANDOFF-20260929.md`。
- **用户可见行为的确认**：同分辨率 60↔165Hz 手动切换后 tick 立即跟随——**未能
  实机自动化验证**（切换系统显示设置需要用户手动操作，未打扰用户）；行为证据为
  公开 seam 的事件级回归测试（FakeScreen 发 `refreshRateChanged(180)`，断言
  TickDriver 间隔重读，先红后绿）。边界：假屏/旧 Qt 无 `refreshRateChanged` 时
  接线静默跳过，行为与改动前完全一致（`_connect_screen_signal` getattr 容错，
  见实现要点）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `.venv/Scripts/python.exe -m ruff check pet/overlay_window.py tests/test_overlay_window_capabilities.py` | All checks passed |
| 聚焦 | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests/test_overlay_window_capabilities.py -q -p no:cacheprovider` | 12 passed in 2.38s（含新回归 1 例，先红后绿已验证） |
| 受影响时序族满载 3 遍 | 同上 ×3 | 通过（改动为信号接线，无时序敏感路径） |
| 全量 | 未跑 | 改动为单文件信号接线 + 单测试文件，接口/持久数据/生命周期/平台分发均未变；按风险门聚焦+相关测试足够，跳过理由在此登记 |
| 架构红线 | 不涉及 | 未触碰退役模块与拓扑边界 |

## 七、已知限制与后续

- 同分辨率切刷新率的**真人手动场景**未实机复现（需用户切系统设置）；后续若用户
  在日常使用中切换刷新率发现 tick 未跟随， reopen 本报告。
- PetWindow 同族缺口未修（见「未改动」理由）；若未来该路径重新被驱动，需同步接线。
- 本文件还含并行会话 WIP（存活守卫 `_alive` 族、O2 外设停表 hideEvent 等 ~110 行），
  由其作者另行报告，本 PR 不包含也不评审。

## 八、风险与回滚

影响面：仅 overlay 拓扑的屏信号接线；无配置键、无持久数据、无迁移。
回滚：本改动只有两处 hunk（`_wire_screen_dpi_signals` / `_disconnect_screen_signals`
的信号元组与 docstring）+ 一个测试文件的新增段——**以已隔离提交或明确补丁为单位回滚**；
**不要**整文件 `git checkout -- pet/overlay_window.py`（该文件还含并行会话的存活守卫/
O2 停表 WIP，整文件回退会一并抹掉它们）。无落盘状态残留。
