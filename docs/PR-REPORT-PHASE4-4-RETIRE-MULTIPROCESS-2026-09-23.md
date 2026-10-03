# PR 报告：Phase 4.4a/4.4b 多进程多宠退役层（停用 → 删除）

- 分支：`feature/single-overlay-window`
- 提交一（4.4a 停用）：`acf00f5 refactor(app): 4.4a 停用多进程多宠退役层——新路径零引用收口`（23 文件，+441/−2796）
- 提交二（4.4b 删除）：`refactor(app): 4.4b 删除多进程多宠退役层——机器化守卫锁定`
- 权威清单：`.scratch/single-overlay-window/PHASE4_DESIGN.md` §3 T5/T6、§10（v1.1 注释清理项）、§12（v1.3）
- 机器化守卫：`tests/test_architecture.py::test_retired_multiprocess_layer_files_are_gone`、
  `::test_pet_tree_has_zero_retired_layer_imports`、
  `::test_overlay_new_path_has_zero_retired_layer_imports`

**范围**：退役对象只有「多进程多宠层」（跨进程碰撞 IPC / slot 文件锁 / 进程孵化 /
子宠 taskkill 清理 / runtime 标记的活消费侧）。`PET_RENDER_TOPOLOGY=legacy`
（PetWindow 渲染面）**永久保留**并可启动；`is_overlay_topology` 默认值未动；
`--slot` / `DSH_PET_SPAWN_OFFSET_INDEX` 兼容解析保留；`island_collision` 的 clamp
数学未改（以静态成员钩子形态重生，见 T6 表）。

## T6 逐条处置结果

