# PR 报告：每屏一窗的独立多屏 + 「允许桌宠跨屏」开关（`docs/PR-REPORT-PER-PET-MULTISCREEN-2026-10-16.md`）

> **基线**：`6a68570`（`origin/main`，含 #285 播放器）
> **分支**：`feat/per-pet-multiscreen`（worktree `D:/dsh-pet-wt-multiscreen`）
> **日期**：2026-10-16
> **范围**：累计 **36 个文件 `+4144/−463`**（本分支相对 `origin/main`，含先前一片宿主化改造，
> `git diff --numstat origin/main`）；
> 其中**本刀** = `bcac67c..1dfad90` 的 18 个文件 `+923/−18`（开关与位置归属语义首版）
> ＋ `1dfad90..5c3fe80` 的 9 个文件 `+535/−67`（提交前双审缺陷的修正与回归，见末节）
> **本刀提交**：`518480d`（实现与测试）→ `1dfad90`（文档与索引）→ `5c3fe80`（双审修正）
> → **`7ef7b71`（文档口径更正，当前 HEAD）**
> **已推送并开 DRAFT PR（不可合并状态）**：`feat/per-pet-multiscreen`，base `main`；
> **不 merge、不删分支、不 release**
> **运行期状态（2026-10-16 深夜更新）**：二审判定的 5 条缺陷里，前 4 条已修并补回归；
> 第 5 条「弹簧档跨屏位置连续性」**已在第三轮修掉**（三片：临时合法域 + advance 后按实际
> 位置移交 + 原子换帧；松手不被控制器拽回；跨缝只读投影）——见 §「第三轮」。
> **"绿"与"连续性达标"仍分开记**：第二轮的测试只证明弹簧滞后被保留（不证明位置连续），
> 第三轮新增 `tests/test_overlay_seam_passage.py` 14 例才把"逐拍轨迹 == 无内缝参考、
> 移交原子恒等、松手/弹弓不跳、拼接像素完整"逐条钉住。
> **PR 仍为 Draft**：真机双屏未验（本机只有一块活动屏），第三轮改动**未 push**。
> 门数字：**第三轮（最终）`ruff` 通过 + 全量 `QT_QPA_PLATFORM=offscreen python -m pytest -q --timeout=300` = 7854 passed / 15 skipped / 0 failed（24:06，`EXIT=0`，`.scratch/per-pet-multiscreen/full-suite-r3.log`）**；第二轮 7840 passed / 15 skipped / 0 failed 是第二轮改动的结果（比第三轮少 14 例 = 本轮新增）。
> **关联**：[`AGENTS.md`](../AGENTS.md)（多屏段落 = 现行口径）、[`SETTINGS-CHANGE-GATES.md`](SETTINGS-CHANGE-GATES.md)（本刀新增设置的准入/准出记录）、[`INDEX.md`](INDEX.md)（本报告已登记）、
> `.scratch/per-pet-multiscreen/HANDOFF.md`（断点与未验清单）、多屏条目的 BACKLOG（`D:/dsh-pet-src/.scratch/BACKLOG.md`）；
> #284（整群搬屏）**不采用**、不混 DLC

## 〇、状态与边界（先读这一段）

- **已推送并开出 DRAFT PR（Draft = 不可合并）**：分支 `feat/per-pet-multiscreen`，base `main`；
  不 merge、不删分支、不 release。**这不是"可合并状态"**：下面第一条阻断未解决。
- **合并阻断（未解决）**：**弹簧档（`drag_physics`）跨屏时仍不满足位置连续性**——移交那一帧
  这只的全局位置仍会跳（实测 840.5 → 2009.1，**+1169 px**），来源是"每屏一窗"的**本窗钳制**
  （身体必须完整落在目标屏可用区内）。本轮只做到"不再瞬移到光标处、弹簧滞后与轨迹保留"，
  **没有做到位置连续**；实测数字与前后对照见「第二轮修正」末节。定位与修法交还主代理。
- **首轮门**：`ruff check pet/ tests/` 通过；全量 `pytest -q` **7835 passed /
  15 skipped / 0 failed**（23:17）；受影响时序族 **3 连跑各 193 passed**。
- **提交前双审（ops5.5 + astra）判定 5 条确定缺陷：4 条已修并补回归，1 条（上述跨屏连续性）
  未解决**。首轮门数已被第二轮取代，引用时只用第二轮的数字。**现有测试全绿但不覆盖
  "位置连续"这条要求**——`test_crossing_with_drag_physics_keeps_the_spring_lag` 只断言
  "不跳到光标处 + 滞后保留 + 目标换帧后全局等价"，**没有**断言跨屏前后位移连续。
- **真双屏未验**：本机 Qt 口径只有 **1 块活动屏**（§四之一），跨缝手感 / 异 DPI /
  负坐标拼接只有假屏逻辑证据（假屏不是 `QScreen`，见 §四）。
- **显存未测**：只给理论缓冲估算（§三之三），明确不是实测。
- **打包产物未构建**；macOS / Linux **未跑**（不推断）。

## 一、核心特性

用户 2026-10-16 定案：**直接采用「每块有桌宠的屏各一张合成窗」**（不再做 A/B 原型
对比），并新增一个**全局开关**控制这个能力。用户看到的变化：

| # | 能力 | 说明 |
|---|---|---|
| 1 | 每屏一窗 | 每块**被占用**的显示器各一张透明合成窗；进程、tick 时钟、音效池、联动、托盘、素材库仍只有一份 |
| 2 | 逐只独立跨屏 | 把某一只拖到另一块屏，只搬这一只；其余宠的屏、位置、边界、窗口一个像素不动 |
| 3 | 逐屏独立仿真 | 行为（漫游/落位钳制）/ 碰撞世界 / 抛掷物理 / 边缘探头**逐屏一份**：两块屏上局部坐标相同的两只宠在真机上相距上千像素，共用一个世界会被判成接触 |
| 4 | 位置记忆逐只独立 | `screen_name` + `rx/ry` 逐只落盘，比例相对**它自己那块屏**的可用区算；重启按各自记忆回各自那块屏 |
| 5 | **允许桌宠跨屏开关** | 新增全局键 `allow_cross_screen`，**默认关**、**重启生效**（进程快照）。关着时全部宠只留在启动那块屏、只有一张窗、拖不过去 |
| 6 | 关闭不丢多屏位置 | 关着（或某块屏临时拔掉）期间，位置比例照旧更新，**屏幕归属不被机械动作改写**；重新开启并重启，各宠回到各自那块屏 |

**红线 / 不变量**：

- **单屏 + 默认开关 = 旧行为逐位不变**：一张窗、一个宿主、一份控制器；关闭态没有
  任何多出来的窗口 / 线程 / 定时器。
- **共享面绝不复刻**：`TickDriver`（一个 QTimer）、音效、台词、托盘、素材库、媒体
  缓存、DSH 监视器都只有一份（`ShellOverlayWindow` 只是窗口，不持共享服务）。
- **屏归属不许被机械动作改写**：这是本刀新增的数据语义（§二之一）。
- **不做的三件事**：不 warp 鼠标、不加 native 几何兜底、不做 DLC。

## 二、修改文件说明

### 2.1 本刀新增：开关与位置归属语义

