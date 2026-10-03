# PR 报告：overlay 双端全量审查收口（DS 34 条 + GPT 3 条）（2026-09-24）

分支 `feature/single-overlay-window`。应用户要求对新架构做 DS + GPT 双端全量
独立审查（GLM 额度耗尽，GPT 替补），审查发现全部复核、修复、验收。

审查原始结论：
- DS（`.scratch/single-overlay-window/_full_review_ds.md`）：阻断 2 / 应修 16 /
  建议 16。总评「不可按现状交付为默认产品形态」。
- GPT：阻断 3（岛显隐未接入 overlay、岛撞 60-300 被阈值截断、慢帧门禁口径）。

## 修改文件说明

### 阻断级（全部修复）

- **B1 岛速幽灵速度**（`25e4185`）：静止的岛持残留速度会把贴上的桌宠拍进
  THROWN（默认开的新误报，且旧测试结构上抓不到）。双闸：
  `pet/island_bridge.py` 同 rect 死区样本即清零（治松手样本落 10ms 死区）；
  `pet/sprite_collision.py` 速度样本带写入时刻、超
  `STATIC_VELOCITY_TTL_SECS=0.15s` 未刷新按 0 处理（治按住不动零回调）。
  新增 2 条「不注入停止样本」回归。
- **M1 圈末 re-arm 每圈新起 ffmpeg**（`25e4185`）：`restart_clip` 只调
  `start()`，WebM 软停续圈前提 `_soft_parked` 只在 `stop()` 置位——改回旧机
  序列 `jumpToFrame(0)→start()`（实跑实证：gen 1->2 retired=1 → 1->1 retired=0）。
- **M2 re-arm 吞每圈首帧**（`25e4185`）：`restart_clip` 作废 `_frame_sig`，
  不再用「帧号 0 + 旧末帧图」记签名。
- **M3/M4/M11 按下即拖拽**（`600992b`）：对齐旧机 `DRAG_THRESHOLD` 语义——
  `pet_sprite.on_press` 只是点击候选、新增 `begin_drag()` 唯一升级点；
  `overlay_window.mouseMoveEvent` 过阈值才升级（绑 drag 动画/碰撞无限质量/
  探头取消三处全部改挂这一刻）；按下不再取消探头会话（**M4 探头点击拉直
  复活**）；点击台词名只在 `on_sprite_clicked` 真改绑时取（M11）。
  配套 `560d350`：弹弓就地恢复拖拽补 `begin_drag`。
- **GPT#1 岛显隐路由**（`aa9631e`）：`_toggle_pet_from_island` /
  `_aggregate_pet_visible` 只遍历 `instances[].win`（overlay 恒 None）→
  岛单击调不动桌宠；overlay 拓扑路由到 `OverlayShell`。
- **GPT#2 岛撞 60-300 被截**（`aa9631e`）：`_on_collision_squash` /
  `_on_collision_probe` 删掉 hit_min_dv=300 二次过滤（事件的阈值已按 pair
  分级：静态 60/普通 300）。

### 应修批（全部修复）

- **M6 config↔sprite 同步点**（`fb459b6`）：`_sync_sprite_settings` 启动/
  refresh/spawn 三处同步 drag_physics/throw_strength/no_move/playback_speed；
  修 sprite 默认值与 config 相反（drag_physics=True vs False、cap=6000 vs
  standard=4800）的开箱不一致；菜单 set_playback_speed 补持久化。
- **M7 落岛收尾复位飞行速率**（`fb459b6`，`sprite_collision._settle_supported`）。
- **M8 关机窗口停全部子宠库 clip**（`fb459b6`，ISSUE-111 同族）。
- **M9 stop() 停 self_talk 定时器**（`fb459b6`）。
- **M10 气泡风格/字号热改即生效**（`fb459b6`）。
- **M5 六个死开关接线**（`600992b` 同批 a/b/c + `1fcff9a`/`11b77d1`/`aa4c256`）：
  shift_drag、lock_position（overlay_window 按下闸门）、pet_opacity、
  animation_gap_seconds、golden_spin_on_click（复用 GoldenSpinController）、
  music_sing_enabled（host 形唱歌链，含轮询/续播/热改/显隐对称）。
- **M12 M-1 节能三复合项**（`5238a6c`/`1b7e9f7`/`b1355ef`）：位置分离去抖
  15tick→0.24s 秒基（降档不再放大 7-60 倍）；穿透轮询两段式（盒内 10ms/
  盒外 50ms）；0 sprite 空窗停表。