| T6 条目 | 4.4a | 4.4b | 结论 |
|---|---|---|---|
| `collision_ipc.py` | 新路径零 import（grep 复核）；`PetInstance.collision_ipc` / `CollisionIpcSession` 全部摘除（app.py 建/启/停、island 发布通道、switch_character 重建链） | 文件删除 + 两个守卫断言 | 已退役 |
| `collision_codec.py` | 仅被 `collision_ipc`/`collision_client` 使用，随使用侧一并停用 | 文件删除；`test_architecture` 零 Qt 清单移除该项；`tests/test_collision.py` 帧编解码/水位去重两族（161 行）删除 | 已退役 |
| `collision_client.py` | D9 业务链（squash/throw_egg/edge_probe/碰撞音效/预测反弹）在 sprite 世界均已落地 → 满足 T6「否则只停不删」的前置；窗口侧 `CollisionClient` 组合、委托 property 块、`_submit_collision_state` 14 处调用、`_predict_collision_bounce` 全部摘除；撞岛「落地重进探头」arm 改为窗口本体标记 | 文件删除 | 已退役（前置条件成立） |
| `collision_debug.py` | 唯一消费者是 `collision_client`/`collision_ipc` | 随消费者一并删除（否则成为零引用死文件） | 已退役（超出清单但必要） |
| `instance_launcher.py` | `launch_new_pet` 停用：`spawn_pet` 统一走进程内新窗；`--slot` / `DSH_PET_SPAWN_OFFSET_INDEX` 解析保留（T5） | 文件删除 + `test_desktop_pet_features` 两条孵化用例删除 | 已退役 |
| `slot_manager.py` 锁/PID 部分 | `main()` 不抢锁（T5 明示）；`spawn_in_process_window` 改用 D6 无锁分配器；`slot_handle` 全链摘除 | 删除 `acquire_pet_slot`/`acquire_file_lock`/`release_file_lock`/`get_slot_lock_path`/`_try_acquire_slot_lock`/`_try_lock_file`/`_unlock_file`/定长 PID 记录/`SlotLockError`/`SlotManagerError`/`msvcrt`/`fcntl`；`migrate_legacy_spawns` 与 `_recover_migration_staging` 去掉锁竞争（落位判定改「目标是否已存在」） | 已退役（锁面） |
| `slot_manager.py` 保留项 | — | `backup_corrupt_config` / `seed_slot_config_from_main` / `get_config_path_for_slot` / `get_sessions_dir_for_slot` / `migrate_legacy_spawns` / `slot_to_instance_id` **保留**，与 T6 一致 | 保留（T6 要求） |
| `window_placement.py:20` 模块级 import | — | slot_manager 改为「保留面」重写（不含锁面），模块级 import 无需再拆分；`runtime_marker_versioned()` 由 flag 快照改为恒 True | 处置完成 |
| `child_pet_cleanup.py` | `AppShell.clear_spawned_pets` 去掉文件级 taskkill 清扫；设置进程回退消费者改走 D12 指令通道，并在 legacy `AppShell` 补上 D12 消费者（`_consume_settings_command` + 目录 watcher/3s 轮询挂点） | 文件删除 + `tests/test_child_pet_cleanup.py` 删除 | 已退役 |
| runtime markers 活消费 | — | **改判：保留**。核实 D7 通道的落地形态就是 runtime marker 本身（`overlay_shell._sync_runtime_marker` 写 → `settings_standalone.standalone_pet_geometry` 读），并无独立替代文件；删除会让独立设置进程失去避让定位。marker API 与 `pid_alive`/`read_live_instances` 全部保留 | 保留（D7 通道本体） |
| 岛远端墙通道（island_collision publish/remote） | `attach_publisher`/`detach_publisher`/`_publish_static_state`/`on_remote_snapshot`/`_remote_*`/`_pub_*`/TTL 常量全部删除，只留本进程直连硬墙 + `_apply_hit` 业务链 | — | 已退役 |
| island_collision clamp 数学重生 | 核实：`sprite_collision.capsule_circles`（体育场/胶囊等效圆链）+ `add_static_member`，由 `island_bridge.py:207` 装配 | — | 已确认（未改 clamp 数学） |
| `experimental_single_process_spawn` 键 | 键仍被读取（只参与 hub/共享子系统门控），行为不变 | schema 删除（defaults / reload 白名单 / 归一化）；`tests/test_config_schema.py` 快照去掉该键；`tests/test_spawn_toggle_hidden.py` 整篇删除；`_single_process_spawn` 快照删除，依赖面常开化：共享子系统恒建、hub 门收敛为用户级 `experimental_shared_decode`、runtime marker 恒版本化、窗级「退出这只」恒注入、日志槽位按活窗数派生、全屏监视由共享 watcher 接管（`shared_fullscreen_watcher_active`，测试自建宿主仍走旧路径） | 已退役 |
| `multi_window_shared.py` | — | 不删、**常开化**（`AppShell.__init__` 恒建）；`instances[].win` 遍历的 sprite 等价物已在 4.3 后半落地并核实：`presentation_targets(shell)` 在 overlay 拓扑返回 `[OverlayShell]`（`pet/multi_window_shared.py:43-59`） | 保留 + 常开 |
| §10 注释清理（`click_sound.py:850`、`dsh_state.py:45`、`win_job.py:19`、`harness_launcher.py:378/603/658`） | — | 全部同批改写为不依赖已删模块的自洽表述 | 已清理 |
| §10 文档项 | — | `AGENTS.md` 拓扑/守卫说明重写（CollisionIpcSession 图与 IPC 段落删除，改为 overlay/legacy 双拓扑 + 退役层守卫）；`README.md` 模块树同步；`docs/WINDOW_PY_SPLIT_GUIDE.md` 表格与范例段同步；`docs/INDEX.md` 修正「ISSUE-42 指针缺失」注记（该指针已随退役删除） | 已清理 |

## 修改文件说明

### 提交一 4.4a（`acf00f5`，23 文件，+441/−2796）

