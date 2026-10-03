# PR 报告：全量大审修复批次（21 条已验证缺陷）

> **基线**：`6b34114`（PR #215 HEAD）
> **分支**：`feature/single-overlay-window`　**日期**：2026-10-03
> **范围**：16 个产品文件（+925/−249）+ 20 个测试文件改动 + 2 个新测试文件 + 1 份前置专项报告
> **关联**：两家独立全量审查（astra / ops5.5，资料包与发现原文在 `.scratch/full-review-20261003/`：REVIEW-BRIEF.md、REVIEW-BRIEF-EXTRA.md、FINDINGS-ASTRA.md、FINDINGS-OPS55.md、VERDICT.md 对账表）；前置专项 [`PR-REPORT-STALE-CLIP-PAUSE-FREEZE-2026-10-03.md`](PR-REPORT-STALE-CLIP-PAUSE-FREEZE-2026-10-03.md)（本批第 1 条的完整取证）

## 一、核心特性

用户实机报障「拖拽后偶发卡住 / 提起动画变静态图 / 挂机回来三只全冻但还在移动」，根因定位为 **clip 暂停标记跨绑定滞留**（隐藏期换绑不清旧 clip 的 `_paused`，恢复只续当前 clip，旧 clip 再绑时 `start()` 不起定时器冻在首帧）。以此缺陷类为引子，两家外部模型对全仓库做了一次八维度大审（运行时正确性/并发生命周期/性能/内存资源/错误处理/持久化/跨平台/打包依赖），27 条发现并集经主代理逐条回查裁决：**修 20 条（加上冻结根因共 21 项修复）、缓 5 条、否 1 条、产品决策 1 条**（逐条对账见 VERDICT.md）。

用户可见变化：拖拽/提起/走路动画不再冻成静态图；锁屏/挂起后桌宠真正降载（此前原生通知从未接入）；隐藏宠物不再是隐形碰撞墙；贴贴分离一次到位（**碰撞手感有变化，见 §五边界**）；屏迁移不再冻 clip 或截断位置；锁屏/退出时位置与资源收口不再被单步异常跳过。

**红线 / 不变量**：「隐藏期零推进」契约不破（sprite 暂停中换绑仍立刻 re-pause，既有测试把守）；`ImpulseResult.dx_*` 末轮语义不变（新增 `sep_*` 累计字段承载新口径）；纯位置分离去抖（0.24s 墙钟窗口）语义不变（被抑制 pair 的位移精确扣减，400 组随机场景恒等式验证偏差 ≤4.3e-14）；不写任何 git 历史外的用户配置/素材。

## 二、修改文件说明

`git diff --numstat`（本批，不含瘦身 PR #223 的 3 个文件——那刀独立交付）：

