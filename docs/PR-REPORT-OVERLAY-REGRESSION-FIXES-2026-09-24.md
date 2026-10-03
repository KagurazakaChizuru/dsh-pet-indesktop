# PR 报告：overlay 架构六类实机回归修复 + 上游 main 同步（2026-09-24）

分支 `feature/single-overlay-window`。新架构部署到日常环境后用户实机报出六类问题，
本批次全部根因实锤定位并修复，同时把上游 `main`（PR #187 等 9 个提交）合入本分支。

问题清单（用户原话归类）：
1. 桌宠经常原地消失又出现（旧架构已修过的回归）；
2. 边缘探头被撞出的「头槌」（抛掷彩蛋）结束后，偶尔被撞又误入头槌态；
3. 上游 PR 有 bug 修复更新，需同步；
4. 移动与移动动画匹配的优化丢失（滑步感、拖拽无悬空动画等）；
5. 自言自语气泡与点击气泡不出现；
6. 拖拽灵动岛撞桌宠只有平推、没有碰撞弹开。

## 修改文件说明

### 上游同步（merge `origin/main`，9 提交）

含 PR #187（issue #186 跨屏拖拽/抛掷恢复 + 托盘图标消失占位修复 + 右键菜单
「鼠标穿透」去重收敛）与 4 个 CI/测试加固提交。auto-merge 无冲突；3 处语义
冲突调和：

- `pet/window.py`（+1/-1）：`_stop_physics` 的 `_reentry_after_throw_armed`
  改 `getattr` 防御取值（上游 `_PhysicsStub` 无此字段，与本函数既有防御口径一致）；
- `tests/test_tray_icon_ready.py`（+20/-3）：本分支帧序列 B 档让真实素材首帧
  在构造期同步就绪，「首帧未就绪」前提无法自然复现，两条用例改显式清状态模拟；
- `tests/test_sprite_menu_facade.py`（+3/-1）：「鼠标穿透」按上游意图从右键
  全菜单期望清单移除（入口收敛设置页/托盘/命中右键小菜单）。

### 修复 1：切动画瞬间闪消失（commit `b04c132`）

根因：`FrameSeqClip.start()` 在预取未就绪时把显示槽清成 None，sprite paint
取不到帧画透明=桌宠消失；行为状态机每 ~10s 切一次动画故「经常」发生。旧架构
`stop→jumpToFrame(0)→start` 同步拿首帧的语义（edecd57）移植时丢失。

- `pet/frameseq_clip.py`（+4/-2）：`start()` 不再清显示槽，保留预热帧/上一圈
  末帧直到帧 0 到货；
- `pet/pet_sprite.py`（+10/-2）：`bind_clip` 在 `start()` 前 `jumpToFrame(0)`
  同步取帧 0；不再清 `self._pixmap`（旧帧兜底，新帧到货覆盖）；
- `pet/overlay_shell.py`（+6/-0）：`set_on_top` 加同值早退守卫（防御性，
  `refresh_settings` 每次保存都走这里，避免不必要的原生窗口重建）；
- `tests/test_frameseq_clip.py`（+27）、`tests/test_pet_sprite_hardening.py`（+83）。

### 修复 2：头槌结束后误入头槌（commit `57b5f91`）

根因：`_probe_hit_confirmed` 把探头 5 秒重进倒计时残留旗标当作「本次撞击真
取消了活跃探头会话」的证据；彩蛋 `end()` 不清该倒计时，5s 窗口内再被撞即误
re-arm。实机日志铁证：arm 30 次 vs 探头退出仅 11 次（63% 假 arm）。旧架构
arm 与「cancel 真取消活跃会话」原子绑定（edge_probe.py:283-287）。

- `pet/sprite_edge_probe.py`（+12/-4）：`on_sprite_collision_hit` 返回 bool
  （真执行 `cancel(...,"collision_throw")` = True）；
- `pet/overlay_shell.py`（+9/-4）：取消结果显式传给 egg
  （`probe_cancelled=cancelled`）；
- `pet/sprite_throw_egg.py`（+34/-29）：arm 仅当 `probe_cancelled is True`；
  删除 `reentry_remaining_of>0` 推断分支（残留态泄漏唯一通道）；
- `tests/test_sprite_throw_egg.py`（+67/-7）、`tests/test_sprite_edge_probe.py`（+4/-3）：
  新增「egg.end 后 5s 窗口内 probe_cancelled=False 不得 arm」回归。

### 修复 3：拖拽灵动岛撞桌宠只推不弹（commit `ca5bb11`）

