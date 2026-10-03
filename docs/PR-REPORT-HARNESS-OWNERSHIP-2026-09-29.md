# node 桥门控收紧与退出归属收口（K1 + K2）（2026-09-29）

> **基线**：`ebf971e`（fix(collision): 拖拽成员速度通道）+ 工作树未提交 WIP
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-29
> **范围**：2 个产品文件 + 2 个测试文件（1 个新增）
> **关联**：`.scratch/windows-parity-20260926-a/fix-20260929-K1K2/REPORT.md`、
> `.scratch/overnight-20260929/MORNING-REPORT.md`（「待你拍板」第 1 条）、
> `docs/ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md`（关机窗口派生进程纪律）

## 一、核心特性

过夜取证量出了一笔常驻账：**`node.exe` 联动桥 41.9MB，桌宠退出后不收口**。两个缺口：

| # | 缺口 | 语义 | 修法 |
|---|---|---|---|
| K1 | 自动拉起门控**太宽** | 只看 `enable_chat and harness_autostart` → `agent_link.dsh` 没开（桥接插件没装、`DshMonitor` 不跑、`DshStateTracker` 停表）也拉起 41.9MB node.exe | 门控改为 `enable_chat and config["harness_autostart"] and self._dsh_tracker_wanted()`；联动关 → **立即停** |
| K2 | 退出**无收口** | `_on_about_to_quit` 没有任何 harness 调用；`_spawn` 用 `CREATE_NO_WINDOW`，父死子不死 → 桌宠退出后 node 仍活着 | 新增自拉起 pid 登记表 + `stop_self_launched_harness()`：**三重条件**才杀（登记表命中 + 进程存活 + 终止前**重读命令行**过 `_looks_like_harness`） |

**红线 / 不变量**：
- **用户手动起的实例永不误杀**：`dsh web` 手动起的进程不在登记表里 → 收口永远碰不到它。
- **手动菜单不受门控**：门只装在 `_maybe_autostart_harness`；`launch_harness` / `launch_harness_gui` 未改
  （用户明示要开就开，有测试钉住）。
- **关机/注销窗口不动**：`_session_end_done` 为真时整段跳过——issue #111 纪律是关机窗口不再派生进程，
  `taskkill`/`Get-CimInstance` 同样是派生且无收益。
- `enable_chat` 与 `harness_autostart` 仍是**前置条件**（不是被替代）：无 Chat 的变体连 Harness 菜单都不显示。

## 二、修改文件说明