| 文件 | 改了什么 + 为什么 | ± |
|---|---|---|
| `pet/config.py` | 新增全局键 `allow_cross_screen`（默认 `False`）+ reload 白名单 + `_bool_or_default` 归一。默认关 = 存量用户行为不变 | +6 |
| `pet/overlay_shell.py` | ① 壳构造时**快照一次** `self._cross_screen_allowed`（重启级，运行期不重读，与 `stream_capture_mode` 同口径）；② `_host_for_restore` 开关闸：关着时全部宠落**启动那块屏**（不采纳记忆、不建第二张窗）；③ `route_drag_to_screen` 与 `move_sprite_to_screen` 开关闸：关着时拖拽/搬移一律拒绝；④ `_save_child_geometry` **不再无条件写 `screen_name`**，只在"本宠身上记着待写的归属"时与比例一起写；⑤ 新增 `_remember_sprite_screen`：有意换屏时唯一改屏归属的地方（`move_sprite_to_screen` 成功分支调用），**只把屏名记在这只自己身上、不在拖拽路径写盘**（单键写实测中位 3.4 ms、p95 4.2 ms，锁被占最长等 5 s，GUI 线程不为一次落盘停这么久），落盘由下一次几何自存与比例同一次原子写完成。④⑤ 合起来兑现"关闭再启动不覆盖原多屏位置" | +62/−4 |
| `pet/settings_pet_controls.py` | 新增 `CROSS_SCREEN_HINT`（行说明，末尾逐字带 `GLOBAL_SCOPE_NOTE`，由 `set_scope_note` 削到标注里）、`cross_screen_check` 控件（**非 overlay 拓扑置灰** + tooltip，理由写在行内注释）、`GLOBAL_SCOPE_ROWS` 登记（全局作用域标注） | +22 |
| `pet/modern_settings_dialog.py` | 常规域「窗口与系统」新增一行「允许桌宠跨屏」，排在窗口旗标类之后；claim 表加 id；保存回写 `allow_cross_screen` | +13/−1 |
| `pet/settings_default_marks.py` | 默认值标记映射 `cross_screen → allow_cross_screen`（出厂默认 False 可比） | +1 |
| `pet/settings_page_guide.py` | 「窗口与系统」组描述补一句"能不能拖到别的显示器上"（分组语义变了，描述同步） | +1/−1 |
| `AGENTS.md` | 多屏段落补：跨屏能力由 `allow_cross_screen` 门控、`screen_name` 是"屏归属"且只由有意换屏写、几何自存不写屏名 | +9/−1 |

**为什么把屏名从"无条件自存"里摘出来**（本刀最关键的一处：数据语义选择）

原先 `_save_child_geometry` 每次落盘都把 `screen_name` 写成"当前所在屏"。这条在
多屏下有两处会吃掉用户摆好的布局：

1. 关着跨屏启动 → 全部宠被摆到启动那块屏 → 退出自存把归属全改成那块屏；
2. 某块屏临时拔掉 → 宠被并到活着的屏 → 同样被改写。

两种情形都是**机械动作**（用户没动这只宠的屏归属），却会丢掉"这只属于哪块屏"的
记忆。改法取最小清晰语义：**`screen_name` = 屏归属，只由"有意换屏"改写**，且**与
比例同一次原子写落盘**（有意换屏时把这笔待写记在这只自己身上，退出/收尾的几何
自存把两者一起写）。这样：

- 单屏普通拖动的持久化**不受影响**（比例照旧逐次落盘，不是"关闭时一律禁写"）；
- 关闭 / 临时缺屏共**同一条**语义（用户要求"能共用就覆盖"）；
- round trip 可回归：关闭 → 拖动 → 保存 → 重新开启并重启 → 仍回各自那块屏；
- 拖拽路径（mouseMove → 跨屏路由）上**没有磁盘 I/O**：单键几何写实测中位
  **3.4 ms**（p95 4.2 ms、max 5.3 ms，n=200），且目录锁被别人占着时最长可等 `DEFAULT_TIMEOUT_S` = 5 s
  ——把这个写放进逐帧回调是不可接受的。

### 2.2 本刀修改的既有测试（都是契约随语义收紧，不是放宽）

| 文件 | 改了什么 + 为什么 | ± |
|---|---|---|
| `tests/test_overlay_hosts_multiscreen.py` | 夹具显式打开开关（本文件测的是"允许跨屏"下的合同；默认关时壳体只在启动那块屏建窗，多屏断言无从成立）；两处直接构造的 `CapConfig` 同样带上 | +8/−2 |
| `tests/test_overlay_independent_screens.py` | 同上（`_make_shell` 打开开关）；**修掉双屏夹具的 `QApplication` 实例 patch 泄漏**（只补类级 `QGuiApplication.screens/primaryScreen`——产品读的就是类级静态方法，补实例属性会在 PySide6 对象上留影子、`monkeypatch` 撤回时写回"已被补成假屏的值"，泄漏到下一条用例）；`test_each_pet_persists_its_own_screen_and_ratio` 改成新语义（没换过屏的那只档案里**没有** `screen_name`，但 `rx/ry` 照旧更新） | +21/−6 |
| `tests/test_config_schema.py` | 默认值 / reload 白名单快照加 `allow_cross_screen`（快照即现状文档化） | +1 |
| `tests/test_settings_compat_layering.py` | 「窗口与系统」行序期望补 `settingRow_cross_screen` | +1 |
| `tests/test_settings_ia_first_cut.py` | 同上：跨屏行排在窗口旗标类之后（原先断言"光标穿透是最后一行"） | +3/−1 |
| `tests/test_architecture.py` | `modern_settings_dialog.py` 行预算 2515 → **2526**（实测；带日期注释说明这 11 行是行装配 + claim + 保存回写，控件与文案落在 `settings_pet_controls`） | +6/−1 |

### 2.3 本刀新增文件

| 文件 | 内容 |
|---|---|
| `tests/test_overlay_cross_screen_switch.py`（327 行） | 开关的 8 条契约：默认关、重启级（**三进程往返**：运行中改配置不生效 → 重建后生效）、关着时全宠只在一块屏一张窗、`move_sprite_to_screen` 被拒、**真鼠标事件**拖到另一块屏仍不换宿主且被本屏钳住、关闭态普通拖动照旧落比例、**关闭→开启 round trip 回到各自那块屏**、屏临时缺失共用同一语义 |
| `tests/test_settings_cross_screen.py`（128 行） | 设置行 5 条契约：默认关 + 保存 round trip（重开对话框读回）、全局作用域标注（说明里那句被削到标注、可访问说明不丢）、非 overlay 拓扑置灰 + tooltip、默认值标记与单项重置入口、四组搜索词命中 |
| `.scratch/per-pet-multiscreen/probe_cross_screen.py` | 真机探针：`screens` 打印 Qt 屏枚举（活动屏唯一权威）；`switch` 用**三个独立子进程**在隔离 `APPDATA` 下各跑一次"写 config → 建壳" |
| `.scratch/per-pet-multiscreen/bench_hosts.py` | 同屏模拟成本实测（一宿主 vs 两宿主，A/B/A 交替多轮 + 噪声带；宿主创建/show 一次性成本；RSS/USS；理论帧缓冲估算） |
| `.scratch/per-pet-multiscreen/bench_profile_write.py` | 单键几何写的成本实测（n=200，中位/p95/max）——"屏归属不进拖拽路径"这条结论的依据 |