| 文件 | 改了什么 + 为什么 | 增/删行 |
|---|---|---|
| `pet/app.py` | `main()` 不抢 slot 锁（T5）、`--slot` 兼容解析保留并只用于选身份；`spawn_pet` 统一走进程内新窗；`spawn_in_process_window` 改 D6 无锁分配；`PetInstance` 去掉 `slot_handle` 与 `collision_ipc`；`clear_spawned_pets` 去掉文件级 taskkill 清扫；`_on_window_exit_requested`/`_on_about_to_quit` 去掉 slot 解锁与碰撞会话停止；新增 legacy D12 指令消费者；island 发布通道摘除 | +98/−188 |
| `pet/window.py` | 删除 `CollisionClient` 组合与全部碰撞委托 property、`attach/detach_collision_session`、`_submit_collision_state` 及 14 处调用、`_predict_collision_bounce`；`detach_decode_sessions` 承接解码 broker 收尾；`_stop_physics` 承接「撞飞落地→边缘探头重进」arm | +20/−161 |
| `pet/island_collision.py` | 删除跨进程发布/远端墙全部代码，保留同步硬墙 + `_apply_hit` 业务链；arm 写到窗口本体 | +10/−180 |
| `pet/window_optional_services.py` | 会话结束收尾改调 `detach_decode_sessions`（仅解码侧） | +4/−4 |
| `pet/modern_settings_dialog.py` | 「一键退出子肥鱼」统一走 D12 指令通道（legacy 不再 taskkill） | +12/−23 |
| `tests/pet_window_fakes.py` | **新增**：从被删的 `tests/test_collision_window.py` 收编 `FakeClip`/`FakeLibrary`/`make_pet_window`（6 个窗口级测试族共用） | +105 |
| `tests/test_collision_window.py` / `test_collision_settings.py` / `test_island_remote_wall.py` | **删除**：窗口侧碰撞客户端 / 会话绑定 / 远端墙的用例（行为已退役） | −1256 / −186 / −472 |
| `tests/test_single_process_spawn.py` | 去掉 slot 锁句柄/碰撞会话用法与断言，新增「spawn_pet 恒进程内」「无子窗时 clear 为空操作」用例，slot 上限改测 D6 分配器 | +60/−215 |
| `tests/test_architecture.py` | 新增新路径零 import 守卫（按目录枚举 overlay_*/sprite_*/tick_*/pet_sprite/island_bridge） | +47 |
| 其余 13 个测试文件 | 引用改道（`pet_window_fakes`）、D12 语义更新、legacy 门控测试改写、去 slot/session 打桩 | +121/−320 |

### 提交二 4.4b（工作树 39 文件，+326/−1319；另 9 个文件删除见下）

**新增/删除文件**

- 删除 `pet/collision_ipc.py`（−1286）、`pet/collision_codec.py`（−246）、
  `pet/collision_client.py`（−585）、`pet/collision_debug.py`（−34）、
  `pet/instance_launcher.py`（−65）、`pet/child_pet_cleanup.py`（−261）
- 删除 `tests/test_collision_ipc.py`（−1306）、`tests/test_child_pet_cleanup.py`（−361）、
  `tests/test_spawn_toggle_hidden.py`（−70）

> 说明：这 9 个删除与用户并发提交 `5f5e408 chore(overlay): 撤除右键归因临诊日志…`
> 一起入库——制作 4.4b 时这些删除已 `git rm` 暂存，该提交把它们一并带走。
> 未改写用户提交（拒绝改写他人历史）；4.4b 提交承载其余全部删除侧改动与守卫。