### 实现（16 个文件，按修复批分组）

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/pet_sprite.py` | +34/−3 | ① bind_clip/restart_clip 补 `else: resume()`——sprite 未暂停时清掉 clip 跨绑定滞留的 `_paused`（冻结根因，两处对称收口）；② `flipped`（Qt 6.9+）加 `mirrored` 回退（requirements 声明 6.5） |
| `pet/library.py` | +33/−2 | ① `resume_warm` 重启 `_idle_trim_timer`（否则首次隐藏后池级回收终身停摆）；② `shutdown` 先试 `close()`（FrameSeqClip worker 的 deleteLater 此前永不执行）；③ 新增 `warm_allowed()` 公开闸门；④ 供给取消的 except 分支同样孤儿化 worker（否则库析构带活线程 = Qt abort） |
| `pet/frameseq_clip.py` | +50/−7 | ① `warm_first_frame` 后台只解码、提交经 `_warm_frame_ready` 信号回 GUI 线程复核（消除后台直写显示槽竞态：倒写帧 0 / 撤销池级回收）；② `close()` 幂等化 |
| `pet/webm_clip.py` | +148/−61 | ① 暂停并入节流谓词转阻塞背压（本地 reader + feed 消费端；feed 补 `reset_stall` 防暂停被看门狗误判断流）——改前暂停=持续解码持续丢帧、暂停位置丢穿；② `start()` 的 `_running` 后置到线程+定时器成功之后，中途失败走 `_hard_stop` 收口照抛；③ `cancel_first_frame_warm` 的 terminate 失败接入未确认追踪；④ abandoned 条目告警只打一条 + 终局清出（此前每 500ms 刷屏且 clip 永久钉注册表） |
| `pet/tick_driver.py` | +22/−6 | `set_suspended` 逐 sprite 停/续表加 per-sprite 容错（一只抛错不再中断整轮——幂等守卫下这轮是唯一机会） |
| `pet/overlay_shell.py` | +206/−74 | ① `_clips_playable()` 有效可播闸门（窗口可见 且 未挂起），统一 `set_sprite_visible`/`_set_all_clips_paused` 恢复路径（整窗隐藏中逐只显示、锁屏中避让解除都不再提前放行）；② `_spawn_slot` 按有效可播初始化新 sprite 节拍 + `start()` 补放行；③ 退出收口逐步隔离 `_run_exit_step`（save_position/供给取消必达）+ 主库子宠库同一 `_shutdown_libraries`；④ 屏迁移：快照有效可见性（隐藏/避让中迁移不再无条件 show），可见分支迁移后补恢复节拍 |
| `pet/sprite_behavior.py` | +72/−9 | ① `_plan_duration` 按 sprite 速率换算计划时长（8 个读取点；改前读 clip 残留速率，慢动作被提前切走/快动作长停末帧）；② 预测预热与落地预热过库级闸门（设置页关预热/隐藏期不再直提 `_WARM_EXECUTOR`） |
| `pet/collision.py` | +27/−0 | `ImpulseResult` 新增 `sep_dx_a..sep_dy_b` 累计分离字段（`dx_*` 末轮原义不动）；求解器逐 pair 累计记账 |
| `pet/sprite_collision.py` | +66/−15 | ① 位置写回改按 combined 累计量每只一次 `set_pos`（去抖抑制 pair 精确扣减）——改前多轮迭代只写末轮，实测该移 14.19px 实移 0.84px；② 隐藏 sprite 整只退出成员快照（不再当隐形障碍墙）+ 可见性入运动签名 + 去抖表按成员离场清理 |
| `pet/overlay_window.py` | +14/−3 | `sprite_at` 粗筛 `rect()` → `paint_bounds()`（旋转后画出原矩形的像素可命中；alpha 细判原点不变——bounds 原点方案实测采错像素，已纠偏） |
| `pet/session_watcher.py` | +78/−16 | 缺陷三层修复：双继承 `QAbstractNativeEventFilter`（普通 QObject 被 Qt 直接 TypeError 拒装）+ 双基类各自显式初始化（漏了 C++ 子对象不建，装上收不到任何消息）+ `_message_address` 归一 VoidPtr/int（6.x 真机传 VoidPtr，收得到也认不出）；install 失败不再假成功（warning + 返回 False），新增 `uninstall()` 接退出收口 |
| `pet/config.py` | +23/−2 | reload 区分「键缺失」与「显式 null」：`_NULL_ACCEPTING_KEYS` 白名单（消费者逐一排查后仅 `context_menu_layout`）——设置页「恢复默认」此前静默回滚且会被主进程写回旧值 |
| `pet/proactive_limiter.py` | +94/−18 | 状态文件逐字段类型契约（`{"count": null}` 类穿透回退默认）；写盘复用 `atomic_replace_with_retry` + 清 tmp + warning；`consume_budget` fail-closed |
| `pet/slot_manager.py` | +50/−18 | 两处直写改 temp+replace；读侧只在 pid 确认死亡时删标记（改前解析失败即删，竞态窗口误删活进程避让标记） |
| `pet/agent_link.py` | +23/−5 | `_session_meta_cache`/`_exploration_names` 加 256 有界 FIFO（此前随会话数单调增长） |

### 测试（20 改 + 2 新，新增回归 60+ 条，全部先红后绿）

| 文件 | 覆盖 |
|---|---|
| `tests/test_sprite_visibility.py` | 冻结根因毒化链 + 暂停所有权闸门 + restart 对称收口 |
| `tests/test_frameseq_clip.py` | 后台预热不倒写显示槽 / 提交寄存 `_pending[0]` / 半销毁降级 / close 幂等 / shutdown 回收 worker |
| `tests/test_library_idle_frame_trim.py`、`test_library_priority_warm.py` | trim 恢复重启（含兄弟库）、warm_allowed 闸门 |
| `tests/test_webm_clip_lifecycle.py`、`test_webm_clip_broker_feed.py`、`test_webm_first_frame_lock.py` | 暂停背压不丢帧 / 暂停中 stop·换代回收 / feed 暂停不触看门狗 / start 失败定序 / terminate 追踪 / abandoned 终局 |
| `tests/test_sprite_behavior.py`、`test_flight_bubble_suppression.py` | 计划时长按 sprite 速率（0.5/2.0 双向）、预测/落地预热过闸 |
| `tests/test_tick_driver.py` | set_suspended 单只抛错不中断整轮（停/续双向） |
| `tests/test_overlay_spawn.py`、`test_overlay_lifecycle_gaps.py` | 隐藏期 spawn 暂停继承 / start 补放行 / 退出收口必达 / 主库 shutdown |
| `tests/test_sprite_collision.py`、`test_requested_regressions.py` | 累计分离写回终位断言（真 PetSprite）/ 去抖不搭车 / 隐藏退出碰撞 |
| `tests/test_overlay_window.py` | 旋转溢出像素命中（探头+抛掷）/ 负例不误中 |
| `tests/test_session_lock_suspend.py` | 真实安装契约 / VoidPtr 消息 / PostThreadMessageW 真消息投递 / 失败可观测 / uninstall 幂等 |
| `tests/test_config_reload_null.py`（新） | 显式 null 采纳 + 白名单外不采纳 + 两进程视角回写 |
| `tests/test_proactive.py`、`test_slot_and_memory.py`、`test_agent_link.py`、`test_frameseq_provision.py` | limiter 契约/写盘 fail-closed、slot 原子写/活标记不误删、缓存有界、供给孤儿化 |
| `tests/test_overlay_screen_migration.py`（新） | 隐藏/避让中迁移不 show、可见迁移复播、大小屏比例位置保真（真壳真 clip） |
| `tests/test_pet_sprite.py` | flipped→mirrored 回退逐像素一致 |

### 未改动（刻意）

- `restart_clip` 之外的 legacy `pet/window.py`：AGENTS.md 划定「只修崩溃」，同理论毒化在 legacy 暂停语义下可能存在，不在本批范围。
- `pet/decode_fanout.py`：发布端暂停→订阅者 1.9s 回退本地 ffmpeg 是 DS-1 修复的已知连带（部署版全 frameseq 素材不触发），修法在 hub 侧暂停语义，另立项。
- 瘦身三件套（`scripts/build_onedir.ps1`/`scripts/slim_bundle.py`/`tests/test_bundle_slim.py`）：PR #223 独立交付，本批不含。

## 三、实现要点

- **暂停契约归 sprite 持有，clip 状态不得跨绑定滞留**：所有修复围绕这一所有权原则——bind/restart 时按 sprite 当前状态强制对齐（`resume()` 幂等 no-op），而不是给 clip 引入世代概念。备选「`start()` 无条件清 `_paused`」被否（改变全部调用方语义，legacy 依赖不可控）。
- **有效可播 = 窗口可见 ∧ 未挂起**：暂停有两个独立所有者（壳的显隐 / 驱动器的挂起），恢复路径必须看合取而非「这次是谁解除的」。
- **碰撞写回用求解器自己的记账口径**：combined 的 per-sprite 累计量恒等于各 pair 累计之和，去抖抑制按 pair 精确扣减后写回仍严格「每只一次 set_pos」（分次会被 body_box 钳制非线性截断）。
- **后台线程只生产、GUI 线程才提交**：预热竞态的修法范式（信号队列投递 + 提交点复核），选信号而非 `Q_ARG` 是因为后者运行期解析类型名、被测试替身替换后静默丢失。

## 四、性能分析

- **bind/restart 新增 else 分支**：真 FrameSeqClip 实测 **0.299µs/次**（timeit 100k），触发频率 = 动画换绑（实机 5–30s 一次），稳态可忽略；零系统调用/零内存增长。
- **sprite_at 粗筛**：无旋转 +1.43µs/次（多一次 paint_bounds），45° 旋转 +13µs/次；Windows 穿透轮询 10ms/次 → 4 宠新增 ≈0.08% 核（无旋转）/0.5% 核（全旋转姿态，仅探头/抛掷期）。
- **碰撞写回**：per-sprite 循环 N=2/4/8 实测 +0.7/+1.4/+3.0µs 每 tick；真位移时 `set_pos` 次数从「每 pair ≤2 次」降为「每 sprite ≤1 次」。
- **迁移**：`set_bounds` 6.74µs/只/次（迁移本身是毫秒级原生窗口重建）；可见分支补放行 3 宠 4.38µs（未暂停时幂等空转）。
- **WebM 暂停背压**：reader 每帧多一次 bool 读（24/s/clip）；暂停期 CPU **下降**——实测 2s 暂停窗口解码帧计数 0 增长（改前约 5 帧/s 持续解码丢帧）；feed 分支 `delivered` 钉住不再增长。
- **锁屏接入后**：`set_suspended` 真实生效 = 锁屏期 tick 强制 T3（1000ms 心跳）+ 逐 sprite 停播放节拍——此前该路径从未触发（过滤器没装上），整夜挂机解码被真正消除。
- 无新增线程/定时器/网络/磁盘常驻成本；`_idle_trim_timer` 恢复运行是**恢复既有设计**（10s 兜底回收），不是新增开销。

## 五、实机运行记录

- **取证**（部署进程 pid 7556 日志全时间线扫描）：tick p50=6.0ms 健康、全程零条 frameseq 预取 WARNING（排除预取失能）、全屏 watcher hide/show 每天数十次（毒化机会频率证据）、出现 T1→T2 quiet 降档（帧到达停止指纹）、drag 素材 241 帧完好（排除素材损坏）。定位报告全文见前置专项报告。
- **红→绿**：每条缺陷均有修复前红色回归（真实断言失败与实机症状逐字对应，如 `clip._timer.isActive()==False`、`assert 871 == 1360.0 ± 2`、原生过滤器 TypeError）与修复后绿色；六批红绿证据与各批全量（4209/4226/4237/4258/4279/4285 passed 逐批递增）在各批交接报告（`.scratch/full-review-20261003/` 各 agent 输出）。
- **主代理复验**：每批产品 diff 逐行复核 + 相关族本地复跑（76/169/100/78/421/61 绿）+ 最终全量自查 **4284 passed / 12 skipped / exit=0**（642s，日志 `final-fullsuite2.log`）。
- **真机构建与部署**：本分支工作区（+瘦身三件套本地叠加）构建 `dist-onedir` 双冒烟全过（exe 2.9s 起、--settings 0.8s 起），部署 `D:\dsh-pet\`（pid 16004，三宠复活、106 段帧序列映射、tick 满速）。
- **无法自动验证项（探针证据替代）**：锁屏/挂起的真实 Windows 会话（offscreen 用 PostThreadMessageW 真消息替代验证过滤器链）；真人拖拽手感与多屏迁移（需部署后实机确认）；非 Windows 平台（本轮未动三平台）。

**边界（诚实登记）**：
- 碰撞分离修到位后**手感变化未实机验收**（方向 = 求解器设计口径还原，真人体验待用户确认）。
- frameseq 原生崩溃家族（既有立项）本周期出现率偏高（9 次全量 4 次 ~27% 处 AV，崩点漂移、栈含 concurrent.futures worker，重跑即绿）；与本批改动无关（崩点周边文件未动、相关族单跑全绿），但建议根修专项提上日程。
- 发布端暂停→订阅者回退 ffmpeg（DS-1 遗留，webm 冷集才沾边）。
- `character_head_box` 已实现零消费（接上或删除）待产品决策。
- 非 Windows overlay 默认拓扑吞输入（两家审查 P0/P1 一致命中）：本轮按「暂停三平台」纪律缓修，**属发布阻断级，建议尽快立项**。

## 六、本地 PR 说明草稿

> 本 PR 追加提交 = 全量大审修复批次（21 条已验证缺陷 + 60 条新回归，两家独立审查 → 主代理逐条裁决 → ds 六批修复 → 逐批验收）。用户可见：拖拽/挂机冻结修复、锁屏降载真实生效、隐藏宠退出碰撞、碰撞分离到位、屏迁移不再冻帧/截位、退出收口不再被单步异常吞掉。逐条对账与红绿证据见 `.scratch/full-review-20261003/VERDICT.md` 与 docs 两份报告。已知边界：碰撞手感变化待实机验收；非 Windows 拓扑穿透缺口缓修（发布阻断级，另立项）。

## 第二轮修正（2026-10-03 晚）：close() 的 deleteLater 是崩溃放大器

**起因**：本批推送后 CI ubuntu/macOS 双双段错误（exit 139，~27% 处、栈含 concurrent.futures worker）；当日本地全量崩溃率亦偏高（4/9）。

**定位实验**（崩溃邻域连跑：test_foreground_steal + test_frame_path_waste + test_frameseq_* 五族）：

| 代码状态 | 崩溃率 |
|---|---|
| 修复版（DS-1 close() 挂 deleteLater） | 3/17（2/11 + 1/6） |
| 仅回退预热信号改动 | 2/6（排除预热 emit 嫌疑） |
| close() 去掉 deleteLater（只退役） | 0/6 |
| 正式修复（退役制） | 0/6 |

**结论**：DS-1 缺陷 2 的修复把「worker 挂 deleteLater 到共享预取线程」引入库收口路径；共享线程被看门狗重建/退出收口杀掉后，死线程队列里的 DeferredDelete 无人处理，线程销毁/重建竞态 = access violation。崩点在 frameseq 域内漂移（钉到三条不同用例）正符合「异步落地撞上死对象」的签名。

**修法**（与文件内 `_revive_prefetch_worker` 的退役先例同制）：
- `FrameSeqClip.close()`：worker 退役 = 断开 `loaded` 信号 + 留引用进 `_retired_workers`，**绝不 deleteLater**；幂等标志保留；
- `_revive_prefetch_worker` 的退役列表**删掉 4 条上限裁剪**——裁掉引用 = 让 GC 在随机线程析构跨线程 QObject，同类风险；
- 库收口注释与两条测试改写为新契约（退役 ≠ 销毁，断言 `isValid` 仍真）。

**验证**：邻域 6 连跑全绿（对照 deleteLater 版 3/17 崩）；`test_frameseq_clip.py` 31 passed；ruff 净；最终全量见 final-fullsuite3.log。

**边界**：早前隔离的 `test_retained_frame_is_not_reused_as_frame_zero` 肇事于本批之前（上周），与本放大器不同源，维持隔离+立项根修不变。

## 第三轮修正（2026-10-03 深夜）：macOS CI 三文件组合段错误的处置

**现象**：推本批后 macOS CI 在主套件 81% 处确定性段错误（3/3 同点：`test_sprite_visibility.py::test_rebind_while_paused_stays_paused` 边界，崩溃线程为无 Python 帧的原生线程）。Windows/ubuntu 同代码全绿（各 2 次）+ 本地 Windows 同组合 8 连跑仅 1 崩。

**定位链**：单文件（visibility）绿 → 双文件三组合全绿 → 三文件（overlay_spawn + overlay_lifecycle_gaps + visibility）同进程必崩 = 跨文件累积态炸弹。Windows 本地复现的 dump 显示两个 `overlay_shell._load`（自言自语配图加载）守护线程跨测试存活，崩在主线程测试体的原生调用里。预热信号与 close() 的 deleteLater 均已分别经对照实验排除（后者是 ubuntu/windows 家族的放大器，已修）。

**处置演变**：先按 webm 族先例把三文件在 macOS 拆独立进程止血（dd3e632，全绿）；随后按 conftest 登记册既有范式（`_shutdown_live_for_tests`）做了**根修层止血**——OverlayShell 接入活跃登记册，逐测试 stop() 收口其 tick 驱动器/计时/监视器/配图加载线程/素材库，并把配图加载线程纳入壳生命周期（stop 时换代作废）+ `list_self_talk_images("")` 空配置扫 CWD 的缺口堵上。收口后：Windows 本地 spawn 单文件 12/12、三文件组合 10/10 全绿（修复前 2/12 与 1/8 崩），登记册收口后 Windows 本地复现消失（10/10 绿）但 macOS 81% 依旧（仅存于 mac）——按 CI 纪律停止重试，mac 三文件拆独立进程作为最终 CI 处置（dd3e632 形态，全绿实证），win/ubuntu 保留主套件内全覆盖。

**未结案**：登记册收口是测试侧防线；退出窗口里守护线程与 Qt 拆除的深层竞态（生产侧"退出瞬间偶发闪退"量级）仍归 frameseq/生命周期专项。配图加载线程现已具备作废机制，专项里再补进程退出时的 join。