### 2.4 累计（本分支相对 `origin/main`，含先前一片宿主化改造）

| 文件 | ± | 一句话 |
|---|---|---|
| `pet/screen_host.py`（新） | +83 | 屏宿主：overlay + 屏局部可用区 + 该屏的行为/碰撞/物理/探头/彩蛋控制器组；`host_for_collision` 反查点 |
| `pet/overlay_shell.py` | +1256/−398 | 宿主表 + `hosts()`/`host_for_sprite`/`host_for_screen`/`_host_of`；`_create_host`/`_wire_host`/`_release_host`/`_reap_empty_hosts`；跨屏移交 `route_drag_to_screen`/`move_sprite_to_screen`/`_transfer_sprite`/`_place_sprite_in_host`；逐屏几何同步与屏事件处置；一切"整组"动作改遍历 `_hosts`（显隐/停止/关闭/整窗能力/气泡/岛墙/投喂/音效/位置监听） |
| `pet/overlay_window.py` | +59/−11 | `detach_sprite_for_transfer`（摘出但**不**广播移除、**不**释放 clip）、跨屏后的坐标换算钩子（`_sprite_event_pos`/`_follow_overlay`）、按 sprite 当前宿主取行为/探头 |
| `pet/tick_driver.py` | +45/−10 | 仿真段按宿主分组（同 tick、同 QTimer，每屏只跑自己的世界）；`hosts` 只读视图；裸 overlay（单世界装配）语义逐位不变 |
| `pet/pet_sprite.py` | +23 | `translate_frame(delta)`：拖拽中换局部坐标系时把绝对坐标类样本（弹簧目标、轨迹）整体平移；`_drag_offset` **不平移**（差值，平移反而错位） |
| `pet/sprite_behavior.py` | +7 | `forget()` 一并交还圈末回调挂接权（否则跨屏交出去的 sprite 在新世界里圈末续播永不接管） |
| `pet/sprite_sound.py` | +9/−5 | `on_collision(..., world=)`：多屏下按撞出事件的那个世界取阈值（单世界口径不变） |
| `tests/test_overlay_hosts_multiscreen.py`（新） | +637 | 宿主公开面、同局部坐标不碰撞、跨屏拖拽只迁一只、换屏不改手感（松手初速）、移交不是退出（clip/成员不注销）、DPR 跟随目标屏、关一张窗不停整组时钟、屏事件、逐宠位置记忆 |
| `tests/test_overlay_independent_screens.py`（新） | +529 | 逐只迁移合同 + 反例（另一只不动 / 空屏不留窗 / 同屏必撞对照 / 单 timer 不双重推进 / 逐只落盘与复活） |
| 其余 11 个既有测试文件 | +79/−37 | 断言随"一屏一宿主"调整（宿主枚举、窗口数、能力下发目标等） |

## 三、性能分析

**环境**：本机 Windows，Python（本仓库 `.venv`），真机唯一的活动屏 = `H27T22S`
2560×1440 / DPR 1.0 / 170Hz（Qt 枚举，见 §四之一）。同屏模拟与 CPU 数字来自
`.scratch/per-pet-multiscreen/bench_hosts.py`（offscreen 平台 + 两块几何相同的假屏），
真平台启动数字来自 §四的隔离探针。

### 3.1 稳态开销（受影响路径）

| 口径 | 1 宿主（= 默认关 / 单屏） | 2 宿主（同屏模拟） |
|---|---|---|
| `tick_sim` 每帧 | **0.212 ms**（min 0.151 / max 0.299，5 轮取中位，N=600 帧/轮，预热 200 帧） | **0.140 ms**（min 0.117 / max 0.204） |
| 多一张宿主的边际 | — | **−0.072 ms/帧**，本 harness 噪声带 **0.148 ms** ⇒ **偏移在带内，等于测不出** |

数字方向为负的解释（不作为性能结论）：拆成两块世界后每块世界里只有一只宠，成对
碰撞判定归零；同一进程里 A/B 交替跑多轮就是为了把漂移摊平，但 offscreen 平台没有
真实上屏，**painting/GPU 合成成本根本没被量到**。诚实结论：**宿主拆分在仿真段没有
可测出的每帧增量**，真实多屏的合成成本**未测**。

### 3.2 新增路径的一次性成本与触发频率

| 路径 | 触发频率 | 实测 |
|---|---|---|
| 新建一块宿主（窗 + 三控制器 + 碰撞世界） | 只在"这只宠第一次落到某块屏"那一次 | `_create_host` **0.4 ms**；该窗 `show()` **2.0 ms** |
| 有意换屏记屏归属（`_remember_sprite_screen`） | 每次用户主动跨屏拖拽落点 | **0 次写盘、0 ms**（只在这只身上记一个字符串；写盘并进下一次几何自存） |
| 单键几何写（`write_profile_geometry`，屏幕归属原先会走的路径） | 有意换屏若立即写盘会是每次 1 写 | **中位 3.423 ms / p95 4.234 ms / max 5.299 ms**（n=200，`.scratch/per-pet-multiscreen/bench_profile_write.py`）——这正是把它挪出拖拽逐帧路径的理由 |
| 位置自存（`_save_child_geometry`） | 拖动收尾 / 退出 / 开局落位 | 与改动前**同样一次写**（不再写 `screen_name` 这个键，文件字节略小；有意换屏时把屏名并进同一次写，而不是多一次写） |
| 跨屏路由判据（`route_drag_to_screen`） | 拖拽中每帧一次 | 关闭态是**一次布尔判断**后立即返回；开启态沿用原有判据 |
| 新增线程 / 定时器 / 网络 | **0** | `TickDriver` 仍只一个 QTimer；无新线程、无网络、无新系统调用 |

### 3.3 内存

| 口径 | 数值 |
|---|---|
| RSS：1 宿主 → 2 宿主 → 回 1 宿主 | 93.7 MB → 93.7 MB → 93.7 MB |
| USS：同上 | 64.41 MB → 64.41 MB → 64.41 MB（Δ **+0.00 MB**） |
| 理论帧缓冲/窗 | 面积 2560×1440 × 4 B × DPR 1.0² = **14.1 MB**（4K 2560×1440→3840×2160 时约 33.2 MB） |

**必须如实说明**：offscreen 平台不为窗口分配真实后端缓冲，所以这里的 Δ≈0 **不能**
读成"真实多屏下第二个窗口不占内存"。真实成本主要是每窗一块合成缓冲，上面给的是
**理论估算**；**显存占用本机没有可读计数器，未实测**。

### 3.4 开关关闭态（默认态）的净开销

关闭时只有一个宿主，与改动前**逐位相同**的一张窗 + 一组控制器；新增代码只有三处
布尔闸（壳构造一次、拖拽每帧一次、搬移调用一次）与"少写一个键"。**没有新的定时器、
线程、窗口或磁盘写入**。

### 3.5 测试证据

- 本刀新增 focused：`tests/test_overlay_cross_screen_switch.py` **8 passed**、
  `tests/test_settings_cross_screen.py` **5 passed**。
- 多屏两个姊妹文件：`tests/test_overlay_hosts_multiscreen.py` +
  `tests/test_overlay_independent_screens.py` **28 passed**。