> 归因依据 = 证据报告逐函数记录的改动范围；`pet/app.py` 是**累计** diff（同文件还含更早的 WIP），
> 本批在该文件里是「4 处新增，共 +55/−1」，**不把累计数算作本批**。

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/harness_launcher.py` | +86 / −3 | **K2 主体**：新增 `_SELF_LAUNCHED_PIDS` + `_record_self_launched` / `_forget_self_launched`（自拉起 pid 登记表）；`_spawn` 起成功后登记 `proc.pid`；新增 `stop_self_launched_harness()`（三重条件，返回被终止的 pid）；`_looks_like_harness(..., image_hints=...)` 新增参数 + `_SELF_LAUNCHED_IMAGE_HINTS`（比反查路径多认 `cmd`，理由见下）；**按端口反查路径行为不变** |
| `pet/app.py` | 累计 +324 / −31；**本批 +55 / −1**（4 处） | **K1 + K2 接线**：① 新增 `_harness_autostart_wanted()`（门控表达式）；② `_maybe_autostart_harness()` 改调该门；③ 新增 `_stop_self_launched_harness()`（薄转发 + 异常隔离）；④ `_apply_external_config_change()`：跟踪器停表后，门关 → 停自拉起 harness；⑤ `_on_about_to_quit()`：跟踪器收口后，`_session_end_done` 为假才执行收口 |

### 测试

| 文件 | 增删 / 行数 | 覆盖 |
|---|---|---|
| `tests/test_harness_ownership.py` | 新增 327 行（未跟踪） | 19 条：门控四组合、手动菜单不受门影响、三重条件收口、读不到命令行 = 放过、关机窗口跳过、登记表清理 |
| `tests/test_harness_launcher.py` | +23 / −11 | **改既有用例 1 条**：`test_harness_autostart_hook_gates` 原用 `SimpleNamespace` 桩（会把门一起替掉，等于没测门），改为真 `Config` + `AppShell.__new__`，并补 `dsh_link=False` 那条断言 |

### 未改动（故意）

`pet/modern_settings_dialog.py`（设置项文案**未同步**——见「已知限制」第 3 条）、
`pet/session_watcher.py`（关机窗口语义，本批零改动）、`pet/config.py`（**未新增配置键**）。

## 三、实现要点

- **门控表达式为什么复用 `_dsh_tracker_wanted()` 而不就地再读一次 config**：
  `_dsh_tracker_wanted()`（本分支 WIP 新增）已经是「`agent_link.dsh`」的**文档化单一口径**，
  跟踪器按它启停；同一功能门写两份早晚漂移。
- **收口为什么必须重读命令行**：登记表是**进程内**的（重启即空），而 pid 会被复用。
  三重条件里「终止前重新读命令行并确认是 harness」是防误杀的最后一闸；读不到命令行 =
  判定失败 = **放过**（保留登记，下次再判）。
- **为什么自拉起路径要多认 `cmd`（Windows 实测）**：本机 `which("dsh")` 是
  `%APPDATA%\npm\dsh.CMD`，`_wrap_cmd` 把它包成 `cmd.exe /c …\dsh.CMD web`，
  于是**直接子进程镜像是 cmd.exe**（真正监听的 node 是它的子进程）。
  只认 node/dsh 会让收口在主力平台上**静默失效**，故自拉起路径放宽到 `("node","dsh","cmd")`；
  按端口反查路径仍只认 node/dsh。
- **「联动关 → 立即停」是一个产品选择**：理由是这条服务的唯一消费者就是 DSH 联动管线；
  但 `harness_autostart` 单开关关闭**不**停（那是「以后不要自启」，不是「现在停掉」）。
  用户拍板的语义：**正在用桌宠自拉起的页面时退出桌宠会断服务**。

## 四、性能分析

**方法（可复现）**：证据目录 `fix-20260929-K1K2/green-after.txt` §7 的三段计时脚本
（本机 3 次采样；`process_command_line` = PowerShell `Get-CimInstance` 取命令行）：

```bash
.venv/Scripts/python.exe -c "…hl.process_command_line(os.getpid()) 计时…"
# sample0: 0.694s  cmdline_len=578
# sample1: 0.643s  cmdline_len=578
# sample2: 0.664s  cmdline_len=578
# is_running_pid: True 0.0097s
# stop_self_launched_harness(空表): [] 0.000003s
```

环境：Windows / `.venv` Python 3.13.7；本机 `dsh` 经 `%APPDATA%\npm\dsh.CMD` 安装（**本次补报告复核过：`which dsh` → `/c/Users/me/AppData/Roaming/npm/dsh`**）。

| 指标 | 实测 | 归属 |
|---|---|---|
| 收口·空表（最常见：联动关 / 本进程没拉过） | **3 µs**、**0 次系统调用** | 新增路径 |
| 收口·有自拉起实例 | `process_command_line` **0.694 / 0.643 / 0.664 s**（热机 3 次）+ `taskkill`（Windows 分支无轮询）≈ **合计 0.7–1.0 s** | 新增路径 |
| 存活探测 | `is_running_pid` **0.0097 s** | 新增路径 |
| 省下的常驻内存 | `node.exe` **41.9 MB**（过夜取值的归属项） | 稳态 |

**结论（逐条回答模板四问）**

1. **稳态开销**：**只在门变窄这一侧变化**——联动不开时，整条 node.exe（41.9MB + 一个常驻进程）
   不再被拉起；开着的场景稳态零变化（收口不在 tick/热路径上）。
2. **新增路径的绝对成本与触发频率**：收口只发生在**两条用户主动路径**——正常退出、联动关闭；
   空表时 3µs/0 系统调用，有实例时 0.7–1.0s（一次性，且发生在退出期，不影响交互帧）。
   运行期新增路径 **0 条**。
3. **新系统调用 / 网络 / 磁盘 / 线程**：无网络、无磁盘、无新线程；
   `Get-CimInstance`（PowerShell）与 `taskkill` 是**退出期**的两次派生。
4. **内存与缓存增长**：登记表是进程内一个 `set[int]`（每自拉起实例一条），
   无新增长寿命缓存。**本次未做进程外 RSS 前后采样**（41.9MB 来自过夜取证归属）。

## 五、实机运行记录

1. **Windows 平台实测（本批的关键前提，本次补报告复核）**：
   `which dsh` → `/c/Users/me/AppData/Roaming/npm/dsh`，且 `%APPDATA%\npm\dsh.CMD` 确实存在
   （`ls` 输出 `dsh.CMD` 342 字节、09-16 落盘）。这条支撑了「直接子进程镜像是 cmd.exe，
   所以自拉起路径必须多认 cmd」——若只认 node/dsh，收口在本机主力形态下**静默失效**。
2. **OS 边界成本实测（真机）**：上表三段计时脚本在本机真跑（`process_command_line` 走
   PowerShell `Get-CimInstance`，0.64–0.69s；`taskkill` 在 Windows 分支无轮询）。
3. **未实机验证（明确登记）**：证据报告写明「**全程零 git 写操作、未构建、未起桌宠**」（全量 pytest 与实机端到端均已于后续修正轮补齐，见下方「第二轮修正」「第三轮修正」）。
   因此以下三条**没有端到端实机记录**：
   - 桌宠**退出时真的杀掉**自己拉起的 node（需要有活实例的真实退出）；
   - 联动关时**不再拉起** node（需要真机启动 + 观察进程树）；
   - 手动起的 `dsh web` 在收口时不被动（三重条件已由 19 条用例覆盖，但那是 mock/桩级）。
4. **部署时间序（本批之后确实出包了，但不是字节级验证）**：`D:/dsh-pet/dsh-pet-standalone-webm-chat.exe`
   mtime **09-29 15:52**、部署进程 PID **39276**（`CreationDate 2026/9/29 16:06:51`，`--slot 0`）——
   晚于本批收口时间（08:25）。**注意**：PyInstaller 把 `pet/**` 编进 PYZ，包内无 `.pyc` 可直接比对，
   故「部署包里的 `harness_launcher.py` 就是本批版本」只经时间序推断。
5. **无法自动验证的能力**：关机/注销窗口的行为（`WM_QUERYENDSESSION` 路径需要真机关机，
   且按设计本批**不改**该路径）；用户正用着页面的退出体验（产品选择，非技术验证项）。

## 六、测试与验证

| 门 | 命令 | 红（改前） | 绿（改后） |
|---|---|---|---|
| 新增测试首次运行 | `pytest -q -p no:cacheprovider tests/test_harness_ownership.py` | **19 errors**（`AttributeError: module 'pet.harness_launcher' has no attribute '_SELF_LAUNCHED_PIDS'`，seam 不存在） | **19 passed**（5.26s） |
| K2 落地后门控 | 同上范围 | 真跑出多余拉起（`1 failed, 7 deselected`）+ 基线导出无任何收口代码的静态证据 | 绿 |
| harness 三文件 | `pytest -q tests/test_harness_launcher.py tests/test_harness_lifecycle.py tests/test_harness_ownership.py` | — | **67 passed**（11.22s） |
| 验收聚焦 | `pytest tests/ -k 'harness or agent_link or app_shell or about_to_quit or feature_gating' -q -p no:cacheprovider` | — | **360 passed, 1 skipped, 3728 deselected**（28.57s，`EXIT=0`） |
| 受影响同族 | `test_background_service_gates / test_feature_gating / test_config_schema` | — | **33 passed**（4.92s） |
| issue #111 守卫 + 桌宠功能族 | `pytest -q tests/test_session_end_ffmpeg_guard.py tests/test_desktop_pet_features.py` | — | **120 passed**（9.98s） |
| ruff | `ruff check --no-cache pet/harness_launcher.py pet/app.py tests/test_harness_ownership.py tests/test_harness_launcher.py` | — | All checks passed |
| 全量（含本批，交接记录） | `QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` | — | **4158 passed**（`.scratch/HANDOFF-20260929.md:7`，**本次未复跑**）；**2026-10-01 已复跑：4187 passed / 0 failed** |
| **本批新用例（本次补报告现场复跑）** | 11 个批次测试文件合并跑（命令全文见 [`PR-REPORT-GUI-IDLE-JANK-2026-09-29.md`](PR-REPORT-GUI-IDLE-JANK-2026-09-29.md) §六；含本批 `tests/test_harness_ownership.py`） | — | **110 passed in 8.12s（rc=0）** |
| 交付证据纪律 | `pytest tests/test_pr_report_discipline.py -q` | — | **55 passed**（补报告前基线 43 passed） |

## 七、已知限制与后续

1. **纯 `aboutToQuit` 通知的关机**（无 `WM_QUERYENDSESSION` / `commitDataRequest`）仍会走收口，
   因为 `AppShell` 的 `aboutToQuit` 连接**早于** `session_watcher`（Qt 按连接序调用）。
   Windows 上的权威信号是 `WM_QUERYENDSESSION`，实际影响很小；彻底封死需调整连接顺序
   （`session_watcher.py` / `app.py` 启动序，本批范围外）。
2. **退出会断掉用户正在用的自拉起页面** —— 用户拍板的语义，配置项未加。
3. **设置项描述文案未同步**：`pet/modern_settings_dialog.py:447` 仍写「桌宠启动后自动在后台静默拉起」，
   未提新增的联动前置条件——**需下一批补文案**（本批文件范围外）。
4. **`stop_harness`（菜单停止）不写登记表**：用户手动停掉后表里剩一个死 pid，下次收口自行清理，无副作用。
5. **端到端实机未验**：见「实机运行记录」第 3 条。

## 八、风险与回滚

- **影响面**：桌宠启动期的自启决策、退出期/联动关闭时的进程收口。无配置键变化、无落盘格式变化。
- **回滚**：两个文件可独立回滚（`app.py` 的门控 → 恢复旧表达式；`harness_launcher.py` 的登记表与收口函数
  无外部引用时即为死代码）。回滚后**无残留状态**（登记表是进程内的）。
- **失败模式**：① 误杀（三重条件已把「读不到命令行」判为放过）；② 漏杀（登记表在重启后为空，
  但重启后的实例本来也不该杀别的实例）；③ 门变窄导致「联动开着但用户期望自启」的场景不再自启——
  这是**有意的语义变化**（旧口径会拉一个无人消费的服务），已在报告与测试里显式登记。

---

## 第二轮修正（2026-10-01）：审-修-审循环的四缺口与后续发现

> 经多轮独立复核，本批四个实现缺口及后续 14 项问题（12 修复、1 误报、
> 1 明示残余）已全部处置。本节登记最终形态与证据，原报告各节数字以本节为准。

### 修复内容（按缺口）

| # | 缺口 | 修法 | 回归测试 |
|---|---|---|---|
| G1 | `_terminate_process_tree` 对 taskkill 非零只记 warning，失败被记成已终止 | 返回 bool（nt 返回码+128 豁免、posix 送达语义+已死豁免）；收口只在「ok 且句柄确认死亡」才销登记 | `test_stop_self_launched_keeps_pid_when_terminate_fails`、`test_stop_self_launched_keeps_pid_when_target_survives_terminate`、`test_poll_based_confirm_distinguishable_from_pid_probe` |
| G2 | 联动关闭收口在 GUI 线程同步吃 PowerShell 10s+taskkill 15s 阻塞 | daemon 线程收口 + 线程入口门复核（`_stop_harness_if_still_unwanted`）+ `_session_end_done` 窗口不派生 | `test_config_change_stop_harness_runs_off_caller_thread`、`test_async_stop_aborts_when_link_reenabled` |
| G3 | 原进程死后 pid 复用给用户实例 → 命令行复核通过即误杀 | 收口身份门槛加「活体自拉起 Popen 句柄」（`_child_for`）；原进程已死只销登记不下刀 | `test_stop_self_launched_never_kills_pid_after_child_exited` |
| G4 | 自动拉起慢探测期间联动被关 → 关了还在跑 | worker 探测前/拉起前/拉起后三处复核门；`_quitting` 退出标记同源封堵在途 spawn（R2 第五缺口） | `test_autostart_rechecks_gate_before_launch`、`test_autostart_stops_immediately_if_gate_flips_after_launch`、`test_in_flight_autostart_is_reaped_when_quitting`、`test_autostart_never_launches_when_already_quitting`、`test_session_end_gate_also_marks_quitting` |
| R2-锁 | G2 异步化后登记表/子进程列表无锁（双 remove 抛 ValueError 中断收口） | `_OWNERSHIP_LOCK`（RLock）：只锁列表读写瞬间+spawn 双登记同一临界区，慢操作全部锁外 | `test_ownership_registry_writes_are_serialized`（try/finally 释放） |
| R2-桩 | bool 契约打断 `test_harness_lifecycle` 两条存量桩（全量门禁独立复现 2 failed） | 桩补 True 契约；所有终止桩签名随 `proc=None` 参数同步 | 两文件 64 passed |
| R3-posix | `_terminate_process_tree` 内部 POSIX 僵尸空等 3s | 加 `proc` 参数：给出句柄时用 `poll()` 判活顺带 reap | 判别性守卫 |

### 已知限制与明示残余（新增，原 §七 之外）

1. **G2 复核只覆盖「派发→线程入口」**：复核通过后收口的秒级慢操作期间重开联动不在防护内——服务会被停一次且不会自动重拉（自启只在主窗就绪时调度一次），用户可从菜单手动启动（复核发现）。
2. **解释器终结边界的补偿是尽力而为**：daemon 线程在解释器退出时被冻结，第三处检查可能不执行→node 泄漏且下次启动无登记（与本报告原有「漏杀」失败模式同源）。
3. **cmd 先死 node 孤儿**：按「非我所有不杀」放过，端口确认路径（`stop_harness`，有用户确认）兜底。
4. 强杀桌宠后自拉起的 node 需手动结束（设计取舍：误杀方向一次都不许发生）。

### 验证（第二轮，全部本机实测）

- 聚焦：`tests/test_harness_ownership.py`（31）+ `tests/test_harness_lifecycle.py`（33）= **64 passed**；
  harness 三文件 **77 passed**；聚焦族 `-k 'harness or agent_link or app_shell or about_to_quit or feature_gating'` **372 passed / 1 skipped / 0 failed**（ds 独立复跑复核）
- 全量：`QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` = **4183 passed / 11 skipped / 0 failed**（修正轮批后快照）**；随后最终全量 = 4185 passed / 11 skipped / 0 failed**（510s 快照，最终以「第三轮修正」为准）
- ruff：All checks passed（四文件）
- 受影响时序族满载 3 遍（与全量门禁并行的高负载条件）：**374 passed / 1 skipped / 0 failed × 3**（24.8s/24.6s/24.4s）
- **新线程**：`pet-harness-stop`（daemon，联动关闭收口）；**无新系统调用/网络/磁盘**（taskkill/PowerShell 为既有路径）
- 复核留档：`.scratch/pr-review/`（各轮复核简报与意见全文、核验记录）

---

## 第三轮修正（2026-10-01 终审后）：会话结束分流、取消闸与单飞

> 终审复核在成品上再发现三组问题，
> 已全部修复并回归。本节登记终审修复与**本批第一份实机端到端记录**。

### 终审发现与处置

| # | 发现 | 修法 | 回归 |
|---|---|---|---|
| C2 | SessionWatcher 把 aboutToQuit 兜底也汇进 `_on_session_end` → `_session_end_done` 语义污染（正常退出被当会话结束，三处收口误跳过） | `_on_about_to_quit` 先行置 `_plain_about_to_quit`（Qt 按连接序调槽）；`_on_session_end` 只在**真会话结束**（无该标记）时置 `_session_end_done` | `test_session_end_done_not_set_by_plain_about_to_quit` + `test_session_end_done_set_by_real_session_end` |
| P1-1 | `launch_harness` 慢命令解析（npm 最长 15s）后无退出闸，关机窗口照样 spawn | `launch_harness(cancel_check=...)`：解析后、spawn 前评估；自动拉起传入（`_quitting`/`_session_end_done`），菜单不传（用户明示永远可用） | `test_autostart_aborts_when_quitting_lands_during_probe`（status=aborted 且零 spawn） |
| P1-2 | 并发收口共享过期快照：一方已终止回收，另一方凭旧结果向数字 pid 发信号（POSIX 复用即误杀） | ①`_STOP_INFLIGHT` 单飞合并（后到者返回空表）；②发信号前先查句柄：句柄已死 = 我们的子进程已终止 = 不再发任何信号（全平台身份绑定） | `test_stop_self_launched_single_flight`、`test_terminate_binds_to_child_identity_before_signaling` |

### 实机端到端运行记录（本批第一份，此前为零）

> 口径：本记录是 **launcher 函数级真机启动/收口冒烟**——
> 它经过真实 npm/cmd→node 环境与端口，但**未经过**桌宠应用入口（autostart 门控 /
> 联动关闭异步收口 / aboutToQuit 与 SessionWatcher 分流），不替代应用级端到端。
> 「用户实例零接触」证据 = 登记表不含 38080 + **实机后态**：收口完成后 38080
> 仍在监听（前后对照，2026-10-01 10:0x 复测）。


```
[1] 拉起前探测 38991: 空闲（38080 有用户的 dsh web 在跑，全程未触碰）
[2] launch_harness(port=38991, open_browser=False) → started
[3] 端口监听: True（5s 内就绪）
[4] 登记表: [15528]；用户实例（38080）不在表中: True
[5] stop_self_launched_harness() → terminated [15528]
[6] 收口后端口消失: True
RESULT: PASS（2026-10-01 05:4x，本机真 dsh/npm/cmd→node 两层）
```

证实了桩件的三条核心前提在真实 OS 上成立：CREATE_NO_WINDOW 子进程可起、
登记表只认自拉起（用户实例零接触）、收口能终止 node 且端口释放。
桩件无法覆盖的残余假设仍以 §二轮-已知限制为准。
**原始输出留档**：`.scratch/pr-review/e2e-harness-38991.log`（2026-10-01 第二次复跑
全程 stdout：空闲→started→listening→登记[460]→terminated[460]→端口消失→RESULT: PASS；
事后旁证：38991 无监听、用户 38080 持续在跑）。

### 已知限制补充（终审新增登记）

5. **`stop_harness`（菜单端口反查路径）在 POSIX 无句柄**：该句柄确认只覆盖
   自拉起收口；菜单路径的 TERM 后等待仍可能空等 3s（不影响正确性，只影响时长）。
6. **收口快照语义**：遍历期间新登记的 pid 本次不可见（漏杀方向，下次收口自愈）。
7. **`_session_end_done` 分流后的确定性残余**：在途拉起成功与主收口跳过之间仍存在
   理论窗口（进程正常退出时已由主收口覆盖；关机/注销时由 OS 回收兜底）。
8. **POSIX 终止确认对象是直接子进程**：组长退出但同组后代忽略 TERM 时，
   KILL 升级与销登记以组长状态为准（常规 dsh 未见触发，登记为边界）。

### 验证（第三轮，全部本机实测）

- 聚焦两文件：**69 passed**（64 + 终审修复 5）；ruff：All checks passed
- 实机端到端：见上（PASS）
- 最终全量门禁：**主套件 4187 passed / 11 skipped / 0 failed**（504s）+ `test_frameseq_prefetch_watchdog.py`（5 条）按族先例独立跑 ×3 全绿（合计 4192）；时序族高负载 374×3 绿