- **M14 per-sprite visible**（`f9070f7`）：绘制/命中/穿透/位置 fanout 四处
  排除 + 托盘逐只显隐（PHASE4_DESIGN 4.1b 验收项落地）。
- **M15 T4 捕获模式**（`a28bb4d`/`fa5fc4e`）：overlay 下文案改「重启后生效」，
  确认运行期切换路径不被触发。

### 证据纪律（M16）与流程登记（B2）

- `5b936b6`：内存「零增长」勘误（采样点误当曲线；有效口径=瘦身批+部署版
  3h 曲线）；µs 数字补可复现基准 `.scratch/bench_perf_overheads.py`（主线
  复跑：island 1.123µs、curve 1.834µs vs linear 0.365µs、flight setter
  0.551µs）；B2 显式登记（T5 默认化未满足设计先决条件⑤：绘制重入崩溃未
  结案+新路径无等价哨兵——待用户拍板 (a) 结案+哨兵 (b) 显式接受）。

### 未修/另案（诚实清单）

- GPT#3 周期性慢帧（每 ~10s 一次 62-120ms，tick 仪表在案）——专项归因另案，
  不阻塞本轮（修复版部署后第一批实测数据会喂给它）。
- M13 D11 单进程故障域（watchdog/自动重启/崩溃哨兵）——与 B2 同案拍板。
- 建议级 16 条（S1-S16，如 S1 曲线每 tick set_velocity 冗余升档、S3 托盘
  轮询可换帧回调）——择优另案。

## 性能分析

- 门禁：`ruff` 全绿；全量 `pytest` **3486 passed / 11 skipped / 0 失败**
  （370s）；时序族高负载×3 **1083 passed ×3 全绿**。
- M12a 去抖秒基：判定成本不变（一次减法 vs 一次计数），修正的是降档后的
  墙钟口径（T2 下旧口径 3.75s 不分离 → 新口径恒 0.24s）。
- M12b 两段式轮询：盒外 10ms→50ms（唤醒 100/s→20/s）；overlay 全屏窗光标
  恒在盒内为设计内 no-op（收益在 legacy 小窗）。
- M12c 空窗停表：0 sprite 时 tick 唤醒归零（此前空转 250ms 档 4/s）。
- M3 阈值语义：点击路径少一次 clip 绑定 + 一次同步 jumpToFrame(0)
  （每次点击省 ~2.5ms GUI 同步磁盘读，帧序列口径）。
- B1 世界侧 TTL：每次 `_static_member_state` 多一次 `time.monotonic()`
  （~50ns 级），仅静态成员求解路径。
- 打包：`build_onedir.ps1 -Variant webm-chat` 全绿，产物见部署节。

## 实机运行记录

部署（2026-09-24 15:4x）：旧版备份 `D:\dsh-pet.bak-20260924-r3`；新包替换
`D:\dsh-pet` 并保留 frameseq（无重供给）；包内与 zip 检查无 frameseq 残留。
打包冒烟：DLL 链/编码/exe 启动 2.4s/--settings 1.3s 全绿，portable.zip 187.5MB。

运行冒烟（pid 29092，`pet-29092.log` + kimi-cu 截图在案）：

- 启动 1.1s 进事件循环；主宠+2 子肥鱼复活渲染、游走、互撞音效（轻重分级）正常；
- **拖拽实测**（SendInput 真鼠标）：过阈值才跟随光标 + 拖中切悬空动画 +
  松手落定回待机（M3/F1 实机确认，无点击闪悬空姿态）；
- **点击实测**：点击反应动画 + Q 弹 + 音效（无拖拽态残留）；
- **帧节奏**（tick 仪表，T0/T1 满速 170Hz 三档分钟级样本）：
  p50=6.0ms / p99=9.4-10.0ms（标称 6ms）；
- **资源**：WS 207MB（3 宠活跃碰撞期；启动 174MB）；CPU 66.7% 单核
  （≈16 核 4.2%，T0 满速档）；ffmpeg 进程 = 1（冷集 webm，热集帧序列化零进程）；
- 已知未决：周期性 ~100ms 慢帧仍偶发（GPT#3 专项另案，仪表持续在案）。

## 遗留与登记

- B2/M13 待用户拍板（崩溃结案+哨兵 vs 显式接受）；
- GPT#3 慢帧专项归因另案；
- DS 建议级 16 条择优另案；
- PR 推送待用户确认（§13）。