| 文件 | 改了什么 + 为什么 | 增/删行 |
|---|---|---|
| `pet/slot_manager.py` | 重写为「保留面」：删锁/PID 记录/锁异常/`msvcrt`+`fcntl`；`migrate_legacy_spawns` 探活改用 `pid_alive`，落位判定改「目标是否已存在」；runtime 标记 API 保留（D7 通道） | +38/−243 |
| `pet/app.py` | 删 `_single_process_spawn` 快照；hub 门收敛为 `experimental_shared_decode`；共享子系统恒建；窗级「退出这只」恒注入；日志槽位按活窗数派生 | +38/−56 |
| `pet/config.py` | 删 `experimental_single_process_spawn`（defaults / reload 白名单 / 归一化） | +3/−9 |
| `pet/window.py` | 去掉 `single_process_spawn` 构造参数与字段，新增 `shared_fullscreen_watcher_active` | +5/−5 |
| `pet/window_screen.py` | 全屏监视改由共享 watcher 接管（标记缺席时保留自建路径） | +7/−2 |
| `pet/window_placement.py` | `runtime_marker_versioned()` 恒 True（同 pid 多窗必需） | +8/−2 |
| `pet/decode_fanout.py` / `pet/multi_window_shared.py` / `pet/overlay_spawn_state.py` / `pet/overlay_settings_command.py` / `pet/__main__.py` | 文档串/注释与键删除同步（无行为改动） | +3~7 each |
| `pet/collision.py` / `sprite_collision.py` / `island_collision.py` | 删除对已删模块的活引用式注释，保留 clamp/阈值口径说明 | +2~8 each |
| `pet/click_sound.py` / `dsh_state.py` / `win_job.py` / `harness_launcher.py` / `modern_settings_dialog.py` | §10 注释清理 | +1~4 each |
| `tests/test_architecture.py` | 新增「退役层文件不存在」「全 pet/ 树零 import」两条机器化守卫；零 Qt 清单去掉 `collision_codec.py` | +38/−5 |
| `tests/test_slot_and_memory.py` | 删除锁竞争/锁文件格式/PID 记录/占用跳过共 13 个用例（−430），保留落种/损坏备份/迁移/标记 API/`--slot` 校验 | 0/−430 |
| `tests/test_single_process_spawn.py` | 去 flag 键与快照断言、删「两窗 runtime_id 互不为 peer-self」与「flag 关写旧名标记」用例、标记名改版本化 | +30/−158 |
| `tests/test_single_process_shared.py` | 删「flag 关不实例化共享子系统」对照；helper/用例改名（flag 开 → 无条件共享） | +20/−35 |
| `tests/test_overlay_shell.py` | D0 门控用例改为「hub/共享恒开 + 用户级总闸生效 + legacy 同样常建」 | +20/−20 |
| `tests/test_overlay_instance_gate.py` | slot 锁失败路径用例改为「退役层符号不存在 + 启动失败释放门」，并隔离真实用户配置目录 | +18/−10 |
| 其余测试文件 | `conftest` 去 collision IPC 收口；帧编解码/水位去重用例删除；`instance_launcher`/`child_pet_cleanup` 直测删除；`_stop_live_sessions_for_tests` 引用清理 | +~60/−~260 |
| `AGENTS.md` / `README.md` / `docs/WINDOW_PY_SPLIT_GUIDE.md` | 拓扑与模块清单改写（CollisionIpcSession 图/IPC 段/模块表同步） | +48/−49 |

## 性能分析

环境：Windows 11（win32），Python 3.13.7（`D:\dsh-pet-src\.venv`），
`QT_QPA_PLATFORM=offscreen`。样本：每项各 1 次（对照组 `a4da423` 用同一 venv 的
临时 git worktree 跑，同一脚本 `.scratch/_4b_metrics.py`）。

| 指标 | a4da423（退役前） | 本刀之后 | 变化 |
|---|---|---|---|
| `import pet.app` 墙钟 | 3394.1 ms | 1611.8 ms | **−52%**（少 6 个模块的导入与字节码） |
| `pet.*` 已加载模块数 | 87 | 81 | −6 |
| `tracemalloc` 导入期峰值 | 43828.8 KB | 29944.2 KB | **−32%（−13.6 MB）** |
| 全量套件（本机） | 3389 收集（基线口径） | 3238 passed + 11 skipped，231.94 s（另两轮 237.2 s / 300.4 s） | 收集数 −151（删除的 9 个文件与用例） |

逐条回答：

- **稳态开销**：净减少。删除面 = 跨进程碰撞协调者（每实例一条 `QThread` + `QLocalServer`/`QLocalSocket`
  端点 + 50/500ms 上报定时器 + 2s 岛几何心跳）、slot 文件锁（每次启动一次 `msvcrt.locking`/`flock`）、
  子宠清理（`taskkill` 子进程 + 后台 sweep 线程）。`git grep "QLocalServer\|QLocalSocket" -- pet` 命中 0；
  `pet/` 内已无 `fcntl`/`msvcrt` 锁（残留仅 `proactive_limiter.py` 自己的跨进程频控锁，属另一功能）；
  `taskkill` 仅存于 `harness_launcher.py`（dsh 启动器的独立功能）。
- **新增路径成本**：无新增热路径。`AppShell` 新增一个 D12 指令消费函数，挂在**既有**的 config 目录
  watcher 事件与既有 3s 轮询定时器上（不新起线程、不新增定时器）；单次成本 = 一次
  `path.read_text` + `json.loads`（文件不存在时 `FileNotFoundError` 立即返回）。
- **系统调用/网络/磁盘/线程**：无新增。磁盘面只减不增（少写 slot 锁文件、少写
  子宠清理的 taskkill/标记扫描）；网络面无涉（退役层本来就无网络）。
- **内存增长**：无增长；导入路径少加载 6 个模块（实测 −13.6 MB tracemalloc 峰值）。
  运行期每实例少一条 `QThread` 与两个定时器（结构性删除，未单独做稳态 RSS 采样——
  见「未完成项」）。