根因：碰撞世界静态成员（岛）速度写死 0，`add_static_member` 无速度参数；
求解器只认相对速度 → vn≈0 → 冲量 j=0 → 只剩位置分离（平推）。旧架构岛速
估计（`island_collision._update_motion`）在 overlay 拓扑下整体被旁路未移植。

- `pet/sprite_collision.py`（+18/-3）：`add_static_member(..., vx=, vy=)`
  存 `_static_member_velocity` 并打脏 `_static_dirty`；`_static_member_state`
  读存储值；
- `pet/island_bridge.py`（+132/-11）：岛速估计移植到 `update_geometry`
  汇聚点，五条守卫逐条保留（几何动画 `_geo_to` 期间清零不采样——旧注释
  记载的「展开动画 2600px/s 凭空拍飞鱼」教训；尺寸变化重置采样点；
  dt<0.01s 跳过；瞬移守卫；仅拖拽钳 `_MAX_ISLAND_SPEED=1500`）；`_applied`
  含速度（岛停下 rect 不变也归零）；
- `tests/test_island_bridge_velocity.py`（新建 +256）：端到端「800px/s 拖岛
  → sprite 冲量 + THROWN + CollisionEvent + bump」+ 守卫逐条。

### 修复 4：移动与动画匹配层（F1-F7，commits `1e04e2c`/`9d82bf3`/`496ba99`/`40fc3c9`/`5c4ae57`/`1484685`/`39fff25`）

旧架构三层机制移植时整层丢失，逐条补齐：

- F1 拖拽悬空动画：`pet/sprite_behavior.py` 分类表读 `drag`；新增
  `on_drag_started/on_drag_released`（STATE_DRAG）；`pet/overlay_window.py`
  按下命中即绑 drag、`pet/overlay_shell.py` 真拖拽松手回 idle；
- F2 圈末 re-arm（修「多圈移动第 2 圈起动画冻结/长拖拽画面卡住」）：
  `pet/pet_sprite.py` 新增 `restart_clip()` 并接 `clip.finished`；控制器在
  MOVE/DRAG/ACTS 剩余时长 >0 收到 finished 时重播；
- F3 圈内逐帧位移曲线（修滑步感）：`pet/movement.py` 新增纯函数
  `curve_progress_at_time`（墙钟折算等效帧号，委托 `move_position_at_frame`
  插值，曲线语义单一事实来源）；`_start_move` 由匀速改每 tick 按曲线折算
  速度，到点仍 snap；
- F4 抛掷飞行期动画：`pet/sprite_physics.py` 飞行期按速度设播放倍率
  （`physics.flight_anim_speed`，叠加用户速率），落地先复位速率再交还
  （duration 除以 playback_speed，不复位会让下次 _plan_move 失配）；
- F5 接管撤销移动计划（修拖拽后瞬移）：非 normal 打 `suspended`，回 normal
  时 MOVE/TURN 计划作废回 idle，绝不 snap 旧目标点；
- F6 开播失败不建计划：`bind_clip` 返回 bool，失败走旧机同款回退链；
- F7 探头会话闸门：acts 桶降级 idle、turn 不翻朝向（对齐
  `window_optional_services.py:223-233/349-350`）。

### 修复 5：self_talk 族气泡接线（commits `40e6599`/`e43c89c`/`04658fc`/`7a459c2` + 热修 `69445e2`）

根因：周期自言自语/点击气泡/逐动画台词/朗读的唯一宿主是 PetWindow，overlay
拓扑下它不构造，整族静默失效（配置开关是开的，代码没接线）。

- `pet/sprite_bubble.py`：follower 补 `show_image`（配图自言自语通道）；
- `pet/overlay_shell.py`（+200 余行）：`_init_self_talk` 按 window.py:458-480
  逐字段装配 + 单发定时器；5 个 host 形转发；关键语义差——不走
  `window_alerts.show_self_talk_text`（它判 `host.on_open_quick_chat` 会把
  气泡置不可点），用壳自己的 `_apply_bubble_interactive()` +
  `_show_bubble_text`；显隐对称（隐藏停表/恢复重排）；单击分支接
  `_on_sprite_click`（click_show_balance / click_show_self_talk 两路）；
  `_bind_bubble` 透传气泡风格/字号；
- `pet/sprite_behavior.py`（+10）：只读访问器 `anim_of`（点击动画名 →
  逐动画台词）；
- `pet/app.py`（+6）：朗读注入 `on_self_talk_speak = self.speak_self_talk`；
- 热修 `69445e2`：`refresh_settings` 重读 self_talk 字段并重排程——运行期
  改开关/间隔/点击行为/配图目录不再要重启；
- `tests/test_overlay_self_talk.py`（新建 +280 余行，11 用例）。

## 性能分析