- 设置侧守卫（默认值快照 / reload 白名单 / 行预算 / 分组归属 / 作用域 / 搜索 / 文案 lint）：
  全部转绿（改动前它们按预期红）。
- **受影响的真实时序族 3 连跑**（跨屏拖拽 / 宿主生命周期 / tick 驱动器 / 屏迁移 /
  设置行那一族，命令与日志见 `.scratch/per-pet-multiscreen/family-rerun.log`）：
  **3 遍都是 193 passed / 0 failed**（23.01s / 21.28s / 35.07s，`EXIT=0`）。按项目纪律本应"本地 CPU 打满跑 3 遍"，本轮**只做 3 遍串行、
  不加背景负载**——用户明确要求不要把 CPU 打满（同一台机器上还有用户自己的活）。
- **先红后绿（消融）**：逐条撤产品改动都精确令对应用例变红——
  撤 `_host_for_restore` 闸 → 2 红；撤拖拽/搬移闸 → 3 红；把快照改成运行期实时读 → 1 红；
  几何自存重新写 `screen_name` → 4 红（+姊妹文件 1 红）；撤设置页拓扑置灰 → 1 红；
  撤作用域登记 → 1 红。
- **全量套件**：`QT_QPA_PLATFORM=offscreen python -m pytest -q --timeout=300` →
  **7835 passed / 15 skipped / 0 failed / 0 error，23:17**（`EXIT=0`，日志
  `.scratch/per-pet-multiscreen/full-suite.log`）。这是**冻结改动之后**跑的整棵树，
  不是改动中途的结果。

## 四、实机运行记录

### 4.1 屏数证据（活动屏以 Qt 为准）

```
$ python .scratch/per-pet-multiscreen/probe_cross_screen.py screens
platform=windows screens=1
  [0] name='H27T22S' geo=(0,0,2560x1440) avail=(0,0,2560x1392) dpr=1.0 primary=True refresh=170.0
PRIMARY: H27T22S
```

⇒ 本机**只有一块活动屏**（设备管理器里的显示器列表不代表活动屏）。因此：
"宠拖到另一块显示器上"这一条在本机**无法实机验证**；逻辑证据是 §3 的假屏用例
（真壳 + 真 `PetSprite` + 真鼠标事件序列 + 假屏），手感想、异 DPI 观感、错位拼接的
负坐标行为**未验**。

### 4.2 开关与重启级语义（隔离 APPDATA，真 `windows` 平台，三个独立进程）

```
$ python .scratch/per-pet-multiscreen/probe_cross_screen.py switch
isolated base = C:\Users\me\AppData\Local\Temp\pet-probe-cvemyvec
STEP value=absent key_written=False snapshot=False hosts=1 host_screens=['H27T22S'] overlays=1 sprites_in_home=1 visible=[True] start_ms=485.5 tick_ms=0.033
STEP value=true   key_written=True  snapshot=True  hosts=1 host_screens=['H27T22S'] overlays=1 sprites_in_home=1 visible=[True] start_ms=404.8 tick_ms=0.028
STEP value=false  key_written=False snapshot=False hosts=1 host_screens=['H27T22S'] overlays=1 sprites_in_home=1 visible=[True] start_ms=409.8 tick_ms=0.026
FAILURES: 0
```

- **旧配置（没有这个键）→ 默认关**：升级用户不因本刀改变呈现；
- 写 true / false 各起一次**独立进程**：快照跟着磁盘走 → 这就是"重启生效"的进程级证据；
- 三次都是 **1 张窗、1 个宿主、窗真的上屏**（`visible=[True]`，真平台插件）；
- `start_ms` 是**整壳启动**（含首次建库），不是本刀的增量；`tick_ms` 是该替身素材库
  下的仿真段耗时，仅作同环境对照。
- 探针全程 `APPDATA`/`LOCALAPPDATA` 指向临时目录：**没有读写用户真实配置**，没动
  CU，没有鼠标 warp。

### 4.3 用户可见行为确认

| 项 | 结论 | 证据 |
|---|---|---|
| 单屏 + 默认关：仍是一张窗、宠物照常显示 | ✅ 实机 | §4.2 三次 `overlays=1 / visible=[True]` |
| 勾选后面板出现、文案说清"重启生效 / 关闭时只有一块屏 / 记忆不会被清掉" | ✅ 程序化（真控件 + 真 `Config`） | `tests/test_settings_cross_screen.py`（默认值、round trip、作用域标注、置灰、搜索） |
| 关着时拖不过去、不多开窗、宠被本屏钳住 | ✅ 假屏 + 真鼠标事件 | `test_off_keeps_a_cross_screen_drag_inside_the_single_window`（含"光标确实落在另一块屏"的前提断言） |
| 关闭 → 开启后回到各自那块屏 | ✅ 假屏 + 真档案文件 | `test_off_and_on_round_trip_returns_pets_to_their_own_screens` |
| **真双屏手感 / 异 DPI / 交叉区** | ❌ **未验** | 本机只有 1 块活动屏（§4.1） |
| **显存占用** | ❌ **未测** | 无可读计数器；$3.3 只给理论估算 |

### 4.4 待审风险点（留给盲审）

1. `_remember_sprite_screen` 的**屏归属语义**是否与"本宠 reset 保位置"、
   `overlay_spawn_state` 的兼容包装、以及设置页 `screen_name` 相关文案一致；
2. 宿主生命周期：`_release_host` / `_reap_empty_hosts` 在**活跃 grab** 与
   **拖拽落点在缝上**的收尾路径（本刀未改动，但开关改变了可达性）；
3. 关闭态下 `handle_screen_removed` 走到 `_migrate_to_screen` 时，主宿主换屏是否会
   误写任何屏归属（本刀口径：不写）；
4. 设置页把开关放在「窗口与系统」而非新分组，披露层级 = primary 是否可接受。

### 4.5 其他自检（换目录 / 脏值 / 多次输入）

- **换目录跑**：`cd /d && python D:/dsh-pet-wt-multiscreen/.scratch/per-pet-multiscreen/probe_cross_screen.py switch`
  → 三次 STEP 全部 `ok`、`FAILURES: 0`（与在仓库根跑逐行同形：`absent→False`、
  `true→True`、`false→False`，都在 `hosts=1 / overlays=1 / visible=[True]`）。
- **脏值不崩**：把 `allow_cross_screen` 手工写成 `"false"` / `"yes"` / `1` / `0` /
  `null` / `[]` / `{}`，`Config.get` 全部返回 **`bool`**（`"false"` → `False`，
  不是被当真的非空字符串；`null`/`[]`/`{}` → `False`），无异常。
- **多次输入**：开关探针本身就是三次不同输入（键缺失 / true / false）+ 三个独立进程。

## 五、已知限制、后续与回滚

**已知限制**

0. **【合并阻断】弹簧档跨屏位置不连续**：跨屏那一帧仍有 **+1169 px** 级跳位（每屏一窗的
   本窗钳制，1:1 路径共有）。本轮只保留住弹簧滞后，**没有**做到位置连续；现测试只证明
   滞后保留。修法待定（见「第二轮修正」末节）。
