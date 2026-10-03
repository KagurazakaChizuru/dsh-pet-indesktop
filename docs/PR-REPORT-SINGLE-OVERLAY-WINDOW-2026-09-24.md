# PR 报告：单合成窗（overlay）新架构产品化 + 帧序列化 B 档

> **基线**：`main`（含 Merge PR #185）
> **分支**：`feature/single-overlay-window`　**日期**：2026-09-24
> **范围**：45 个提交，122 个文件，+23078 / −8233（`git diff --stat main...HEAD`）
> **关联**：`.scratch/frame-seq-feasibility/FEASIBILITY.md`（帧序列化可行性实测）、
> `docs/PR-REPORT-PHASE4-4-RETIRE-MULTIPROCESS-2026-09-23.md`（4.4 退役刀详录）、
> `docs/PR-REPORT-OVERLAY-MENU-PARITY-2026-09-24.md`（菜单 parity 详录）

## 一、核心特性

把桌宠的渲染与宠物生命周期从「每宠一个 OS 窗口 + 多进程碰撞 IPC」替换为
「单进程单合成全屏窗 + sprite 世界」，并把热集动画（≈95% 播放时长）从
运行时 ffmpeg 解码替换为构建期/首跑转换的无损 WebP 帧序列。用户可见变化：
多宠碰撞在同一物理世界内实时求解（碰碰车）、进程数 N→1、ffmpeg 进程群
归零、切动画/首帧从 60-166ms 降到 ~2.5ms、右键菜单/岛/弹弓/边缘探头等
全部交互语义与旧版逐项一致。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 单合成窗渲染拓扑 | OverlayWindow 统一 tick/脏矩形/联合命中/逐像素穿透；PetSprite 帧签名缓存/拖拽/抛掷；行为/碰撞/物理三控制器进程级一组，统一 TickDriver 驱动（M-2），TickGovernor 四档闲置降档（M-1） |
| 2 | 交互 parity | 右键全菜单（模板感知 legacy/modern，一项不缺）、拖文件投喂、气泡/快速对话锚点、自说自话、灵动岛 stadium 碰撞墙、弹弓蓄力瞄准+轨迹预览、边缘探头+throw_egg 彩蛋、squash Q 弹、acts 随机动作池、碰撞/点击音效（异步） |
| 3 | 多宠生命周期 | 活跃宠清单复活、无锁 slot 身份分配、子肥鱼各自位置持久化、主实例提升、托盘聚合、设置进程指令通道（D12）、逐 sprite 设置路由（D13）、双开单实例门（D4） |
| 4 | 帧序列化 B 档 | 热集 11 clip 转无损 WebP 帧序列（libvpx+bgra 防坑参数固化），首跑后台低优自动供给（原子目录/QLockFile 互斥/会话闸门），GUI 零解码异步预取 |
| 5 | 多进程层退役 | collision_ipc/codec/client、instance_launcher、child_pet_cleanup 等 −4214 行删除，机器化守卫锁定；legacy 拓扑保留为捕获模式与 `PET_RENDER_TOPOLOGY=legacy` 逃生门 |

**红线 / 不变量**：①高刷流畅（tick p99 < 50ms，任何活动瞬间回全速）；
②交互语义不回退（菜单/岛/弹弓/探头与旧版逐项一致）；
③轻量化（三宠 WS ≤ 旧三进程 ~400MB，CPU 稳态 ≤ 现状，进程数 3→1）。

## 二、修改文件说明

按子系统分组（行数为该组 `git diff --numstat` 合计；两个专项刀另有逐文件详录，
见关联报告）。新架构代码全部新增模块，旧路径（window.py 等）按「只修崩溃」
维护政策只减不加。

### 实现