- **测试面**：守卫使「回潮」变成机器可判：退役模块文件复活、或任何 `pet/` 模块
  （含函数级延迟 import）再次 import 它们，`test_architecture.py` 立刻红。

## 实机运行记录

环境：本机 Windows（非 CI、非 mock），`QT_QPA_PLATFORM=offscreen`，`APPDATA`/`LOCALAPPDATA`
指向临时目录（**不触碰真实用户配置**），脚本 `.scratch/_4b_smoke.py`。

```
===== topology=legacy(no env) -> ALIVE_AT_TIMEOUT
（20s 超时点仍存活；无 ImportError/ModuleNotFoundError）
===== topology=overlay -> ALIVE_AT_TIMEOUT
（20s 超时点仍存活；输出为空 = 零 traceback）
```

- **硬约束 1（legacy 必须仍能启动）**：`python -m pet`（无 env）真进程启动并稳定存活到
  超时点；进程内不再 import 任何退役模块（`test_pet_tree_has_zero_retired_layer_imports` 同时守卫）。
- **hub 常开化是否引入 legacy 回归**：对照跑 `experimental_shared_decode=false`（旧 flag-off 形态）
  与默认（hub 开），同一条既存报错在两边的命中数分别为 484 / 546 次 —— 与 hub 无关。
- **已知既存缺陷（非本刀引入）**：`pet/frameseq_clip.py:239` 的
  `decode_throttle_divisor` / `decode_pace_external` 是**普通方法**（`webm_clip.py:1436` 是 property），
  而 `window.py:2646`/`decode_fanout.py:329` 按属性读取 → FrameSeqClip 路径上
  `predictive_prewarm.on_frame` 抛 `TypeError: int() argument ... not 'method'`（45s 内 484~546 次）。
  `git blame` 落在 `716ad4a9`（2026-09-23，本刀之前）；对照 `a4da423` worktree 同样复现。
  **本刀未修**（不属退役层，改动会引入本刀外的行为变化），登记为后续刀。
- **验收命令与真实输出尾部**：
  - `./.venv/Scripts/python.exe -m pytest -q`（`QT_QPA_PLATFORM=offscreen`）
    - 4.4a：`3320 passed, 12 skipped, 270 warnings in 300.37s`
    - 4.4b：`3238 passed, 11 skipped, 269 warnings in 231.94s`
  - `./.venv/Scripts/python.exe -m ruff check pet/ tests/` → `All checks passed!`（两刀各一次）

## 未完成项 / 偏差

1. **提交边界被外部提交切入**：4.4b 制作期间用户并发提交 `5f5e408`（撤除右键归因临诊日志），
   把已 `git add`/`git rm` 的 9 个退役文件删除一并带走。因此 `git log` 里两刀之间夹着
   用户的 `5f5e408`；4.4b 提交本身承载其余全部删除侧改动、守卫与文档。拒绝改写用户提交。
2. **`runtime markers 活消费` 改判为保留**：T6 预设「D7 替代通道已在，确认后删」，
   核实结论是 D7 通道的实现形态就是 runtime marker（`overlay_shell._sync_runtime_marker`
   写、`settings_standalone.standalone_pet_geometry` 读），删除会让独立设置进程失去避让定位。
   故 marker API 保留，未删。
3. **`frameseq_clip` property/method 不匹配**（上文实机记录）未修，属退役层之外，需另开一刀。
4. **稳态内存未做进程 RSS 采样**：仅有导入期 `tracemalloc` 数字；运行期内存变化是结构性
   删除（少一条 QThread/两定时器/若干标记文件），未在 30 分钟长稳里量 RSS —— 归入 4.5 长稳验收。
5. **默认化翻转未做**（任务明示不动）：`is_overlay_topology()` 默认值保持 legacy，
   `PET_RENDER_TOPOLOGY=overlay` 仍是 dev flag，由主人在实机长稳后亲手翻转。
6. `PetWindow` 侧的捕获模式行为收窄（多宠不再跨进程碰撞）**按设计**：legacy 的多宠由
   `spawn_in_process_window` 以进程内多窗承担，窗间不做冲量交换（T4「捕获模式内单宠单窗」）。