1. **真双屏没验**（本机只有 1 块活动屏）：跨缝手感、"两只窗各裁一半"的瞬间观感、
   异 DPI 缩放、上下错位拼接（负坐标 / 空洞）只有假屏逻辑证据。
2. **显存/合成缓冲没测**：只有理论估算（§3.3）。offscreen 平台不为窗分配后端缓冲，
   所以那里的内存差值不能外推到真机。
3. **打包产物未构建**：本刀不动构建脚本，但也没有产出过含本特性的包。
4. **legacy（捕获模式）下开关置灰**：那边本来就是真窗口、能跨显示器，本开关对它
   没有第二个读点；置灰 + tooltip 是如实呈现，不是功能缺失。
5. 首次跨屏时新建宿主有一次 0.4 ms + show 2.0 ms 的开销（§3.2）；这是"多一块屏"
   的固有成本，未做预热。

**后续（现状）**

- 本分支已推送并挂 **Draft PR（不可合并）**；**不 merge、不删分支、不 release**。
- **待办（交回主代理）**：定位并解决"跨屏那一帧的钳制跳位"（缺陷 4 的残余）。
  可能的着力点：允许过渡期内跨窗越界绘制的中间态、或改判据/接管时机——需另行设计，
  本轮明确不做。
- 有真双屏的环境补一次实机验收（跨缝手感 + 混合 DPI）。

**风险与回滚**

- **影响面**：`allow_cross_screen` 默认关 ⇒ 存量用户的呈现、窗口数、位置写入
  与改动前一致（§3.4）；受影响的是"打开开关之后"的行为与 `screen_name` 的写入时机。
- **配置迁移**：只有新增键，无旧键改写；`Config.reload` 白名单与归一同步登记。
  用户回退版本时该键成为未知键（被读入即保留、不参与任何判定），不产生半套状态。
- **回滚**：`git revert`（或丢弃本分支）即可；没有数据需要修复——多屏归属写在
  各宠自己的 `config-slot-N.json` 的 `screen_name` 里，旧版本不读该键的使用方式
  与本刀不同（旧版本会把它当作位置的一部分在退出时改写），但不会因此启动失败。
- **开关作为运行期降级口**：若真机上出现多屏异常，用户可以关掉跨屏开关并重启，
  回到"单屏一张窗"的旧行为，无需回滚版本。

## 第二轮修正 —— 提交前双审判定的 5 条缺陷（2026-10-16 晚）

> 双审（ops5.5 + astra）在提交前给出 5 条确定缺陷。本节按同一文档追加，保留首轮
> 叙述与对照；**首轮的门数字已被本节末尾的第二轮结果取代**。
> 基线：`1dfad90`（本轮改动 = 该提交之后的本地提交）。
>
> **结论口径（2026-10-16 晚，用户当面更正）**：**5 条里 4 条已修并补回归；第 4 条
> 「弹簧档跨屏位置连续性」未解决，判为合并阻断**。下表的第 4 行已按此改写；
> 本节末尾的实测表就是它未达标的证据。**不得把本轮表述为"5 条全部修好"。**

### 5 条缺陷、根因与处置

| # | 级别 | 缺陷（双审原文口径） | 根因 | 处置 / 状态 |
|---|---|---|---|---|
| 1 | P1 | 关闭跨屏或屏缺失时，临时承载那块屏的 `rx/ry` 会覆盖原多屏比例；保住 `screen_name` ≠ 保住位置 | `_save_child_geometry` 只要"承载屏 == 无冲突"就照写比例 | **已修**：按**承载屏 vs 屏归属**分流——不一致 = 临时承载 → **一个几何键都不写**（`_stored_screen_name` 读档案里的归属，`_remember_sprite_screen` 记的待写优先）；一致 → 照旧写比例（单屏普通拖动持久化不受影响） |
| 2 | P1 | 新生成的子宠从没跨屏 → 无 `screen_name`；主宠单独拖到副屏后重启，子宠跟着主宠也到副屏 | 无归属的落位判据是"跟随主宠那块屏" | **已修**：**首次落位即记下归属**（`_build_slot_sprite`：`_cross_screen_allowed` 且档案无 `screen_name` 时记待写 = 落位那块屏）；关闭跨屏时**不记**（那时是临时承载，记了就是缺陷 1 的覆盖） |
| 3 | P2 | 跨屏拖到副屏后、同一次 grab 里进弹弓：`event.position()` 是本窗（A）坐标，混上 sprite（B）坐标 → 抓取偏移错一个屏原点、预览画在源窗 | 弹弓的三个入口与 UI 都直用本窗局部坐标 | **已修**：① 统一输入：`_grab_cursor_pos(event)` 把事件坐标换算成**被抓住那只的坐标系**（不 warp 鼠标）；② 统一预览：瞄准 UI 的绘制与脏区按 `_follow_overlay` 归属到**持 sprite 的那张窗**；③ 壳内**共用一个** `SlingshotController` |
| 4 | P2 | `drag_physics` 时路由按光标落点 `set_pos` → 跨屏那一帧把这只瞬移到光标处、抹掉弹簧滞后 | 路由把"目标落点"当成了落点写进位置 | ⚠️ **部分修 / 未达标（合并阻断）**：改走"只换坐标系"后**不再瞬移到光标处、弹簧滞后与轨迹保留**（实现价值成立），但**位置连续性没做到**——跨屏那一帧仍出现 **+1169 px** 级跳位（来源 = 每屏一窗的**本窗钳制**：身体必须完整落在目标屏可用区内；`drag_physics=False` 的 1:1 路径同样存在该钳制）。这是**架构层面的残余**，本轮未解决，定位与修法交还主代理 |
| 5 | P2 | `_bind_position_listener` 只挂 `self.overlay`（主宿主窗）：主宠移副屏后 runtime 标记不再更新，主宿主被回收时注册连窗口一起消失 | 监听挂"家"的窗，而不是"持这只"的窗 | **已修**：挂到 `_host_of(sprite)` 那张窗，并先摘掉其它宿主窗上的同名回调 |

计分：**4 项已修（1/2/3/5）；1 项未达标（4）。**

### 修改文件说明（第二轮）

| 文件 | 改了什么 + 为什么 | ± |
|---|---|---|
| `pet/overlay_shell.py` | `_stored_screen_name`（新，只读档案里的屏归属）；`_save_child_geometry` 的**临时承载分流**（缺陷 1）；`_build_slot_sprite` 的**首次归属**（缺陷 2）；`route_drag_to_screen` 改为"只换坐标系"移交 + 判据注释写清"为什么不能用实际位置"（缺陷 4）；`_bind_position_listener` 挂实际宿主窗并清旧注册（缺陷 5）；`_wire_host_overlay` 共用一份弹弓控制器 + `__init__` 的 `_slingshot` 字段（缺陷 3） | +75/−17 |
| `pet/overlay_window.py` | `_grab_cursor_pos`（新：事件坐标 → 被抓住那只的坐标系）；瞄准移动/发射/右键进瞄准三处改用它（缺陷 3）；`_paint_slingshot` 与 `_refresh_slingshot_visual` 按归属窗绘制/刷脏区（缺陷 3） | +32/−4 |
| `pet/settings_pet_controls.py` | 行说明与注释同步（"屏与位置都不会被清掉…仍回到各自那块屏的原位置"）——行为没变，是第二轮修复让这句更准 | +3/−3 |
| `tests/test_overlay_hosts_multiscreen.py` | 新增 `_right_press` / `_painted` 助手与三节用例：跨屏组合手势（缺陷 3）、弹簧拖拽跨屏连续性（缺陷 4）、标记监听归属（缺陷 5） | +139 |
| `tests/test_overlay_cross_screen_switch.py` | 新增 `_drag_on_current_screen` 助手；round trip 改成**严格比较** `rx/ry`（含关闭期间真鼠标拖动）、新增"缺屏 clamp 后严格比较"、"关闭态不盖首次归属"、"子宠不跟主宠跑"（缺陷 1/2） | +96/−38 |
| `tests/test_overlay_independent_screens.py` | `test_each_pet_persists_its_own_screen_and_ratio` 改成新语义（首次落位就记归属） | +8/−7 |
| `AGENTS.md` / `docs/SETTINGS-CHANGE-GATES.md` | 现行口径同步：首次落位即钉归属、临时承载不写任何几何键 | +6/−4 |