| 子系统 | 文件（新增/修改） | 改了什么 + 为什么 | 增/删 |
|---|---|---|---|
| overlay 核心 | `pet/overlay_window.py`、`pet/pet_sprite.py`、`pet/sprite_behavior.py`、`pet/sprite_collision.py`、`pet/sprite_physics.py`、`pet/tick_driver.py`、`pet/tick_governor.py`、`pet/overlay_peripherals.py` | 统一 tick/脏矩形/联合命中/穿透路由；sprite 帧缓存/抛掷/碰撞世界/抛掷物理；TickDriver 两段拆分（仿真与 advance/paint 解耦，M-2）；四档闲置降档（M-1，电池模式卡顿实测驱动）；DPR 归一化渲染（125%/150% 不变糊，D2）；collision_id 单调身份（防地址复用幽灵扫掠） | ≈ +5200 |
| 交互移植 | `pet/sprite_menu_facade.py`、`pet/sprite_menu.py`、`pet/sprite_bubble.py`、`pet/sprite_feeding.py`、`pet/sprite_sound.py`、`pet/sprite_edge_probe.py`、`pet/sprite_throw_egg.py`、`pet/sprite_slingshot.py`、`pet/island_bridge.py` | 右键全菜单（模板感知+缺失条目全补齐+deferred 回调派发）；气泡跟随/快速对话锚点；投喂；音效（后改异步，见修复组）；边缘探头/彩蛋/弹弓/岛墙——旧窗口绑定语义按 sprite 世界重写 | ≈ +4900 |
| 产品壳与生命周期 | `pet/overlay_shell.py`、`pet/overlay_spawn_state.py`、`pet/overlay_instance_gate.py`、`pet/overlay_settings_command.py` | AppShell 挂载层：拓扑分流/屏事件迁移/会话结束链/显隐/托盘聚合/能力 parity；活跃宠清单+无锁身份+位置持久化+主实例提升；双开单实例门；设置指令通道与逐 sprite 路由 | ≈ +2400 |
| 帧序列化 | `pet/frameseq_clip.py`、`pet/frameseq_provision.py`、`tools/convert_frameseq.py`、`pet/library.py`（接入） | 无损 WebP 帧序列播放器（异步预取、进程级共享线程）；首跑自动供给（原子目录/QLockFile/会话闸门/BELOW_NORMAL）；转换器薄壳复用核心 | ≈ +1000 |
| 退役删除（4.4a/4.4b） | 删除 `collision_ipc.py`、`collision_codec.py`、`collision_client.py`、`collision_debug.py`、`instance_launcher.py`、`child_pet_cleanup.py`；`slot_manager.py` 重写保留面；`pet/window.py` 去 CollisionClient 全家；`island_collision.py` 去发布/远端墙；`config.py` 删 `experimental_single_process_spawn` 键 | 多进程多宠层整体退役（T5/T6），机器化守卫锁定「文件不存在+全树零 import」；legacy 路径收窄为捕获模式 | +493 / −4707（另删文件 −4214） |
| T5 默认化 | `pet/overlay_settings_command.py`（env 读取唯一实现）、`pet/app.py` | 默认 overlay 拓扑，`PET_RENDER_TOPOLOGY=legacy` dev 逃生门（不进 Config/设置页/schema） | +30 / −10 |

### 修复（本分支内发现的真缺陷）

| 提交 | 缺陷 | 修法 |
|---|---|---|
| `19048d4` | frameseq 每 clip 一 QThread，clip 销毁撞运行中线程 access violation（test_move_sync 实崩） | 预取线程改进程级共享，clip 只挂 worker |
| `0191195` | 共享预取线程进程退出不收口 → 0xC0000409 尾崩（无 exec() 上下文 QApplication 析构不发 aboutToQuit） | aboutToQuit + atexit 双钩收口，幂等可重建 |
| `a4da423` | **overlay 全屏置顶分层窗使 Windows QUNS 报 BUSY(2)，全屏探测兜底误判 → 宠物 1Hz 自激频闪（soak 日志 64 连翻）** | QUNS 兜底只收 D3D 全屏(3)/演示模式(4)；回归测试 6 条 |
| `c2377c4` | 碰撞/点击音效同步阻塞（winmm 首播 157ms/其后 62ms）卡 tick | 播放移入事件循环下一轮，tick 零阻塞 |
| `d34282a`+`6b0b89e` | frameseq decode 兼容层是普通方法，window/decode_fanout 按属性读 → TypeError 484~546 次/45s | 改 property（与 WebMClip 同形） |
| `3155d7e` | 屏迁移重建 overlay 后点击音效/全量菜单/投喂/穿透回调/位置监听全部丢失（既有缺陷） | 迁移路径全量重挂 + 投喂控制器重建 |

### 测试

新增/重写测试约 +6900 行：`test_overlay_window*`、`test_sprite_*`（行为/碰撞/
物理/菜单/气泡/投喂/音效/探头/彩蛋/弹弓/岛桥/生命周期/设置指令/托盘路由/
菜单 parity）、`test_tick_driver.py`、`test_tick_governor.py`、
`test_frameseq_*`、`test_overlay_spawn*`、`test_overlay_instance_gate.py`、
`test_platform_win_busy_state.py`、`test_architecture.py`（退役守卫×3）。
菜单 parity 测试用**真实 PetWindow** 接线作基准递归比对，防双边同缺。

### 文档

本报告 + 两份专项报告（关联节）+ `docs/INDEX.md` 登记；`.scratch/` 下
FEASIBILITY/HANDOFF/PHASE4_DESIGN（v1.2 M-3 坐标系裁决、v1.3 decode
fanout 决议）为过程文档（gitignored）。

## 三、性能分析

