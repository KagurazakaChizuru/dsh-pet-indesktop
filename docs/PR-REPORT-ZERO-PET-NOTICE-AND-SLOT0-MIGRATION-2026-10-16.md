# PR 报告：零宠物启动不再静默 + slot0 迁移不再「既没迁走又删掉」

> **基线**：`6a68570`（`origin/main` 顶端，含 #272/#274/#276–#281/#285；
> 本片开工时是 `0b7152d`，收口前合入了 `6a68570`）
> **分支**：`fix/zero-pet-notice-and-slot0-migration`　**日期**：2026-10-16
> **范围**：实现 3 个文件（`+92 / −9`）、测试 2 个文件（1 个新增，`+225 / −0`）、
> 文档 2 个文件（`docs/INDEX.md` 登记、本报告）
> **关联**：GitHub issue [#286](https://github.com/MerZlin/dsh-pet-indesktop/issues/286)；
> 相关既有报告 [`PR-REPORT-CURSOR-PASSTHROUGH-2026-10-15.md`](PR-REPORT-CURSOR-PASSTHROUGH-2026-10-15.md)（#277）、
> [`PR-REPORT-SLOT0-SETTINGS-271-2026-10-15.md`](PR-REPORT-SLOT0-SETTINGS-271-2026-10-15.md)（#274）、
> [`PR-REPORT-SETTINGS-POLISH-2026-10-16.md`](PR-REPORT-SETTINGS-POLISH-2026-10-16.md)（全量红先例）

## 一、核心特性

issue #286 的现场是「**进程在、托盘在、桌面上什么都没有**」，而且从用户侧完全无法自查：
日志停在 `进入事件循环`、CPU 累计 **0.72 s 且 5 s 不增长**、无线程活动、无子进程、无 TCP
连接——观感等同于「启动失败或被安全软件拦了」。根因不是某个异常被静默吞掉（报告者这一点
的推断不成立，见 §三），而是**「一只宠物都没有」这个合法状态本身不报错、不打日志、不给任何
提示**。本片把它变成可观测的，并顺手处理同一族数据卫生问题：slot0 迁移在目标档案已存在时
**不写目标却照样清源**——该数据卫生口径在 §九 被大幅更正（"清源"保留、"不留可恢复副本"
才是真缺陷）。

| # | 能力 | 说明 |
|---|---|---|
| 1 | overlay 零宠物不再静默 | 启动收口处若一只 sprite 都没有：WARN（含活跃集合与配置目录）+ 托盘 tooltip 说实话 + 恢复窗开着且空白时补一句说明 |
| 2 | legacy 零宠物不再静默 | `_build_empty_pet_tray`（只剩托盘、没有捕获窗那条路）补同样的 WARN + 托盘 tooltip |
| 3 | slot0 迁移不再"既没迁走又删掉且无处可读" | `already-exists` 支**不覆盖目标**、**清源每宠键**（与 `Config.save()` 的全局清理同一条规则），清源前先保证恢复路径真的留住了那批值（规范备份装的就是它们就直接用，该路径被另一份快照占用则不覆盖它、另存时间戳恢复副本）；未采用的键名登记在 `retained_keys`，`copied_keys` 只记真写进档案的。**§九 更正**：本片首版写的是"该支不清源"，实测在盘上不成立（见 §九） |

**红线 / 不变量**：

1. **零宠物仍是合法状态**，本片**不**替用户造宠物、**不**改活跃集合、**不**碰任何档案
   ——只陈述与指路（与 `PR-REPORT-SLOT0-SETTINGS-271` 的「不覆盖、不自动修复」同口径）。
2. **`_slot0_profile_diagnosis` 一个字节都不写**。它是"slot0 档案降级"的专用诊断源，
   被 `_spawn_failure_text`、托盘 tooltip、恢复窗三处读；往下塞别的东西会顶掉坏档案路径
   （见 §三「自查到的一处自伤」）。
3. **迁移的目标档案在 `already-exists` 支一个字节都不许动**（既有用例
   `test_slot0_migration_never_overwrites_existing_profile` 逐字节钉死）。本片只做减法：
   不再删源，绝不新增对目标的写入。
4. **空合成窗必须处处穿透**（零 sprite 时逐像素判据恒为 `True`）。这是既有设计，本片钉住
   它而不是改动它——一个看得见又不可穿透的全屏置顶窗才会造成"整个桌面点不动"。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---:|---|
| `pet/overlay_shell.py` | +54 / −0 | ① `_build` 尾段（`_slot_signature_cache` 之后）新增一行调用 `self._announce_no_pets_if_empty()`——放在 `_build_tray()` **之后**，因为托盘是零宠物态下唯一的可见入口，提示要能改到它；② 新增 `_announce_no_pets_if_empty`（`_all_sprites()` 非空即返回；否则 WARN + 托盘 tooltip + 恢复窗**空白时**补文案）与 `_no_pets_reason`（按三条已知入口如实陈述原因，**不猜**：优先用 slot0 降级诊断，其次"活跃清单为空"，最后"清单里的宠物都没能建起来"）。整段是**一个 hunk**，不含任何多屏几何改动。 |
| `pet/app.py` | +14 / −0 | `_build_empty_pet_tray` 补 docstring 说明"这里必须留一条 WARN"、补 WARN（含活跃集合与配置目录）与托盘 tooltip 实话化；菜单与恢复窗的既有可见入口一字未动。 |
| `pet/pet_profiles.py` | 首版 +24 / −9；**§九 更正后 +90 / −20** | `migrate_slot0_profile`：首版把 `already-exists` 支改成**不再清源**——§九 实测该口径在盘上不成立（`Config.save()` 会把它抹掉，`retained_keys` 成了骗人的字段）且把双真值写成了"修复"。更正后：两条支**都清源**（与 `Config.save()` 同一条规则），清源前用新增的 `_backup_holds_values` 验"备份真的装着即将被清掉的那批值"，验不过就在**不覆盖**规范备份的前提下另存时间戳恢复副本（新字段 `recovery_path`），取不到副本就**不清源**并返回 `backup-failed`；`retained_keys` 语义改为"未采用的源每宠键（值在备份里）"；模块头与函数 docstring 同步。`retained` 显式初始化（首版漏了，`created` 支会 `UnboundLocalError`，见 §五）。 |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---:|---|
| `tests/test_no_pet_startup_notice.py`（新增） | +201 / −0 | 7 项：overlay 零宠物 WARN + 点名配置目录、恢复窗说明与托盘 tooltip、有宠物时不打该 WARN（对照）、**空合成窗处处穿透**守卫、**零宠物不得占用 slot0 诊断源**（含下游契约：生成失败仍须带该槽档案路径）、legacy 零宠物 WARN + 点名配置目录、legacy 恢复入口不许被日志改动挤掉。 |
| `tests/test_pet_profiles.py` | 首版 +24 / −0；**§九 更正后 +96 / −9** | 首版那一条（源每宠键原样保留）在 §九 被**改写**为新契约：目标字节不变、源每宠键清干净、被清掉的值可从备份取回、`retained_keys` 如实登记、`copied_keys` 为空、且**不把源几何补进档案**。新增 3 例：与真 `Config.save()` 的一致性（迁移清源 == 保存清源，两条路不许有分歧）、规范备份被旧快照占用时另存恢复副本且**旧备份逐字节不动**、取不到恢复副本就**不清源**且目标不动。 |

### 未改动（明确不做）

- `pet/window_placement.py`、`pet/pet_sprite.py`、`pet/overlay_window.py`、`pet/platform_win.py`：
  **一个字没动**。issue #283（多屏拖拽在 sprite 世界回归）的修复已从本片**拆出**单独留存，
  不在本提交内——它的核心能力本机单屏无法真机验证，不该与本片一起进。
- `tests/test_overlay_shell.py` 等既有 overlay 用例：**一条都没改**。
- 全量里那 5 条既有红（`test_module_level_validation` ×2、`test_overlay_instance_gate` ×1、
  `test_settings_stale_form_exit` ×2）：本片不修，归因见 §六。

## 三、实现要点

**为什么修法是「说出来」而不是「强行造一只」。** 零活跃宠物是**合法**状态，有三条真实入口：
用户点过托盘「退出这只」并持久化、`overlay-active-pets.json` 损坏或版本不认识（
`load_active_set` 返回空列表）、slot0 档案降级被剥出活跃集。强行生成等于替用户改意图，也与
"不覆盖、不自动修复"的档案纪律冲突。能做的补偿是**可观测**：日志给排查（含活跃集合与配置
目录这两个最能定位的字段），托盘 tooltip / 恢复窗给用户。这也正是报告者唯一的明确请求
（"请至少把这几步的异常输出到 WARN/ERROR"）。

**报告者的推断哪里不成立。** 他列的四条初始化日志（`素材加载完成` / `恢复位置` /
`全屏监视线程` / `[VIS] 桌宠显示`）**全是 legacy 专属**，overlay 拓扑根本不打印（唯一可
grep 的拓扑行是 `pet/app.py` 的 `渲染拓扑: overlay(单合成窗)`）。所以"异常被静默吞掉"这个
方向偏了：真问题是**没有一只宠物这件事本身不报错**。另外 `PET_RENDER_TOPOLOGY=layered`
**从来不是合法值**——只有大小写不敏感的 `legacy` 判 legacy，其余任何非空值都判 overlay，
全历史从未存在过 `layered` 这个取值；他把 `layered` 当逃生门用属误解，本片不改这个判定
（改它等于改 env 契约），只把事实写清。

**为什么迁移没有选择「把源值合并进目标」。** 目标档案在 `already-exists` 支上
**不许被写**（既有用例逐字节钉死），所以"补目标缺的键"这条路会破掉一条已发布的契约。
这一半仍然成立。

**首版给出的另一半理由（"不清源是纯减法、零写入风险"）是错的，§九 已更正。** 实测：
`Config.save()` 对全局身份**无条件** `pop(PER_PET_KEYS | SLOT_LOCAL_KEYS)`，所以
"不清源"在盘上根本留不住东西——下一次保存就把源里那批键抹掉，`retained_keys` 描述的
"保留"不成立；而且全局配置与槽档案同时装每宠值正是规范禁止的双真值。正确口径是
**清源 + 由备份承担"不丢数据"**：见 §九。

### 自查到的一处自伤（保留对照）

零宠物提示的**首版**把"没有可显示的桌宠：…"也写进了 `OverlayShell._slot0_profile_diagnosis`。
那一条属性是**专用诊断源**——`_spawn_failure_text` 在它非空时优先引用它，从而让"生成失败"
的说明带上坏档案路径（`pet/overlay_shell.py:4480-4481`）。塞进一句笼统文案等于把那条线索
顶掉：`tests/test_slot0_lifecycle.py::test_spawn_failure_reaches_the_recovery_window_when_no_pet_is_visible`
当场红（全量分片里抓到的，基线该文件 51 passed → 本片 1 failed）。

定性：**不是测试太严，是我的改动越权**——把一个属性的语义边界跨用了。修法是收敛到"只走
日志 + 托盘 tooltip + 恢复窗**空白时**补一句"，`_slot0_profile_diagnosis` 一个字节不写。
同一轮补了两条守卫：一条钉"零宠物不得占用 slot0 诊断源"，一条把下游契约直接钉住
（零宠物之后 `_spawn_failure_text(0, exc)` 必须**仍然带该槽档案路径**）。

教训：**给"诊断/状态"这类共享字段写入前，先找全它的读方。** 与既有先例同源
（[`PR-REPORT-ISLAND-HOVER-OSCILLATION-2026-10-13.md`](PR-REPORT-ISLAND-HOVER-OSCILLATION-2026-10-13.md)
的"给悬停触发写判据前必读"）。另一个副产物：单跑聚焦族（当时 203 passed）**发现不了**这类
跨文件的字段跨用，只有全量门能。

## 四、性能分析

**方法（可复现）**：

```bash
QT_QPA_PLATFORM=offscreen PYTHONIOENCODING=utf-8 \
  .venv/Scripts/python.exe .scratch/probe_perf_nopet.py
```

环境：Windows 11，Python 3.12.10，PySide6/Qt 6.12，offscreen，n=20000×5（稳态）/
n=2000×5（异常态）取中位。

| 路径 | 归属 | 实测 | 触发频率 |
|---|---|---|---|
| `_announce_no_pets_if_empty` 早退（有宠物） | 新增（稳态） | **0.233 µs/次** | 每次构建一次 |
| `_announce_no_pets_if_empty` 全路径（零宠物，含一次 `logging.warning`） | 新增（异常态） | **53.233 µs/次** | 仅"确实一只都没有"时，一次性 |

legacy 侧的 WARN 是一条 `logging.warning`（`_build_empty_pet_tray` 本来就要建托盘与菜单，
日志相对那次托盘构造可忽略）。逐条回答模板四问：

1. **稳态开销**：有宠物时新增路径就是一次 `self._all_sprites()` 判空 —— **0.233 µs**，
   每次构建触发一次（不是每帧、不是每次 tick）。相对构建期（`_build` 建行为/碰撞/物理/
   探头/彩蛋/托盘，毫秒级）完全在噪声内。
2. **新增路径成本与触发频率**：零宠物时才走全路径，**53.2 µs**（几乎全部是那一次
   `logging.warning` 的格式化与写盘），每次构建一次。零宠物是异常态、不是常驻态。
3. **有无新的系统调用/网络/磁盘/线程**：**没有**。新增的是一次日志写入与一次
   `setToolTip`（Qt 内存态）。迁移侧反而**减少**一次 `cwl.atomic_write_json(src)`——少一次
   磁盘写与一次锁内落盘，这是本片唯一的 I/O 净变化。
4. **内存与缓存**：零新增容器与缓存；`_announce_no_pets_if_empty` 只在栈上拼一个字符串，
   `_no_pets_reason` 返回一个新字符串。`retained_keys` 是结果对象上的一个元组（既有字段，
   此前恒为空）。

## 五、实机运行记录

本机 Windows 11，真实环境（非 CI、非 mock）。**如实登记：issue #286 的现场无法在本机复现**——
报告者是 Windows 11 + 2560×1600 @150% 从 v4.2.1 覆盖升级，且失效当下的状态需要用
`GetWindowLongW(hwnd, GWL_EXSTYLE) & 0x20` 取一次读数才能分辨"穿透态"与"吞点击态"；
本机是单屏、且没有那台机器的历史配置目录。本片能取到的是**代码级与断言级**的确定性证据：

- **零宠物状态确实存在且可达（源码级）**：`load_active_set` 对 `corrupt` /
  `unsupported-version` / `unreadable` 一律返回 `()`（`pet/pet_profiles.py:539-544`），
  而 `_build` 里 `if 0 in self._remembered_active:` **没有 else**——这一支在改造前既不报错
  也不打日志。新增用例构造的就是这个状态（空活跃集合 + 坏 `config-slot-0.json`）。
- **红→绿取证（撤掉产品改动即红）**，两批分别执行：

  | 产品改动 | 撤掉后 | 断言 |
  |---|---|---|
  | `pet/pet_profiles.py`（**§九 更正后的版本**） | 4 failed | 清源未发生 / 与 `Config.save()` 的分歧 / 旧备份被当成恢复路径 / 取不到副本仍清源 |
  | `pet/overlay_shell.py` + `pet/app.py` | 3 failed / 3 passed | WARN 与诊断缺失；3 个守卫（有宠物不报警、空窗穿透、legacy 恢复入口）前后皆绿 |
  | 零宠物提示首版（越权写 `_slot0_profile_diagnosis`） | 3 failed | 含 `tests/test_slot0_lifecycle.py` 那条既有用例，见 §三「自伤」 |
  | 首版"不清源"口径（**§九 判定为错**） | 1 failed | `assert remaining[key] == source[key]`——首版把这条**保留**当成了正确契约 |

- **实现过程中自己踩到并修掉的两个真实缺陷**（都留在报告里不删）：
  1. `retained` 未在 `created` 支初始化 → `UnboundLocalError`，被
     `tests/test_pet_profiles.py` 当场抓出（首轮 `6 failed`）。
  2. 零宠物提示越权写共享诊断字段 → 被全量分片抓出（见 §三）。
     两次都是"跑门禁才暴露"，不是 review 出来的。
- **用户可见行为的确认**：无。本机没有真实用户参与，也没有 #286 报告者那台机器；
  托盘 tooltip / 恢复窗文案的可见性由 offscreen 下的 `QLabel.text()` 与
  `QSystemTrayIcon.toolTip()` 断言覆盖（能证明赋值正确，**不能**证明用户在真桌面上看得见）。
  `#286` 的最终确认应由维护者在下一个版本包上请报告者复测（见 §七）。

## 六、测试与验证

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `python -m ruff check pet/ tests/` | **All checks passed!** |
| 聚焦（本片） | `pytest -q tests/test_no_pet_startup_notice.py tests/test_pet_profiles.py tests/test_slot0_lifecycle.py` | **124 passed** |
| 受影响族 | `pytest -q tests/test_no_pet_startup_notice.py tests/test_pet_profiles.py tests/test_slot0_lifecycle.py tests/test_overlay_shell.py tests/test_overlay_window_capabilities.py tests/test_overlay_peripherals.py tests/test_overlay_tray_icon.py tests/test_overlay_tray_routing.py` | **226 passed** |
| 受影响时序族满载 3 遍 | 16 个 CPU 繁忙进程打满 16 逻辑核后重跑上一条 | **226 passed × 3**（wall 30 / 27 / 30 s） |
| 全量 | `python scripts/ci_shards.py`（四分片，Windows 已知 access violation 的既有处置） | **5 failed / 7727 passed / 17 skipped**——5 条**全部**是既有的上下文脆弱，见 §八 归因 |
| 架构红线 + 文档纪律 | `pytest -q tests/test_architecture.py tests/test_pr_report_discipline.py` | **176 passed** |

**断言有效性**：三批红→绿证据已在 §五 逐条登记。三条守卫（有宠物时不打该 WARN、空合成窗
处处穿透、legacy 恢复入口仍在）在产品改动前后**都绿**——它们防的是"为了消灭静默而误报"
与"为了让空窗可点而改坏穿透"，属于必须双向成立的断言。

## 七、已知限制与后续

1. **`#286` 的「整屏鼠标失效」没锁定到唯一状态**。报告者同时说"exstyle 含
   `WS_EX_TRANSPARENT` 常驻"与"整屏鼠标失效"，这两句互相冲突：前者是穿透态（桌面正常、
   宠物点不到），后者是 `_press_global` 卡死导致的"全屏吞点击"态。
   `GetWindowLongW(hwnd, GWL_EXSTYLE) & 0x20` 一位就能分辨，但**需要报告者在失效当下取
   一次读数**。本片做的是让零宠物状态可观测（本片）+ 基线已自带 #277 的穿透卡死修复与
   #274 的 slot0 路由修复（**未发布**，v4.3.0 里没有）——所以下一步是发布一个带它们的版本
   请报告者复测，而不是继续盲改状态机。
2. **零宠物时本片不隐藏那个全屏空窗**。改动它需要同时处理"后来生成宠物时把窗显示回来"
   的耦合，且本机单屏无法验证真桌面观感；而空窗在既有实现下**恒为穿透**（本片已用守卫钉住），
   即不会吞桌面点击。触发条件是有人报告零宠物时桌面受影响，届时应做的是"零 sprite 不 show
   窗口 + 生成时补 show"。
3. **采集到的诊断只在有日志/托盘/恢复窗时可见**。若用户既没有托盘又看不到恢复窗（极端
   环境），这条 WARN 是他唯一能提供的证据——这是刻意的取舍，不额外造第四个入口。
4. **issue #283（多屏拖拽在 sprite 世界回归）与 #275（macOS legacy 三缺陷）不在本片**。
   #283 的修复已完成并单独留存（`.scratch/keep-283/`：完整 diff、两个测试文件、报告全文），
   它的核心能力本机单屏无法真机验证，应单独走一次带假屏证据的 PR；#275 需要 macOS 真机，
   且报告者的第二条机制经代码核对**不成立**（`was_dragging` 为真时 `_on_click()` 根本不会
   被调用，`pet/window.py:3278-3308` vs `:3309`）。

## 八、风险与回滚

**影响面**：overlay 与 legacy 两条拓扑在"零活跃宠物"时的日志与提示文案；slot0 迁移在
"目标档案已存在"时的源清理行为。**不影响任何正常路径**（有宠物时的稳态开销 0.233 µs，
迁移在 `created` 支逐位不变）。

**配置迁移**：**没有新增或修改任何配置键**。但本片**改变了迁移的源清理语义**
（`already-exists` 支），按 [`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md) 的
适用范围（"修改保存语义"），该门**触发**并已登记 2026-10-17 一条变更记录。§八 首版写的
"门不触发"是判断错误，特此更正。

**回滚**：`git revert` 本片即可，无残留状态。**迁移侧注意**：本片更正后
`already-exists` 会清源（与首版相反），回滚会把这条口径再翻回去——两版都是"删源"派
（旧版删、首版不删但被 `Config.save()` 补删），所以回滚不会让已经清掉的值回来；
真正兜底的是备份与恢复副本（`config.json.pre-slot0-migration*.bak`），它们**只增不改**，
回滚不动它们。

**分支与合并**：本片开工基线是 `0b7152d`，收口前已合入 `6a68570`（#285 播放器路径）。
那一次合并冲突只有 `docs/INDEX.md` 一处（两方都在"PR 报告存档"表头下新增行），解法是
**两行都留**：upstream 的 `PR-REPORT-MUSIC-PLAYER-PATHS-2026-10-16.md` 行 + 本报告行。
§六 的全部门禁数字都是在**当时那棵合并后的树**上重跑得到的。

**收口合并（2026-10-17）**：本片在收口时又合入了一次当前 main —— `origin/main`
= **`056dc2a`**（含 `#287` 桌面/Android 4.3.1、`#288` 每屏合成窗与逐宠跨屏、
`#291` 歌词直连）。**注意别被本仓库的本地 `main` 分支骗了**：本地 `main` 停在
`99bdc7f`（落后于 `origin/main`），按它判祖先会得出"已经是最新、无需合并"的错误结论；
判定必须用 `origin/main`。这次合并两处冲突，同样按"两边都留"解：

| 冲突文件 | 两边各是什么 | 解法 |
|---|---|---|
| `docs/SETTINGS-CHANGE-GATES.md` | 两边都在「变更记录」顶部新增一条 | 按时间倒序并列保留（2026-10-17 本条 / 2026-10-16 `allow_cross_screen`） |
| `pet/overlay_shell.py` `_build` 尾段 | 本片的 `self._announce_no_pets_if_empty()` / `#288` 的 `self._built = True` | 两个都留：调用在前、`_built` 在后（公告属建壳尾段；`_built` 的两个读点都在运行期路径上） |

合并后专门核对了"零宠物判据在多屏模型下是否还成立"：`_build_slot_sprite` 仍维护
`self.sprite` / `self._spawned`（同时把 sprite 挂进该屏 `pet_host.overlay`），
所以 `_all_sprites()` 依旧是真值来源，不会因为"宠在别的屏"而误报零宠物。
§九之六 与 §九之七 的门禁数字都是在这棵**合并后**的树上重跑的。

### 交付补记（合并后重跑的门禁）

- `ruff check pet/ tests/`：**All checks passed!**；`git diff --check`：干净。
- 本片聚焦（notice + profiles + slot0_lifecycle）：**124 passed**。
- 受影响族：**226 passed**；满载 3 遍（16 个 CPU 繁忙进程打满 16 逻辑核）：
  **226 passed × 3**（wall 30 / 27 / 30 s）。
- 架构红线 + 文档纪律：**176 passed**。
- 全量四分片：**5 failed / 7727 passed / 17 skipped**
  （分片明细 1744+1971+1980+2032 passed，9+3+3+2 skipped）。本片新增的
  `tests/test_no_pet_startup_notice.py` 落在分片 2 且**通过**。

**全量红归因（跑基线对照，不靠推断）**：这 5 条与**同一套四分片跑在 `origin/main` 上**
的失败集合逐条相同、落点分片也相同，且**单独跑全过**、文件全在本片改动之外：

| 失败用例 | 本片（合并后） | 基线 `origin/main` | 归属 |
|---|---|---|---|
| `test_module_level_validation.py::test_catalog_animation_count_guard_survives_optimize` | 分片 2 红 | 分片 2 红 | 既有 |
| `test_module_level_validation.py::test_festival_id_guard_survives_optimize` | 分片 2 红 | 分片 2 红 | 既有 |
| `test_overlay_instance_gate.py::test_real_second_process_refused_on_overlay_topology` | 分片 3 红 | 分片 3 红 | 既有 |
| `test_settings_stale_form_exit.py::test_product_confirm_discard_reads_the_real_button_click` | 分片 4 红 | 分片 4 红 | 既有 |
| `test_settings_stale_form_exit.py::test_discard_unverified_notice_is_a_real_visible_box` | 分片 4 红 | 分片 4 红 | 既有 |

其中 `test_discard_unverified_notice_is_a_real_visible_box` 已有先例登记
（[`PR-REPORT-SETTINGS-POLISH-2026-10-16.md`](PR-REPORT-SETTINGS-POLISH-2026-10-16.md) §六之一：
"0ms 探针 + 前序用例事件循环污染"，并给了"基线只加 30ms sleep 也复现同一条红"的对照）。
**本片不修这一族**；按 AGENTS.md 的 CI 纪律，该由维护者决定是隔离出主套件还是单独办。
基线全量日志：`.scratch/full-suite-baseline.log`；本片全量日志：`.scratch/full-suite-286-merged.log`。

## 九、收口更正：`already-exists` 的"不清源"是**假保证**；#286 三条具体症状逐条复核

> 本节由收口复核补入（2026-10-17）。§一/§二/§三/§五/§八 里"该支不清源"的表述以本节为准。

### 九之一、被更正的口径，以及它为什么错

首版口径：`already-exists` 支**不清源**，源每宠键原样保留，未采用的键登记在 `retained_keys`。

**实测反驳（两层，都可复跑）：**

1. **源键在盘上留不住。** `Config.save()` 对全局身份**无条件**执行
   `for key in pet_profiles.PER_PET_KEYS | pet_profiles.SLOT_LOCAL_KEYS: payload.pop(key, None)`
   （`pet/config.py:2314-2329`），而它只在 `not target.exists()` 时才调用迁移——**目标已存在
   时迁移根本不会被 save 调到**，源里那批键就只等下一次保存被抹掉。复现脚本
   `.scratch/repro_286_retention_defeated.py`：target 已存在 + 源有每宠键 → 迁移
   `already-exists`（源键仍在）→ 紧接着一次普通 `Config.save()` → 源每宠键 `{}`。
   即"保留"最长只活到用户下一次改设置。
2. **`retained_keys` 全仓零读者**：`grep -rn retained_keys pet/` 只有赋值与 docstring，
   没有任何消费方（本片没为它接线）。
3. **它还把双真值写成了"修复"**：全局 `config.json` 与槽档案同时装着每宠值，正是规范
   禁止的"同一份数据两个活真值"。

**定性：这不是修复，是一条假保证**——文件里留不住的东西被描述成"保留"，
用户按报告复测会看到配置已空。所以它不该留在这一片里。

**还有一层容易漏掉的事实**：这条"不清源"是**本 PR 自己的改动**，不是 main 的现状。
`origin/main`（`056dc2a`）的 `pet/pet_profiles.py` 与合并基 `6a68570` **逐字节相同**——
main 上 `created` 与 `already-exists` **一直**都清源。所以下面的"回正"就是回到 main 的
既有口径；本刀相对 main 的净增量是**恢复保证**那半边（见 §九之三 的基线实测）。

### 九之二、更正后的最小一致方案（不新增持久键、不引入迁移框架）

| 项 | 改正后的口径 |
|---|---|
| 规则 | `created` 与 `already-exists` **都清源每宠键**——全局 `config.json` 不留每宠键，全仓只有这一条规则，与 `Config.save()` 的 `pop` 同源 |
| 目标档案 | `already-exists` 照旧**绝不写目标**（锁内复查；`test_slot0_migration_never_overwrites_existing_profile` 逐字节钉死） |
| "不丢数据"由谁承担 | **备份**。`_backup_file` 在这条支路之前跑（`config.json.pre-slot0-migration.bak`，已存在则保留第一份、**不覆盖**）。清源前再用 `_backup_holds_values` 验一次"这份备份**装的就是即将被清掉的那批值**"（值逐条相等——比 `_is_global_config_snapshot` 的"键在不在"强） |
| 恢复副本 | 规范备份路径已被**另一份快照**占用时（旧快照也能过键存在性校验），**不覆盖它**，另存 `config.json.pre-slot0-migration-recovery-<毫秒>-<pid>.bak`（时间戳 + pid ⇒ 结构上不可能覆盖任何既有文件），走新增字段 `recovery_path` |
| 拒绝不可恢复的删除 | 恢复副本写不出 → **不清源**、不写目标、返回 `backup-failed`（宁可留下双份，也不做不可恢复的删除） |
| 可诊断 | `retained_keys` = 未采用的源每宠键；`reason` 点名备份/副本**文件名**；另有一条 WARNING 写明路径与键名 |
| **明确不做** | 不新增任何持久键；不引入 retain/迁移框架；不改 `Config.save()` 的 `pop`（那是单真值的落地处）；**不把源几何补进既有档案**（"不覆盖目标"是已发布契约） |

### 九之三、隔离复现：三种现场（`.scratch/repro_286_backup_route.py`）

三种现场都是**合法配置**（target 已存在、源里有 v4.2.1 形态的每宠键），跑完迁移**再**跑一次
真 `Config.save()`：

| 现场 | 迁移结果 | 规范备份被覆盖? | 恢复副本 | save 后源每宠键 | **不可恢复的键** |
|---|---|---|---|---|---|
| A 无备份 | `already-exists` | （本次新建） | 无（规范备份就是这批值） | `{}` | **无** |
| B 备份是**另一份**快照 | `already-exists` | **否** | 有 | `{}` | **无**（值在副本里） |
| C 备份=当前源 | `already-exists` | 否 | 无 | `{}` | **无** |

**B 这一行是真正需要修的场面**：`_is_global_config_snapshot` 只查键**存在性**，所以一份
**旧**快照也能通过校验、并被"保留第一份"规则保护下来；此时若照旧清源，源里**当前**的每宠值
就再无着落（旧版本退回过、又升级回来时真实可达）。

**为什么没去"把那个校验改严"（值也要相等）——那会把数据卫生问题升级成启动失败。**
`_is_global_config_snapshot` 是 `_backup_file` 的**入场判据**：判不过就返回
`BACKUP_INVALID` → 迁移返回 `backup-invalid`，而 `backup-invalid` **不是**
`SLOT0_DEGRADED_STATUSES` 里的状态 ⇒ `app.py` / `overlay_shell._build` 会
`raise RuntimeError`（**整个应用起不来**）。为了"备份证据更严"让用户开不了机，
是把范围判错了（ops D2 的教训：一份坏档案只该降级那一个槽）。所以改法是把严格性
放进**局部**判据 `_backup_holds_values`：它答否时既不中止、也不丢数据，只是**另存一份
恢复副本**再清源。用户拿到的是"应用照常起 + 值可从副本取回"。

**基线对照（实测，不是推断）**：把同一份现场跑在收口合并进来的 `origin/main`
（`056dc2a`，其 `pet/pet_profiles.py` 与合并基 `6a68570` **逐字节相同**——main 上根本没有
PR 里那条"不清源"）上：

```
migrate status      : already-exists
有 recovery_path 吗 : 字段不存在
规范备份未被覆盖    : True
save 后源每宠键     : {}
备份里可取的每宠键  : {'rx': 1.0, 'ry': 2.0, 'screen_name': 'D1', ...}   ← 旧快照
不可恢复的键        : ['rx','ry','screen_name','facing','scale','character']
```

⇒ **main 的版本同样清源、同样不覆盖旧备份，但没有任何恢复副本，B 现场在 main 上就是
真丢 6 个键**。所以本刀相对 main 的净增量不是"改清源口径"（那一半与 main 一致），
而是**把"清源前先保证恢复路径真的留住了这批值"做成机制**：验值（`_backup_holds_values`）、
占位就不覆盖旧备份而另存恢复副本（`recovery_path`）、拿不到副本就宁可不清源
（`backup-failed`），外加 `retained_keys`/`reason`/WARN 的可诊断信息。

### 九之四、#286 三条具体症状的复核（用隔离合法配置，不碰真实 APPDATA/CU）

| 症状 | 隔离复现 | 现在的结论 |
|---|---|---|
| **不可见**（进程在、托盘在、桌面上什么都没有） | `issue286/repro_a_no_pet.py`（5 个状态：正常升级 / 二次启动 / 空活跃清单 / 活跃清单损坏 / slot0 档案损坏） | 本片**已变成可观测**：空活跃清单与损坏两族都打出 `overlay: 启动后没有任何宠物（活跃集合=[…]，配置目录=…）`，`_build_empty_pet_tray` 走"只有托盘、无窗"。仍是**合法状态**，不造宠物 |
| **不可见（第二种机制，与零宠物无关）** | `issue286/repro_c_fullscreen_hide.py`（注入全屏 probe `hit=True`，不依赖本机真的有没有全屏应用） | 复现成立，且**它是另一回事**：全屏误判时 `auto_hide_fullscreen` 把 overlay 藏起来 —— `overlay.isVisible()=False`、`auto_hidden=True`，**进程存活、托盘仍在、没有任何报错**，用户看到的就是"桌宠不见了、没有窗口、没有错误"；退出全屏后**自愈**（无条件依赖那条 1 Hz 探测）。它有一行**专属**的 INFO 日志：`overlay: 全屏状态变化 hit=True why=…`。**这条日志的有无就是两种"不可见"的分界**——报告者贴的日志里既没有这条、也没有零宠物 WARN，所以他的现场更符合"零宠物"（改造前那条路径一条日志都不打，见 §一） |
| **迁移**（升级/降级往返） | `repro_a` 的 `normal-upgrade`→`created`、`second-boot`→`already-exists`；`repro_286_backup_route.py` 的 A/B/C | 迁移本身幂等、可重跑；清源与 `Config.save()` 一致；被清的值可从备份/恢复副本取回。**"迁移把位置/设置弄丢"这条现在可以排除**：源键从来不进读端（见下一行），丢位置只可能是**档案自己没有几何** |
| **拖回右下角** | `issue286/repro_e_position_corner.py`（真 `OverlayShell` + 仓内替身，1920×1080 可用区 1920×1040，用户原位置 rx=0.31 ry=0.42） | **本片修不了，首版也修不了**（下表实证）。覆盖层主宠落点取自**槽档案**：`_build_slot_sprite` → `overlay_spawn_state._clean_geometry(profile.data)` → `_spawn_sprite_pos`，`rx/ry` 为 `None` 就 `_default_corner_pos`（右下角）。全局 `config.json` 的 `rx/ry` 在覆盖层里**没有读者**，而"绝不写目标"是已发布契约 ⇒ 迁移**无法**把源几何补进档案 |

`repro_e` 实测（三行都是合法配置，迁移在每行都跑过）：

| 场景 | migrate | 档案 rx/ry | sprite 落点 | 落默认右下角? | 迁移动过目标? |
|---|---|---|---|---|---|
| A 档案有位置 | `already-exists` | `0.31 / 0.42` | **(535.2, 396.8)** | 否 | 否 |
| B **只有全局**有位置 | `already-exists` | `None / None` | **(1775.0, 959.0)** | **是** | 否 |
| C 两边都没有（基线） | `already-exists` | `None / None` | (1775.0, 959.0) | 是 | 否 |

**所以：本片不声称 #286 已根治。** 已确定的部分是"零宠物不再静默" +
"迁移的源清理口径一致且可恢复"；**未确定**的是报告者那句"整屏鼠标失效 /
`WS_EX_TRANSPARENT` 常驻"——那两句互相冲突（前者是穿透态=桌面正常，后者是
`_press_global` 卡死造成的全屏吞点击），一个 `GetWindowLongW` 读数就能分辨，
必须有报告者那台机器的证据。

**给报告人的最小所需证据（一次就够）：**

1. 失效**当下**取一次窗口扩展样式读数（普通权限即可，**不需要管理员**）。先拿窗口句柄：

   ```powershell
   Get-Process dsh-pet-standalone* | Select-Object Id, MainWindowHandle
   ```

   再读 `GWL_EXSTYLE`（`-20`），看 `0x20`（`WS_EX_TRANSPARENT`）那一位：

   ```powershell
   python -c "import ctypes; u=ctypes.windll.user32; print(hex(u.GetWindowLongW(<上面那个 MainWindowHandle>, -20)))"
   ```

   **`0x20` 置位 = 穿透态**（宠物点不到、桌面正常）；**未置位 = 吞点击态**
   （整个桌面点不动）。这一位就是两条互相冲突的描述的分界线。
2. 同一时刻的**完整日志尾部**（不只是"停在进入事件循环"那一段，要含启动那几行）。
   最省事的路子是托盘右键「打开配置目录」，日志与配置都在
   `%APPDATA%\dsh-pet-standalone-webm-chat\`。
   **要看的关键一行**：有没有 `overlay: 全屏状态变化 hit=True …`。
   有 → 是"全屏误判把桌宠藏起来"那条路（`auto_hide_fullscreen`，退出全屏会自愈，
   与"进程还在但看不见"吻合）；**没有** → 排除它，指向"零宠物"那条路（本片已修成
   可观测，新版会打 `overlay: 启动后没有任何宠物（活跃集合=…，配置目录=…）`）。
   这一行有无，就等于把"不可见"的两个机制分开——比继续猜状态机省事得多。
3. 配置目录里 `overlay-active-pets.json`、`config.json`、`config-slot-0.json` **三个文件的内容**
   （每宠键与活跃集合是判断"零宠物 / 档案降级"的关键）。
4. 出问题的版本号与升级来源版本（例：从 v4.2.1 覆盖升级到 v4.3.x）。

**可直接回复报告人的文本（拟稿，未发送——外发动作需用户批准）：**

> 谢谢反馈，也谢谢那份日志和读数。它们把问题缩小到了**两个可分辨**的现场，剩下的只差一次
> 读数。
>
> 先说能确定的部分：v4.3 的单合成窗拓扑下，「一只宠物都没有」是一个**合法但完全静默**
> 的状态（用户点过托盘「退出这只」、`overlay-active-pets.json` 损坏或版本不认识、slot0 档案
> 降级被剥出活跃集，三种都会走到）。旧版在这种状态下照常显示一个全屏空窗（或只剩托盘图标），
> **不报错、不打日志**——你看到的「进程在、托盘在、桌面上什么都没有」正是它。我们已修成
> 可观测：启动时留一条 WARN（含活跃集合与配置目录）、托盘 tooltip 如实说明、恢复窗空白时补一句
> 解释。请注意它**不会**自动替你造一只宠物（那会改你的意图），但托盘和恢复窗里都有显式的生成入口。
>
> 另外还有一个**长得一样、机制完全不同**的情况：桌宠在系统认为"有全屏应用"时会被自动隐藏
> （壁纸引擎全屏、某些播放器的全屏窗口都可能被误判）。它也会让桌宠"不见了但进程在、托盘在"，
> 退出全屏后会自己回来，而且它**会**在日志里留一行 `overlay: 全屏状态变化 hit=True …`。
> 所以请你在日志里搜一下这一行——**有没有它**就直接把这两种情况分开了：
> 有 → 是全屏误判那条路；没有 → 是"零宠物"那条路。
>
> 最后还需要你帮一件事，来定「整屏鼠标失效」那个根因：你说「exstyle 含 `WS_EX_TRANSPARENT`
> 常驻」和「整屏鼠标失效」——这两句描述的是**两个不同**的状态，一个是"桌面正常、只是宠物点
> 不到"，另一个是"整个桌面都点不动"。分辨它们只需要在失效**当下**取一次读数（普通权限即可，
> 不需要管理员）：
>
> ```powershell
> Get-Process dsh-pet-standalone* | Select-Object Id, MainWindowHandle
> python -c "import ctypes; u=ctypes.windll.user32; print(hex(u.GetWindowLongW(<上面取到的 MainWindowHandle>, -20)))"
> ```
>
> 最后那个十六进制数里，**`0x20` 这一位**在不在，就决定了是哪一种：
> 在 = 穿透态（宠物点不到、桌面正常）；不在 = 吞点击态（桌面也点不动）。
> 顺手把同时刻的**完整日志尾部**与配置目录里 `overlay-active-pets.json` / `config.json` /
> `config-slot-0.json` 三份内容贴一下，我们就能给出确定的结论，而不用再猜。

（外发需用户批准；本节只备稿。）

### 九之五、性能分析（本次更正带来的增量）

**方法（可复现）**：

```bash
PET_SRC=<tree> python .scratch/probe_perf_migration.py
```

环境：Windows 11，Python 3.13.7（仓库 `.venv`），n=400 × 3 轮取中位；每轮**重写源**
`config.json`（迁移会把源每宠键清掉，不重写第二轮就走不到这条支路），只计
`migrate_slot0_profile` 自身。基线 = 把 `pet/pet_profiles.py` stash 掉后跑同一脚本。

| 分支（每进程启动一次，`already-exists`） | 修前 | 修后 | 增量 |
|---|---:|---:|---:|
| 规范备份本来就是这批值（读 + 比值，不复制） | 2262.9 µs | 4298.5 µs | **+2035.6 µs** |
| 规范备份是另一份快照（比值不中 → 另存恢复副本） | 2325.2 µs | 6659.3 µs | +4334.1 µs |
| 纯新增逻辑 `_backup_holds_values`（单测口径，n=20000 × 5） | — | **193.4 µs/次** | — |

**怎么读这张表**：上两行是**整条支路**的耗时，不是纯新增逻辑。修后这条支路多了两件事：
①`_backup_holds_values`（读一次规范备份 JSON + 逐键比值）= **193 µs**，这是真正新增的
工作；②**清理源**那一次 `atomic_write_json(src, …)` —— 它是 `Config.save()` 的下一次保存
本来就要做的写入（`pop` 之后整表落盘），本刀只是把它移到迁移这一步来做，所以是
"同一份工作提前做"，不是净新增。第三行那个 193 µs 才是可归给本刀的净开销。

逐条回答模板三问：

1. **稳态开销 / 触发频率**：这段逻辑每次**进程启动**跑一次（`app.py` / `overlay_shell._build` /
   空身份设置会话各一处），**不是每帧、不是每次保存**。净新增 ≈ **0.19 ms / 次进程启动**；
   在启动总耗时（建行为/碰撞/物理/探头/托盘/素材，百毫秒级）里是噪声。
2. **新系统调用/网络/磁盘/线程**：**没有**新线程、没有网络。磁盘上多**一次读**（读规范备份）；
   只有在"规范备份装着**别的**快照"这一稀有支路上才多**一次写**（恢复副本，字节数 =
   `config.json` 磁盘大小，上表 +2.4 ms 就是它）。`created` 支与既有失败路径逐位不变。
3. **内存**：无新增容器与缓存，只在栈上多一个"键→值"小字典（`copied` 键数级，
   实测 8 键）；`recovery_path` 是结果对象上的一个 `Path | None` 字段。

### 九之六、门禁（本次更正，合并 origin/main **之前**的树上）

见 §六 的同一批命令在更正后的树上重跑结果，本节只记**新增**的门：

- 静态检查：`python -m ruff check pet/ tests/` → **All checks passed!**
- 聚焦：`pytest -q tests/test_pet_profiles.py` → **98 passed**
- 消融（撤掉 `pet/pet_profiles.py` 的产品改动）：
  `pytest -q tests/test_pet_profiles.py -k existing_profile` → **4 failed / 1 passed**
  （那 1 passed 是既有的 `test_slot0_migration_never_overwrites_existing_profile`，
  它只钉"目标字节不变"，前后都该绿）
- 受影响族（profiles + slot0_lifecycle + no_pet_startup_notice + slot0_ownership +
  slot_and_memory + config_schema）→ **227 passed**
- 文档纪律：`pytest -q tests/test_pr_report_discipline.py tests/test_architecture.py`
- 隔离复现（不碰真实 APPDATA）：`issue286/repro_a_no_pet.py`、`repro_e_position_corner.py`、
  `.scratch/repro_286_retention_defeated.py`、`.scratch/repro_286_backup_route.py`

### 九之七、门禁（合入 `origin/main` 056dc2a **之后**的树上重跑）

| 门 | 结果 |
|---|---|
| `ruff check pet/ tests/` | **All checks passed!** |
| `git diff --check` | 干净 |
| 聚焦 + 受影响族（上一节 7 个文件 + `test_overlay_shell.py` + `test_overlay_window_capabilities.py`） | **303 passed** |
| 文档纪律 + 架构红线（`test_pr_report_discipline.py` + `test_architecture.py`） | **186 passed** |
| 全量四分片 | **1 failed / 7877 passed / 27 skipped**（`EXIT=1`，脚本判"分片失败：[3]"）；分片明细 1764+2082+1982+2049 passed、11+4+9+3 skipped。日志：`.scratch/full-suite-289-merged.log`。**那条红的归因已更正并重跑（2026-10-17）→ §九之八** |
| 隔离复现复跑（多屏模型下）：`issue286/repro_e_position_corner.py` | 三行结果与合并前**逐字相同**（A 落原位 535.2/396.8、B/C 落右下角 1775.0/959.0，迁移都没动目标）——`#288` 之后这条结论不变 |

**那 1 条全量红的归因（与上一节那 5 条既有红不是同一批）**：

| 失败用例 | 落点 | 归因 |
|---|---|---|
| `tests/test_screen_capture_ocr.py::test_self_built_sessions_are_injected_into_the_engine_cfg` | 分片 3 | **环境缺可选依赖 + 该用例少一道守卫**，与本刀无关 |

三条依据：

1. 失败点是 `tests/test_screen_capture_ocr.py:909` 的 `from omegaconf import OmegaConf`
   —— **裸 import，没有守卫**；同一文件里相邻两条同类用例（`:823` / `:930`）都写了
   `pytest.importorskip("rapidocr", reason="未安装本地 OCR 依赖（rapidocr）"）`，这条漏了。
2. `omegaconf>=2.3` **确实写在 `requirements.txt:85`**，但这**次全量跑的那个解释器里没有**
   —— 见 §九之八的指认（跑全量的是 `D:/dsh-pet-src/.venv`，`include-system-site-packages=false`，
   系统解释器里其实装着）。是环境缺包，不是代码回归。
3. 该测试文件与本刀**无关**：`git diff 056dc2a HEAD -- tests/test_screen_capture_ocr.py`
   **为空**（与 `origin/main` 逐字节相同，来自更早的 `03768bc`）。加上第 2 条，同一断言
   在 `origin/main` 上**必然同样失败**——当初只写了演绎；**§九之八补上了同解释器上的真红复现**
   （装包前 `1 failed`、装包后 `1 passed`）。

**本刀没有改那个测试文件**：它在 screen-capture/OCR 那条线上，不在本片（slot0 迁移/设置语义）的
范围内，改它会把一个不相干的文件拖进本片 diff；缺的那味药在环境侧（§九之八补装声明过的依赖，
**没有**给用例加 skip、没有放宽任何断言）。`:909` 那行本身缺守卫的观察仍然成立，是否收归
screen-capture 线的作者自便。本片新增/改写的用例（`tests/test_pet_profiles.py` 4 例）
在分片里**全绿**。

**合并后专门复核过的一件事**：`#288` 把 sprite 分散到每屏宿主，但 `_build_slot_sprite`
仍维护 `self.sprite` / `self._spawned`，所以零宠物判据 `_all_sprites()` 不会因为
"宠在别的屏"而误报（否则会在有宠的机器上打出假的零宠物 WARN）。

### 九之八、分片 3 那条红的归因更正 + 分片重跑（2026-10-17）

§九之七 那句「本机解释器里 `import omegaconf` 直接 ModuleNotFoundError」**指错了对象**：
缺包的确实是环境，但是**跑那次全量的那个隔离环境**，不是系统解释器。按**同一个环境**重跑
分片 3 之后，那条红已消失（分片里的红换成了另一条环境依赖用例，见下）。本节只记这件事。

**1. 指认跑全量的解释器（证据在盘上）**

| 事实 | 命令 | 输出 |
|---|---|---|
| 全量分片用的 pytest 是 9.1.1 | `ls tests/__pycache__/ \| grep -oE "pytest-[0-9.]+" \| sort -u` | `9.1.0`（系统解释器，04:28 那次）与 `9.1.1`（**03:30–03:40 那次全量**）两套 pyc 并存 |
| 项目隔离环境就是 9.1.1 | `D:/dsh-pet-src/.venv/Scripts/python.exe -m pytest --version` | `pytest 9.1.1`（Python 3.13.7） |
| 系统解释器是 9.1.0、且**装着** omegaconf | `python -m pytest --version` / `python -c "import omegaconf,omegaconf;print(omegaconf.__file__)"` | `pytest 9.1.0` / `...Python313\Lib\site-packages\omegaconf\__init__.py`（2.4.0） |
| 隔离环境**看不到**系统 site-packages | `cat D:/dsh-pet-src/.venv/pyvenv.cfg` | `include-system-site-packages = false` |

**2. 同一个解释器上的真红复现（装包前）**

```
$ QT_QPA_PLATFORM=offscreen D:/dsh-pet-src/.venv/Scripts/python.exe -m pytest -q \
    tests/test_screen_capture_ocr.py::test_self_built_sessions_are_injected_into_the_engine_cfg
E       ModuleNotFoundError: No module named 'omegaconf'
tests\test_screen_capture_ocr.py:909: ModuleNotFoundError
1 failed in 2.29s
```

对照（系统解释器，同一用例、同一棵树）：`1 passed in 2.98s` ——
所以这条红**只由解释器决定**，与代码分支无关。这就是 §九之七 第 3 条当初只敢写"演绎"的那一步，
现在补成了实测。

**3. 补装（不改测试、不加 skip）**

```
$ D:/dsh-pet-src/.venv/Scripts/python.exe -m pip install "omegaconf>=2.3"
Successfully installed PyYAML-6.0.3 omegaconf-2.4.0
```

`omegaconf>=2.3` 本来就写在 `requirements.txt:85`，所以**仓库里一行都不用改**：缺的是
环境里那一份（同一环境的 `rapidocr` 也缺，但它的每处用例都写了 `importorskip`，所以只有
`:909` 这条裸 import 会红——27 个 skip 里就有它们）。装完同一条用例：**1 passed**。
没有给任何用例加守卫、没有放宽断言、没有 `-k` 掉任何东西。

**4. 分片 3 重跑（只有这一个分片，其余三片沿用 04:01 那次同解释器的绿结果）**

- 文件清单按 `scripts/ci_shards.py` 的同一条切法重算（93 个文件：`tests/test_now_playing_session_probe.py … tests/test_settings_default_marks.py`，**与 04:01 日志里分片 3 的表头逐字相同**）；
- 运行器 `.scratch/rerun_shard3.py`，日志 `.scratch/shard3-after-omegaconf.log`；
- 结果：`1 failed, 1982 passed, 9 skipped`——**条数不变，红的那条换了人**：

| | 分片 3 之前（04:01） | 分片 3 之后（补装依赖后） |
|---|---|---|
| `test_screen_capture_ocr.py::test_self_built_sessions_are_injected_into_the_engine_cfg` | **FAILED**（ModuleNotFoundError） | **passed** |
| `test_proactive.py::TestVisionAndWatcherPhase2::test_foreground_window_info_real_call_no_shadow_bug` | passed | **FAILED** |

**可加总的真实结果**：三片未重跑的绿结果（1764+2082+2049 passed、11+4+3 skipped、0 failed）
＋ 分片 3（1982 passed、9 skipped、1 failed）＝ **7877 passed / 27 skipped / 1 failed**。

**剩下这 1 条红的性质（不是本刀、也不是本片环境缺包）**：桌面当前的前台窗口是不可见的
`WeChatAppEx.exe`（class `Chrome_WidgetWin_0`）宿主窗，而 `pet/vision.py::foreground_window_info`
按自身契约对不可见窗口返回 None——用例断言的是"桌面上存在可见前台窗口"这件**外部事实**。
不是本刀引入：`git diff 056dc2a HEAD -- tests/test_proactive.py pet/vision.py` **为空**；
平行输入链路片（`D:/dsh-pet-wt-input-final`，直接基于 `origin/main` `056dc2a`）上同一条用例
同样红，那一片正用「真实可见性前置条件 + 不放松断言」收它（只改该测试，不动产品）。**合并顺序
建议**：那一片先合，本片的分片跑就无红（本片不重复改那个文件，避免同一个 hunk 落两处）。

**5. 同一棵树上其余门禁（同一个 venv 解释器）**

| 门 | 命令 | 结果 |
|---|---|---|
| 静态检查 | `ruff check pet/ tests/` | **All checks passed!** |
| 聚焦 + 受影响族（11 个文件：`test_pet_profiles` / `test_slot0_lifecycle` / `test_no_pet_startup_notice` / `test_slot0_ownership` / `test_slot_and_memory` / `test_config_schema` / `test_overlay_shell` / `test_overlay_window_capabilities` / `test_overlay_peripherals` / `test_overlay_tray_icon` / `test_overlay_tray_routing`） | 见左 | **329 passed**（含 §九之七 那批 303 例的超集） |
| 文档纪律 + 架构红线 | `pytest -q tests/test_pr_report_discipline.py tests/test_architecture.py` | **186 passed** |

全量**没有**整跑（本轮只重跑红片）：这是任务边界（避免重复 25 分钟），三片绿结果与分片 3
同属 04:01 那一次、同一棵树（本刀此后只动过本报告这一份文档）。