### 性能分析（第二轮）

- **新增路径**：`_save_child_geometry` 多一次**档案读**（只在承载屏 != 归属时才发生，
  即关闭跨屏/缺屏这两种临时承载态；常态走 `pending` 命中，不读盘）。触发频率 = 位置
  自存频率（拖动收尾/退出/开局落位），次数与首轮相同。
- **少了什么**：临时承载态下**不再写盘**（少一次 3.4 ms 级单键写）；
  弹弓控制器从"每窗一份"变成"壳内一份"（少建 N−1 个控制器对象，实测构造 ~µs 级）。
- **没有新增**：线程、定时器、网络、系统调用一个都没加；路由那条 `set_pos` 由
  "写目标落点"变成"写实际位置"，计算量不变。
- **回归口径**：`tick_sim` 成本与首轮同（本轮不碰仿真段）。

### 测试与验证（第二轮）

- 受影响 focused：`tests/test_overlay_hosts_multiscreen.py` + `test_overlay_independent_screens.py`
  + `test_overlay_cross_screen_switch.py` + `test_sprite_slingshot.py` 等 20 个文件
  **392 passed**（一条一条先红后绿见下）。
- **消融（先红后绿，逐条归属）**：撤临时承载分流 → 关闭态 round trip + 缺屏 clamp 两例红；
  撤首次归属 → 子宠跟随那例红；弹弓输入退回 `event.position()` → 组合手势那例红；
  弹弓绘制不做归属换算 → 同一例红（脏区/绘制断言）；路由回到按落点 `set_pos` →
  弹簧滞后那例红；监听挂回主宿主窗 → 标记那例红。**6 条消融各自只打红它该打红的用例。**
- **全量门（第二轮，最终）**：`QT_QPA_PLATFORM=offscreen python -m pytest -q --timeout=300`
  → **7840 passed / 15 skipped / 0 failed / 0 error，23:00**（`EXIT=0`，
  `.scratch/per-pet-multiscreen/full-suite-r2.log`；比首轮多 5 例 = 本轮新增用例）。
- **受影响时序族 3 连跑**：**3 遍都是 198 passed / 0 failed**（21.56s / 22.24s / 35.95s，`EXIT=0`，`.scratch/per-pet-multiscreen/family-rerun-r2.log`）——同样只做 3 遍串行，不额外打满 CPU（用户口径）。
- ⚠️ **这些绿不构成"缺陷 4 已修"**：唯一覆盖缺陷 4 的用例
  `test_crossing_with_drag_physics_keeps_the_spring_lag` 断言的是
  「**不瞬移到光标处** + 弹簧目标与轨迹换帧后全局等价 + 松手不跳」，
  **没有**断言"跨屏前后位置连续"——它证明的是**滞后保留**，不是**位置连续**。
  位置连续这条要求在下面这张实测表里**明确未满足**。

#### 缺陷 4 的前后对照（实测，命令与日志可复现）——**这就是它仍未达标**

`.scratch/per-pet-multiscreen/probe_drag_cross.py`（两块 1920×1080 假屏、两只宠、
``drag_physics=True``、从屏中段起拖、末段一次 700px 大跳跨过缝）：

| 跨屏那一帧 | 修前（按光标落点 ``set_pos``） | 修后（只换坐标系） |
|---|---|---|
| 实际全局 x | 840.5 → **2357.5**（+1517.0） | 840.5 → **2009.1**（**+1168.7**） |
| 弹簧目标全局 x | 2300（= 光标锚定落点） | 2300（同一个） |
| 下一帧 | 2445.5（滞后被抹平：实际≈目标） | 2145.2（滞后保留：仍落后目标 3000） |

**读法（不要读成"修好了"）**：

- 修后**不再瞬移到光标处**、弹簧滞后与轨迹照旧延续 —— 这部分达到了缺陷 4 描述的一半；
- 但**跨屏那一帧仍跳 +1169 px**。它来自每屏一窗的**本窗钳制**（sprite 身体必须完整落在
  目标屏可用区内），与 1:1 路径**共有**同一约束，**不是**"位置连续"。
- 因此本轮把缺陷 4 记为**未解决 / 合并阻断**；本分支以 **Draft PR** 形式挂起，定位与修法
  交还主代理（可能的着力点：允许跨窗越界绘制的过渡态、或改判据/接管时机，需另行设计，
  本轮不做）。

日志：`.scratch/per-pet-multiscreen/probe_drag_cross-prefix-ablation.log`（修前 = 临时消融态，
跑完立即还原并复跑 ruff）、`.scratch/per-pet-multiscreen/probe_drag_cross-r2.log`（修后）。

### 未验边界（第二轮补充）

- **缺陷 4 的"位置连续"未验且已知未达标**（上表）；实机手感同样未验。
- 缺陷 3 的"两只窗各自裁一半"观感与异 DPI 混合缩放仍**未在真机双屏上看过**（本机只有
  1 块活动屏）——跨屏组合手势的坐标正确性只有假屏 + 真鼠标事件证据。

## 第三轮 —— 跨屏大跳的完整修复（三片，2026-10-16 深夜）

> 基线：`9307459` 之前一片为 `9fde6fe`（第一片）、`9307459`（第二片）、`39d1cdf`（第三片）。
> **结论**：第二轮的单一合并阻断（跨屏那一帧 +1169 px 级跳位）在"每屏一窗"现架构内
> 修掉了；**不再把它当成固有可接受**。三片各自可独立回滚。
> **PR 状态不变**：本机只有一块活动屏，实机双屏手感仍未验，PR 保持 Draft（未 push 本轮改动）。

### 根因（三条叠加，用户/主代理定位，代码复核确认）

1. **按光标落点提前移交**：路由在事件时刻用"光标 − 抓取偏移"的目标落点算身体中心，
   而弹簧档（`drag_physics`）的实际位移发生在 `sprite.advance` 里——身体还没过缝就被
   换到另一块屏；
2. **单矩形钳制域**：跨缝时身体两边都不完整，任何单矩形域都会在缝上把它钳住；
3. **移交顺序两次钳制**：`set_bounds(新矩形)` 先用**旧局部坐标**补一次钳制，随后
   `set_pos(… − delta)` 又被钳一次。

### 三片改了什么