| 指标 | 实测 | 口径 |
|---|---|---|
| 30 分钟碰碰车长稳（offscreen，fling+岛+气泡） | 1800s 零崩溃；**1200 次碰撞**；tick p50 16.04 / p90 17.33 / **p99 42.44ms（<50ms 达标）**；paint p50 0.33 / p99 2.0ms；CPU 24.5% 单核；WS 182.5MB | `run_overlay_demo.py` 指标 JSON，exit 0 |
| 三宠真机稳态（T5 默认拓扑） | WS 359.2MB 采样点（≤ 旧三进程 ~400MB，进程 3→1）；CPU ≈0.66 核（16 核 ~4.1%）。**勘误**：初版「稳定零增长」不成立（采样点误当曲线，原始日志 `.scratch/_cpu_3pet.log` ≈+17MB/min）；斜率收口见瘦身报告，部署版 3h 曲线 193-213MB 才是有效口径 | PowerShell 连续采样，pid 40684 |
| 帧序列化 A/B（系统总账） | webm 68.2% → frameseq 预取版 **59.9%（−12%）**；切动画/首帧 60-166ms → **~2.5ms**；热集 ffmpeg 进程归零（唯一 webm reader 为冷集 random，设计如此） | `.scratch/frame-seq-feasibility/FEASIBILITY.md` |
| 退役删除收益 | `import pet.app` 3394→**1612ms（−52%）**；导入期 tracemalloc 峰值 −13.6MB；`pet.*` 模块 87→81 | DS-13 A/B worktree 同脚本 |
| 音效异步化 | 碰撞 tick 从 ~60ms（同步 winmm）回到正常水位；音效延迟 +<16ms 无感 | 岛桥刀实测 62-157ms 同步阻塞驱动 |
| 菜单建造 | legacy 6.0ms / modern 24.9ms（median，与 PetWindow 4.65/20.3ms 同量级） | DS-14 探针 n=25 |
| 边缘探头 | 关闭态 tick 0.28µs 早退；使能非边缘 8.8µs；渲染角度 0 与改造前同路径 | DS-5 实测 |
| 全量门禁 | **3262 passed / 11 skipped / 0 失败**；ruff 全绿；时序族高负载复跑×3 绿 | 命令与环境见下 |

无新增常驻线程（frameseq 预取共享线程 1 条替代原每宠 reader 线程群）、
无新增系统调用/网络；磁盘代价 = frameseq 热集 +153MB/角色包（首跑后台
转换一次性，webm 保留作回退）。

## 四、实机运行记录

真机（Windows 11，2560×1440，用户日常机，非 CI/mock；配置目录隔离
`%TEMP%\dsh-pet-soak1`，源码直接运行）：

1. **拓扑与渲染**：T5 默认化后无 env 启动即 overlay；宠物渲染/游走/转身/
   随机动作/投喂气泡正常；灵动岛创建、拖拽、dock 检测正常（用户实机参与）。
2. **三宠碰碰车**：右键菜单生小肥鱼×2（活跃清单复活重启后自动回 2 只），
   横跨屏幕拖拽对撞 3 轮——碰撞音效轻重分级（0.90 重/0.45 轻，日志在案）、
   撞翻倒地翻滚、分离无卡死（截图在案）。
3. **弹弓**：拖拽中右键进瞄准（橡皮带可见）→ 松手发射 → 飞行 → 落地静止
   （运行时标记坐标追踪取证）。
4. **右键菜单**：modern 模板（分组+图标：AI 对话/看看屏幕/播放动画/大小/
   音乐/桌宠控制/快捷启动/工具与帮助/Agent 联动/主动识屏/待办提醒/桌宠
   设置/退出这只/退出）与 legacy 扁平模板均真机截图验证——修复了用户举报
   的「设置里是新版菜单、右键却是老版」缺陷（facade 此前硬编码 legacy）。
5. **全屏联动**：用户起全屏游戏（DeltaForce）→ 几何判定命中 → 宠物自动
   隐藏；退出游戏 → 自动恢复。并在此过程抓到 QUNS_BUSY 自激频闪案
   （见修复组 `a4da423`——probe why 串落日志后逐秒归因）。
6. **右键菜单/press 路由**：contextMenu target=True 日志在案；用户本人
   左/右点击均正确路由。
7. **会话结束链**：ISSUE-111 等价闸门（session watcher → 停全部 clip/不
   新起 ffmpeg）offscreen 契约测试 + 既有真机脚本复核。

**未覆盖/已知边界**（诚实登记）：
- 双 painter 重入崩溃案（旧架构 Qt6Gui 族）未结案——观察已按用户要求
  停止；新架构为单 GUI 线程单 backing store，病理面不同，全量门禁
  4 轮 3 绿 1 次 0xC0000374（同族漂移崩溃点）列为上线后观察项。
- 多屏混合 DPR 统一世界未做（M-3 裁决：每屏逻辑坐标，跨屏互撞不做——
  与旧架构可观察行为一致）；跨屏拖拽交接为登记立项。
- 弹弓 Esc 取消在 NOACTIVATE 下依赖应用级事件过滤器（右键取消是可靠
  路径）；弹弓 sprite 形变（瞄准拉伸）未做，数学已备。
- 岛轻撞（60-300）只有 bump 无音效（SpriteSoundPlayer 门槛 300）。
- 部署形态：源码运行验证完毕；打包（PyInstaller onedir）与旧部署目录
  替换属发布动作，待用户点头后执行。