- 修复 3 岛速采样：`_update_motion` 0.42µs/次（20 万次微基准），只在岛几何
  事件回调时调用；新增内存 = 每静态成员一个 2 元组；无新线程/系统调用。
- 修复 4 曲线路径 vs 线性路径：单 sprite 20 万 tick offscreen 实测
  21.515µs → 21.642µs（**+0.128µs/tick**，上界 ≤ T0 6ms 档的 0.04%）；
  `set_flight_anim_speed` 稳态 0.836µs/次。无新线程、无按 tick 增长内存。
- **可复现命令（M16 补正，2026-09-24 下午主线补跑）**：
  `QT_QPA_PLATFORM=offscreen PYTHONPATH=<repo> ./.venv/Scripts/python.exe
  .scratch/bench_perf_overheads.py`（n=50000/项）。本机复跑输出：
  `island_update_motion 1.123µs/次`、`curve_progress_at_time 1.834µs/次`
  （linear fallback 0.365µs/次）、`set_flight_anim_speed(steady) 0.551µs/次`
  ——与上文 DS 侧数字同量级（µs 级、不同机器负载下绝对值有差），结论不变：
  新增路径成本可忽略。
- 修复 1 的收益面：切动画不再有空窗，帧 0 同步磁盘读（frameseq B 档既有
  能力），预测预热首次真正生效（此前 start 清槽把预热帧一并清掉）。
- 修复 5 稳态开销：self_talk 仅一个单发 QTimer（间隔 ≥5s），timeout 时一次
  气泡绘制；隐藏期停表零开销。
- 门禁：`ruff` 全绿；全量 `pytest` **3415 passed / 11 skipped / 0 失败**
  （307s）；时序族（overlay/sprite/tick/frameseq/library/spawn/session/gate/
  island）高负载复跑×3：**1028 passed ×3 全绿**。
- 打包：`build_onedir.ps1 -Variant webm-chat` 全绿（DLL 链/编码/冒烟×2），
  产物 187.5MB portable.zip；frameseq 不入包（首跑供给口径不变）。

## 实机运行记录

部署（2026-09-24 12:4x）：旧版备份 `D:\dsh-pet.bak-20260924-r2`；新包替换
`D:\dsh-pet` 并**保留** `_internal/.../frameseq`（153MB，免 ~3min 重供给）；
zip 与包内检查无 frameseq 残留。

启动冒烟（pid 35764，`pet-35764.log`）：

- 启动 1.2s 进入事件循环；`素材加载完成：shenshen 106 段动画` ×3 即刻完成
  ——frameseq 保留生效，无 provision 重跑；
- `overlay: 按活跃清单复活 2 只子肥鱼`（D5 跨重启复活）；
- 工作集 **159MB**（含主宠+2 子肥鱼，对比上一部署版同场景 203MB）；
- `overlay: 全屏状态变化 hit=True ... proc=StarRail.exe` → T3 降载：
  用户游戏全屏期间自动隐藏按设计工作（截图确认游戏确在全屏）。

交互类修复（闪帧/头槌/岛撞/拖拽动画/气泡）的实机观感验证：部署时用户游戏
正在全屏运行，不宜打扰，留待用户验收——对应的机器验证已在门禁内完成
（修复 1/2/3 的回归测试共 20 条、修复 4 的实机探针
`.scratch/single-overlay-window/probe_f1f7_anim_match.py` 以真实角色包 +
真实 ffmpeg + 真实 QTimer 跑通 F1-F4/F7、修复 5 的 11 条用例含「听到的==
看到的」朗读一致性）。

## 遗留与登记

- **B2 流程登记（DS 全量审查指出，显式接受待拍板）**：PHASE4_DESIGN.md §6
  先决条件⑤「Qt6Gui 绘制重入崩溃完成归因（未结案不得切换；新路径需先布
  等价哨兵）」在 T5 默认化时未满足——崩溃案至今未结案（门禁 4 轮 3 绿 1 次
  0xC0000374 退出期崩溃同族待辨），且新路径无 `qInstallMessageHandler`
  等价哨兵。当前状态 = 先决条件未满足且未声明。选项：(a) 结案 + 布哨兵后
  再谈默认化；(b) 用户拍板显式接受该风险继续推进（本分支现状）。在拍板前，
  本条作为**已登记未决风险**跟随每个 PR 报告。
- 探头重进倒计时起点语义漂移（overlay 从 cancel 起算 vs 旧机落定起算，
  飞行 >5s 丢重进资格）——另案，需用户拍板是否对齐；
- `_MAX_ISLAND_SPEED` 在 island_bridge 与 island_collision 各一份，口径人工同步；
- PR 推送待用户确认（§13）。