| 片 | 提交 | 改了什么 | ± |
|---|---|---|---|
| 1 | `9fde6fe` | `PetSprite.set_clamp_rects`：**多矩形合法域**，合法条件 = 身体**逐点落在并集内**（轴对齐网格切分精确判）——跨在缝上合法、屏间空洞不合法（落进去被推到最近那块屏）；`OverlayShell` 派生**相接屏组**（共享正长度边才算相接）、拖拽开始开域、只在"松手后且身体完整落在某块屏可用区内"收窄、拔屏时收回全部开域；路由移到**全部 overlay advance 之后**（`TickDriver.set_post_advance`）只按这一拍的**实际身体位置**判（每 tick 每只一次），移交判据 = 身体完整落在另一块屏可用区内（含边界）；移交改**原子换帧**（域与位置同一个 delta、中间不经单矩形钳制，`old_origin + pos == new_origin + pos`，弹簧目标/轨迹/速度只换表示） | `+151/−14` |
| 2 | `9307459` | 松手后不被控制器拽回：`sprite_behavior` 对开域 sprite 不再按本屏 bounds 硬钳；`sprite_physics._effective_bounds` 让跨屏过渡的 sprite 用它自己域里最近那块屏做反弹/落地边界（不新增"抛掷能跨屏"能力） | `+35/−6` |
| 3 | `39d1cdf` | `OverlayWindow` 跨屏**只读投影**（`set_projection`/`clear_projection`/`projection_rect` + paintEvent 平移重画）；`OverlayShell._sync_seam_projections` 每 tick 收尾按"身体越过本屏几何边界且与邻屏几何相交"登记/摘除并映射脏区；`_reap_empty_hosts` 保留有投影的窗 | `+104/−5` |

新增测试：`tests/test_overlay_seam_passage.py` **14 例**（第 1 片 7、第 2 片 4、第 3 片 3），
逐条先红后绿：撤"临时合法域/实际位置路由/原子换帧"分别打红对应用例；撤行为侧豁免
打红"松手不被拽回"；撤投影打红"跨缝完整可见 + 邻窗保留"两例。

判据覆盖（用户点名的清单）：光标大跳无 tick 不提前移交且弹簧档实际位置不变；
逐 tick 全局轨迹 == 同一块大屏（无内缝）参考轨迹（逐位 `abs=0.001`）；移交原子全局恒等；
释放/右键弹弓冻结与恢复不跳、域不被清；投影拼接像素按身体框采样覆盖 >60%（且证明邻窗
只画投影、不持有 sprite）；左右/上下（含负坐标）真相接可通行、角点相接与屏间空洞不通行；
开关关着不投影不建窗。

### 复现日志（**更正第二轮的口径混淆**）

第二轮报告把两组不同配置的数字挂在同一份日志上，那是错的。四份日志现在是四个明确的配置：

| 日志 | 配置 | 跨屏那一帧 |
|---|---|---|
| `probe_drag_cross-midstart-prefix.log` | 屏中段起拖、修前（消融态） | 840.5 → **2357.5（+1517）** |
| `probe_drag_cross-midstart-postfix-prefixbatch.log` | 同上、第二轮"只换坐标系"之后 | 840.5 → **2009.1（+1169）** ← 第二轮引用的就是这组 |
| `probe_drag_cross-cornerstart-midfix.log` | **贴边**起拖（旧 `-r2` 那份） | 1459 → 1923（+464，钳制主导） |
| `probe_drag_cross-midstart-batch1.log` | 同上中段配置、第一片之后 | 840.5 → 1019.6 → 1292.0（**逐拍平滑，无跳**） |

### 门（第三轮）

- `ruff check pet/ tests/`：通过。
- 全量：**7854 passed / 15 skipped / 0 failed**（24:06，`EXIT=0`，
  `.scratch/per-pet-multiscreen/full-suite-r3.log`）。
- 受影响族（17 个文件，含跨屏/宿主/屏迁移/壳事件/物理/驱动器）：**276 passed**；
  覆盖面更宽的那一族（15 个文件）**3 连跑各 198 passed**（29.3s / 43.5s / 27.9s，
  `.scratch/per-pet-multiscreen/family-rerun-r3.log`）。
- 每片各跑过 focused 与逐步消融（撤任一片即打红对应用例）。

### 仍未验 / 已知代价

- **真双屏未验**（本机只有 1 块活动屏）：跨缝的实机观感、混合 DPI、错位拼接（负坐标）
  仍只有假屏 + 真鼠标事件 + 离屏拼接像素证据；投影的**每 tick 区域 update** 在真机上的
  合成代价未测（区域 = 跨缝那只在本窗的外接矩形，过渡期才有）。
- 本轮**未 push**（避免反复触发 CI）；PR 仍是 Draft，正文需要随本轮结果更新。

## 第四轮 —— CI 稳定化 + 合并 287（2026-10-16 夜）

> 基线：`1d10049`（三片之后仅一笔文档同步）+ 门禁结果 run `38913906551`。
> **口径**：本轮的 macOS 那条是**测试断言过严的稳定化**，不是"产品故障修好了"；
> 产品的 20ms 采样一行未动。Ubuntu 那条（原生崩溃）**未修、根因未定**，本轮只再观察一次。

### 1）macOS 判红 = 断言过严（已修，产品零改动）

- 现象：run `38913906551` 的 `test (macos-latest)` 唯一红为
  `tests/test_now_playing_session_probe.py::test_os_request_happens_on_probe_thread_not_the_caller`，
  断言 `records == ["smtc-session-probe"]` 实际拿到**两条记录，且两条都来自探针线程**。
- 为什么是测试过严：等待窗口的判据是"第一条记录出现"（`_wait_until(lambda: records)`），
  而产品采样间隔 `SESSION_PROBE_TTL_SECONDS = 20 ms`。本机实测（
  `.scratch/per-pet-multiscreen/probe_sampling_cadence.log`，脚本 `probe_sampling_cadence.py`）：
  首条记录 `+34.6 ms`、第二条 `+65.0 ms`，线程集合 `{'smtc-session-probe'}`——首条记录出现后
  主线程只要被调度器压住 ~30 ms（CI 慢 runner 的常态），断言时刻看到两条就是**合法采样节奏**，
  不是"调用线程也查了 SMTC"。**产品采样节奏/线程归属不在本轮修改范围。**
- 改动（唯一一处，1 行断言）：`tests/test_now_playing_session_probe.py`
  `assert records == ["smtc-session-probe"]` → `assert set(records) == {"smtc-session-probe"}`
  （= 非空 且 每次采样都来自探针线程），并加注释说明为何不钉次数。
- 判别力（两条消融，均在本机实测打红；插件留在 `.scratch/per-pet-multiscreen/`，不进提交）：
  - `ablation_sync_probe_caller.py`（把 `_ensure_session_probe` 换成"调用线程当场同步采一次"）→
    `AssertionError: 调用线程自己查了 SMTC：['MainThread']`（第 174 行，红）；
  - `ablation_wrong_thread_probe.py`（采样挪到另一个非探针线程）→
    `assert {'wrong-thread-probe'} == {'smtc-session-probe'}`（第 179 行，红）。
- 复跑（**先做修复后做其余工作**，logs 同目录）：探针文件 **20 连跑、0 失败**
  （同时压 12 个 CPU 忙循环，`probe-fix-stress.log`）；相关族 8 个文件 **104 passed**
  （`now_playing`×3 / `music_detect` / `music_sing_grace` / `music_sing_timer` /
  `music_player_detect_refresh` / `overlay_music_sing`）；`ruff check pet/ tests/` 通过。

### 2）Linux 判红 = `test_memory_trim` 原生崩溃（未修，仅再观察一次）

- run `38913906551` 的 `test (ubuntu-latest)` 退出码 **139（SIGSEGV, core dumped）**，
  崩溃时当前线程停在 `tests/test_memory_trim.py:966`
  `test_unsupported_platform_click_reports_instead_of_crashing`；pytest 进程被信号杀死，
  该分片最后只剩 `............................................................`（无 summary）。
- `main` 上有**逐字历史**（同一用例、同一行、同一 pytest 命令、同一 exit 139），
  但**根因未定**——本轮不宣称它与本分支无关，也不把它记成"已修/已排除"。
- 处置按约定：**不扩大 Linux 分片、不改 workflow、不隔离该测试**；只在本次提交触发的新 CI 里
  再观察一次。若再次原生崩溃，下一步取原生证据（`faulthandler`/core + gdb 回溯）。

### 3）合并 287

- 事实核对：`gh pr view 287` → `state = MERGED`（`2026-10-16T14:44:39Z`），
  `origin/main` = `9fb6c1a`（"feat(desktop+android): 4.3.1 气泡档案/edge-tts 门禁/作者账号 + Android 0.2.x 悬浮桌宠"）。
- 操作：`git merge origin/main`（**普通 merge**，未 rebase / reset / force）→ **无冲突**，
  合并提交 `7244a83`。双方条目都在：行数预算仍按实测校准且原因注释保留
  （`WINDOW_PY_LINE_BUDGET = 4671`、`MODERN_SETTINGS_DIALOG_PY_LINE_BUDGET`，
  `tests/test_architecture.py` 182 passed 含两条预算用例）；`docs/INDEX.md` 我方报告（第 143 行）
  与 287 的桌面/Android 三份报告（151–153 行）并存。

### 4）CI 三端结果（head `8b6af7c`，run `38922171615`）

| 平台 | 结果 |
|---|---|
| `macos-latest` | **通过**（探针用例稳定化生效；该平台不再红） |
| `ubuntu-latest` | **通过**（`test_memory_trim` 那条段错误本轮**未复现**——一次观察，不代表已稳定） |
| `windows-latest` | **失败**：`tests/test_overlay_hosts_multiscreen.py::test_drag_across_screens_transfers_only_the_dragged_pet`（**本刀自己的用例**） |

**Windows 那条的根因与处置（同样是测试稳定化，产品未改）**：

- 断言：拖拽跨屏期间"子宠的全局位置变化 ≤ 24px"（原注释假设子宠只会自己走动、约 1px/拍）。
  CI 实测子宠移动了 `(29.3, −74.6)`；本机复现（单条用例 40 连跑 1 次红）。
- 对照实验（本机，60 次 × 16 拍，脚本 `zz_diag_child_drift.py`，临时文件已删）：

  | 配置 | 子宠总位移 |
  |---|---|
  | 不碰主宠 / 只按下 / 拖但**不跨屏** | **0.00px（60/60）** |
  | 跨屏拖拽，子宠坐在主宠被拖的通道上 | 14.34 – 90px（跨缝后第 2 拍开始，局部坐标与窗口原点分开核对：**窗口原点没动，动的是 sprite 自己**） |
  | 跨屏拖拽，子宠挪到远处（局部 (1480, 200)） | **0.00px（60/60）** |

  即：位移是**接触弹开**，不是坐标混源（窗口原点全程恒为 B 的 `(1920,0)`，没有整屏量级的跳变），
  而"拖鱼撞鱼会被撞开"是本项目**既有且正确**的行为，自带回归
  `tests/test_drag_collision_velocity.py::test_dragged_sprite_knocks_stationary_sprite`。
- 是否与合并 287 有关：**无关**。同一个对照实验在合并前的 `1d10049`
  （`git worktree` 临时检出，已删）逐拍数字**完全一致**（第 10 拍同样 14.34px、60 次同样 max 21.52px）。
- 处置（1 处测试夹具改动，产品零改动）：把子宠落点从主宠被拖的通道
  （全局 `(2200, 700)`）挪到 B 的右侧远处（全局 `(3400, 200)`），**读回容差 `abs=24.0` 不变**。
  这样位置断言恢复它本来的判别力——消融"移交时顺手把别的宠也挪 30px"
  （插件 `ablation_transfer_drags_bystander.py`）仍立刻红：`子宠被这次移交带动了 (30.0, 0.0)`。
- 复跑：该用例 **40 连跑 0 失败**；多屏/overlay 族 8 文件 **141 passed**；`ruff` 通过。

### 5）门（第四轮）

- `ruff check pet/ tests/`：**All checks passed**（`ruff-r4.log`）。
- **合并后累计全量**（本机，合并提交 `7244a83`）：
  `QT_QPA_PLATFORM=offscreen python -m pytest -q` → **7903 passed / 14 skipped / 0 failed**（23:53，`EXIT=0`，
  `.scratch/per-pet-multiscreen/full-suite-merge-r4.log`）。相对 r3 的 7854/15 是 287 带入的新测试
  （净增 49 通过、1 条跳过项随平台条件变化），**无失败**。
- 双方都动过的交互面（`pet/` 重叠 13 个文件：`config.py`、`modern_settings_dialog.py`、
  `overlay_shell.py`、`overlay_window.py`、`pet_sprite.py`、`screen_host.py`、
  `settings_default_marks.py`、`settings_page_guide.py`、`settings_pet_controls.py`、
  `sprite_behavior.py`、`sprite_physics.py`、`sprite_sound.py`、`tick_driver.py`）另跑了一条
  设置/精灵/驱动器子集：**276 passed**（2:08）。
- bridge 零依赖门（CI 同口径）：`node --test` 8 个契约文件 **44 passed / 0 fail** +
  `verify_import.mjs` OK。
- PR 状态：仍 **Draft**，不合并、不 tag、不 release。
- push 账目：本轮共 **2 次**普通 push——第 1 次（`8b6af7c`）触发 run `38922171615`，
  三端结果见上文第 4 节（Windows 红在本刀自己的用例）；第 2 次（`26cd835`）带 Windows 那条
  测试稳定化再触发一次三端 CI。除这两次外未再 push，也未重跑/隔离任何用例。

### 仍未验（第四轮不改变）

- **真双屏未验**（本机 Qt 只枚举到 1 块活动屏）：跨缝手感、混合 DPI、错位拼接仍只有逻辑证据。
- Ubuntu 原生崩溃只在 `38922171615` 里**未复现一次**，属**未解决**项（见上文 2）；
  本轮不作"已稳定"结论，也不因此改 workflow / 隔离测试。
- 被拖宠物把旁边宠物撞开的**幅度**在 CI 上比本机大（本机 14–90px，CI 见到 ~80px），
  原因未逐项查清（不排除平台差异/拖拽动力学差异）；本刀只把用例的判据挪出这条通道，
  没有改产品行为。
