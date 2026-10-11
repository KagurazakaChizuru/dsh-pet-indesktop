# PR 报告：SMTC 视频被当歌曲（媒体类型否决 + 浏览器会话开关）

> **基线**：`0227a6e`（fix/issue-batch-2026-10 分支上本批开始处）
> **分支**：`fix/issue-batch-2026-10`　**日期**：`2026-10-06`
> **范围**：17 个文件（实现 8、测试 6、依赖 1、文档 2）
> **关联**：工单「SMTC 视频被当歌曲」；前置实测见本报告 §五（Chromium 对网页视频
> 恒报 MUSIC 的探针结论）

## 一、核心特性

**现象**：用户在 Edge/Chromium 里播 B 站视频，桌宠气泡显示「我在唱《<视频标题>》」、
去歌词接口取词、还开了唱歌动画。

**根因（实测，非推断）**：`pet/now_playing.py` 只读 SMTC 的 title/artist/album，
只要"有标题 + `playback_status == PLAYING`"就当歌曲；而**浏览器把网页视频也上报成
`MediaPlaybackType.MUSIC(1)`**——本机实测 Edge 与 Chromium（两个独立构建）播放
B 站视频时 `info.playback_type` / `props.playback_type` 恒为 1，且 artist/album/
subtitle 全空、genres 为空，SMTC 里**没有任何字段**能把网页视频与网页音乐分开。

| # | 能力 | 说明 |
|---|---|---|
| 1 | 类型否决（A 腿） | 明确 `VIDEO(2)` 的会话不进唱歌链路：不显示、不取词、不触发动画；`Unknown(0)` 与表外应用照常放行 |
| 2 | 会话分层 | 多会话同播按「音乐 > Unknown > 视频」选会话；视频仍可在只有它在播时被选出，保证 `skip_track` / `toggle_play_pause` 的传输控制在看视频时照常可用 |
| 3 | 浏览器会话开关（B 腿） | 新增设置「浏览器媒体会话参与歌词」（`music_browser_media_enabled`，**默认关**）：关时来自已知浏览器的会话同样不进唱歌链路；打开即恢复旧行为（网页版音乐平台需要它） |
| 4 | 动画门否决制 | `music_detect.is_music_playing` 增加「当前在播的会话被唱歌链路接受」条件；判定由**非主线程**的常驻探针产出，门只读缓存 |

**红线 / 不变量**（不允许被破坏的既有语义）：

- `Unknown(0)`（第三方播放器不上报类型）与**否决表外**的应用一律退回旧行为，不做白名单式误伤；
- 没有 SMTC 会话、或只有暂停会话时，退化成"只看音量峰值"的旧行为（游戏/无会话声音照常触发）；
- **主线程绝不查 SMTC**：唱歌定时器槽只读缓存（主线程同步查 WinRT 会永久阻塞窗口，
  见 `pet/music_lyric_controller.py` 的采样线程说明）；
- `skip_track` / `toggle_play_pause` / `play_session_for` 的会话选择语义不变；
- 读 `playback_type` 一律 `getattr` 兜底：读不到按 Unknown 放行，**绝不**因字段异常
  吞掉整次采样（`_read_async` 的字段兜底是"整次返回 None"，那会退化成"播放器没了"）。

## 二、修改文件说明

### 实现

| 文件 | 增删 | 改动意图 |
|---|---|---|
| `pet/now_playing.py` | +422 / −12 | ① `MEDIA_TYPE_*` 常量、`_MEDIA_TYPE_RANK` 分层表、`_BROWSER_APP_IDS` 否决表；② `normalized_app_id`（去空白/小写/去 `.exe`——实测同一机器上 `Chrome`/`MSEdge`/`cloudmusic.exe` 形状不统一）、`is_browser_session`（表外恒 False）；③ `_SessionSnapshot`（每会话**只读一次** `PlaybackInfo`，类型/状态/来源固化为一份，读取计数从 5 次降回 1 次）、`_read_media_type`/`_read_playback_status`（双兜底，读不到→Unknown/None）；④ `_source_allows_singing`（否决规则本体，唯一一份实现，选择器与动画门共用）+ `_SessionSnapshot.allows_singing`；⑤ **两个选择器语义隔离**：`_pick_playing_session` 保持 HEAD 原样（传输控制：切歌/暂停，不分层不否决），新增 `_pick_singing_session`（唱歌/歌词：**在可接受候选里**分层选，被否决会话在选择阶段出局）；⑥ `_read_async`/`get_now_playing` 新增 keyword-only `allow_browser`，无可接受候选即 `return None`；⑦ 会话探针 `song_session_accepted`/`refresh_session_probe_once`/`_probe_loop`/`_ensure_session_probe`/`reset_session_probe`（常驻后台线程，2s 一拍，缓存**逐会话事实表**，采样有界超时 3s，空闲 8s 自行退出） |
| `pet/music_detect.py` | +57 / −5 | 模块 docstring 改口径（原文"音乐、视频、游戏都会触发"→ 说明"峰值 + 当前会话未被否决"）；新增 `set_browser_media_enabled` / `browser_media_enabled`（宿主每拍推送的开关注入）与 `session_vetoed()`（只读 `now_playing` 缓存，不查 SMTC）；`is_music_playing` 峰值判定后叠加 `not session_vetoed()` |
| `pet/window_alerts.py` | +26 / −0 | 新增 `_push_browser_media_setting(host, music_detect)`：宿主每拍按 cfg 把开关推给 `music_detect`（读配置的地方只有宿主；不另存一份会过期的副本）；`check_music_sing` 在门之前调用它，并补 docstring 说明"为什么这里**不**另加立即退出分支" |
| `pet/music_lyric_controller.py` | +19 / −1 | 新增 `_browser_media_enabled()`（采样线程上读 cfg，脏值/缺失按关）；`_sample_loop` 把 `allow_browser=` 传给 `now_playing.get_now_playing`——否则开关在歌词链路是个摆设；模块 docstring 补"不是所有会话都是歌" |
| `pet/config.py` | +12 / −0 | 新键 `music_browser_media_enabled` 四处登记：默认值 dict（默认 False + 理由注释）、`reload()` 白名单、`_normalize_pet_settings`（走 `_bool_or_default`，防字符串 `"false"` 被 `bool()` 判真把用户关掉的否决又打开）、`set()` 归一化名单 |
| `pet/settings_pet_controls.py` | +9 / −0 |
| `pet/settings_music.py` | +33 / −0 | 新控件 `host.music_browser_media_check`（`ToggleSwitch`，与 `music_lyric_check` 同处构造、同 `setChecked(config...)` 口径） |
| `pet/modern_settings_dialog.py` | +5 / −0（另修改 1 行 claim） | 「音乐关联」组新增 `SettingRow("music_browser_media", ...)`；`claim(...)` 加上该 id（不登记会掉进「待分类（开发期）」，被 `test_settings_interaction_tabs` / `test_menu_layout` 拦下）；`_save` 回写配置。（该文件同时带有其它批次的改动，本批只占上面这几行） |
| `requirements.txt` | +12 / −3 | 新增 `winrt-Windows.Media>=3.0; platform_system == "Windows"` 与理由注释；**修正原注释里过期的打包说法**（见 §六） |

### 测试

| 文件 | 增删 | 覆盖 |
|---|---|---|
| `tests/test_now_playing_media_type.py`（新增） | +834 | 50 例：媒体类型否决（视频不当歌 / 视频不压住音乐 / 视频被跟踪时被抢回 / Unknown 与音乐放行 / 读不到类型按 Unknown 放行）、歌词链路（视频不产「我在唱」、不取词；同播唱音乐）、浏览器开关（开关关=会话被拒、开关开=旧行为、app_id 形状归一、否决表外放行、浏览器不压住暂停的音乐、开关翻转不等探针、采样线程如实传参）、动画门（视频不触发、音乐/Unknown 触发、无会话维持音量触发、判定缺失放行、暂停会话不否决、唱歌中切视频/浏览器（开关关）必须停且不重开） |
| `tests/test_architecture.py` | +10 / −1 | `MODERN_SETTINGS_DIALOG_PY_LINE_BUDGET` 2403 → 2407：设置行主体最终落在 `settings_music.py`，该文件只净增设置行注册与回写，实测 2407。按该文件既有约定"只随实测校准、不为达标压行"补日期注释 |
| `tests/test_config_schema.py` | +1 / −0 | reload 白名单快照加入新键（新增键漏登记立即红的护栏） |
| `tests/test_now_playing_session_probe.py`（新增） | +280 | 8 例：**探针线程与生命周期契约**——OS 请求发生在探针线程（调用线程零 SMTC）、缓存读零 OS 请求、空闲期限自行退出、采样异常不打死线程、挂起请求有界收口、退出后可重启、常量契约（有限且次序合理）、端到端事实→否决 |
| `tests/test_music_player_settings.py` | +55 / −0 | 浏览器会话开关的**平台契约** 3 例：非 Windows 不出设置行（平台闸门优先于控件存在）、控件缺失时行也不建、控件本体只在 Windows 创建且保存路径安全跳过 |
| `tests/test_music_lyric.py` | +2 / −1 | 既有 `fake_get_now_playing(tracked_app_id=None)` 改为接受 `**kwargs`：采样线程现在还会传 `allow_browser`，旧桩会 `TypeError` 被采样线程的 `except` 吞掉，表现为"开启后不采样"（1 行适配，断言不变） |

### 未改动（明确说明，避免误以为漏了）

- **`scripts/build_onedir.ps1` / 打包脚本**：按任务书要"登记 PyInstaller
  hiddenimports"，实测**不需要**，故意不动（证据见 §五·4）。
- `pet/overlay_shell.py`、`pet/window_optional_services.py`、`pet/window.py`：
  两条拓扑的唱歌/歌词链路都经 `window_alerts.check_music_sing` 与
  `MusicLyricController`，开关从 cfg 就地读取，无需在宿主机上新增接线。
- `pet/music_players.py`：播放器路径探测与本次判定无关。

## 三、实现要点

1. **否决规则只有一份实现**：`_source_allows_singing(media_type, browser, allow_browser)`。
   两个入口语义刻意不同并写进 docstring：采样层（歌词）**不看**会话是否在播——
   暂停的视频/浏览器会话同样不该被当成歌曲显示；动画门**要求**会话在播——出声的
   可能是游戏或不上报 SMTC 的播放器，此时按会话存在与否决会误伤（用户后台挂着一个
   暂停的 B 站页签就再也不唱歌）。
2. **会话分层与传输控制**：两个选择器语义**隔离**——`_pick_playing_session`
   保持 HEAD 原样（不分层、不否决），`_pick_playback_session`（`skip_track` /
   `toggle_play_pause` 用）继续走它，看视频时点暂停仍然暂停视频；唱歌/歌词独享
   新增的 `_pick_singing_session`——被否决会话在**选择阶段**就出局，只在可接受
   候选里分层选（音乐 > Unknown > 视频），不是"先选赢家再否决"（那会让被否决的
   浏览器会话压住同播的表外音乐播放器）。
3. **线程模型**：探针是**常驻**线程（不每拍新建——winrt 按线程初始化 COM
   apartment，每拍新建会累积句柄，仓库已有同类教训）。它缓存的是**逐会话
   事实表** `((媒体类型, 是否浏览器, 是否在播), …)`，而不是最终判定：
   开关改动因此在下一拍读取时立刻生效，不必等探针重采（有专门用例钉住）。
4. **为什么 `check_music_sing` 里没有"立即退出"分支**：先写过一版显式否决分支
   （视频/浏览器立刻停唱），实测它会让"只桩 `is_music_playing` 的既有用例"
   （`test_music_sing_grace` / `test_music_sing_timer` / `test_overlay_music_sing`
   共 7 条）绕过桩直接读到**真实 SMTC**——本机开着浏览器视频时那批用例就红。于是
   否决只留在 `music_detect` 一处，退出走既有的 6s 静音宽限期（"必须停、不重开"
   仍然成立，有 `test_video_session_ends_singing_already_started` 钉住）。
5. **开关的 schema 与设置页位置**：
   - 键名 `music_browser_media_enabled`，域=「桌宠」页的「音乐关联」组，
     设置行 id `music_browser_media`，标签「浏览器媒体会话参与歌词」，
     `ToggleSwitch`，默认 **False**，`commit_policy=**on_finish**`（「保存并退出」批量回写，
     与同组其它音乐键一致——本批先前写成 immediate 是错的，已更正）；
   - 归一化：`_bool_or_default(..., False)`，`set()` 与 `reload()` 双路生效；
   - 前端消费点两处：歌词采样线程（`MusicLyricController._sample_loop`）与
     动画门注入（`window_alerts._push_browser_media_setting`）；
   - slot 说明：**落盘后**生效，无需重启、也不需要额外刷新钩子——两条消费链
     （歌词采样线程 / 动画门注入）都**每拍重读 cfg**（`_browser_media_enabled()`、
     `_push_browser_media_setting()`），所以没有缓存副本要失效；
   - 平台：**仅 Windows** 创建控件与设置行（SMTC 是 Windows 专属能力），
     非 Windows 上该行不出现、保存路径安全跳过（值本身与平台无关，换平台不丢）。

## 四、性能分析

**环境**：Windows 11 / Python 3.13 / PySide6 / winrt 3.2.1 / PyInstaller 6.22.2，
本机真实 SMTC（存在 1 个浏览器会话）。命令均为
`cd D:/dsh-pet-src-wt-issues && PYTHONPATH=D:/dsh-pet-src-wt-issues python <脚本>`。

| 指标 | 实测 | 归属 |
|---|---|---|
| `is_music_playing()`（真机、峰值表已热） | min 51.1µs / **median 53.7µs** / max 161.6ms（n=200，max=首次 `_get_meter()` 的 COM Activate，既有行为） | 既有热路径（主线程，1s 一拍） |
| 本批新增的主线程开销：`song_session_accepted()` 缓存读 | min 0.5µs / **median 0.6µs** / max 20.7µs（n=500） | **新增**，占既有单拍 53.7µs 的 ≈1.1% |
| `refresh_session_probe_once()`（一次 SMTC 采样） | min 3.84ms / **median 4.72ms** / max 7.37ms（n=20） | **新增**，每 2s 一次（0.24% 占空），跑在后台线程 |
| `get_now_playing()`（对照） | min 3.68ms / median 4.77ms / max 6.38ms（n=20） | 既有 |
| 探针节奏（门每 1s 问一次，连续 7s） | 询问 7 次 / 采样 **3 次**（TTL=2s，符合预期） | 新增 |
| 唱歌功能关掉后（停止询问） | 探针 **7.5s 内自行退出**，线程数 2→1，缓存清空 | 新增（不留常驻轮询） |
| 内存：WinRT 首次加载（任何 SMTC 调用） | ΔRSS +10.0MB / **ΔUSS +1.60MB**（对照：本批探针运行中 ΔRSS +10.1MB / ΔUSS +1.84MB） | 探针线程自身 ≈ **+0.24MB USS**；其余是 WinRT 栈加载 |
| 新增网络 / 磁盘 | 0 / 0（未做系统调用级追踪，不将该项记作已验证的 0）；新增 1 条 daemon 线程（仅在唱歌功能开启时存活），它每 2s 发起一次 SMTC（COM/WinRT）查询——这是本批的新增 OS 交互，量级已在上表实测 | 新增 |

**逐项回答**：

- **稳态开销**：唱歌功能开启时，主线程 +0.5µs/拍（1s 一拍），后台 +5ms/2s；
  功能关闭后探针自行退出，回到改动前的形状（0 额外线程、0 额外 SMTC 调用）。
- **新增路径成本与触发频率**：探针每 2s 采一次 SMTC，与既有歌词采样（1s 一次）
  同一量级；两者都开启时是两条常驻线程（各 1 个 COM apartment，**不随拍增长**）。
- **内存**：探针线程自身增量 ≈0.24MB USS（线程栈为保留地址空间，实测 USS 增量）。
  **需要说明的取舍**：在"开着自动唱歌、但从未开过歌词"的配置下，本批让该进程
  首次加载 WinRT（ΔUSS ≈1.6MB / ΔRSS ≈10MB）——这是"读 SMTC 才能否决"的必然
  成本，替代方案（主线程查 SMTC）是不可接受的（会阻塞窗口）。

## 五、实机运行记录

**1）真实 SMTC 读取（本机，用户 Edge 有一个暂停的 B 站会话）**

```
$ python /tmp/smtc_live_verify.py
=== 0) 真实 winrt 能否读出 playback_type ===
  app_id='MSEdge' info.playback_type=1 props.playback_type=1 status=5 title='什么？deepseek v4.1，kimi k3免费了？…'
=== 1) 采样层：开关开（旧行为）===
  -> Playback(track=Track(title='…-快乐小咸鱼a-稍后再看-哔哩哔哩视频', artist='', album='', duration=188.0, playing=False), app_id='MSEdge')
  app_id = MSEdge | is_browser_session = True | playing = False
=== 2) 采样层：开关关（本次新增口径）===
  -> None        # 该浏览器会话被唱歌链路拒绝
=== 3) 动画门探针：真实会话事实 ===
  facts = (True, 1, True, False)      # (有会话, 媒体类型=MUSIC, 是浏览器, 未在播)
  song_session_accepted(allow_browser=True)  -> True
  song_session_accepted(allow_browser=False) -> True   # 未在播 → 不否决（设计如此）
=== 4) 动画门（峰值用假表=系统在出声，判定用上面真实事实）===
  浏览器开关=False -> is_music_playing() = True (session_vetoed=False)
```

→ 任务的验收点"pip 装包后真读一次本机 SMTC、确认 `playback_type` 读取正常、
开关关时该会话被唱歌链路拒绝"**已达成**：类型读取为 1(MUSIC)，采样层
`allow_browser=False` 返回 `None`（拒绝）。

**2）探针生命周期（真机，见 §四两行"探针节奏 / 自行退出"）**：门问 7 次、探针采
3 次；停止询问后 7.5s 内线程退出且缓存清空。

**3）打包侧（PyInstaller 6.22.2，最小可复现构建，三次）**

- `probe_noflag`：只 static import `winrt.windows.media.control`（与产品同形），
  **不加任何 collect/hiddenimport** → 产物内
  `_internal/winrt/windows/media/__init__.py` 在包内，frozen 程序打印
  `RESULT: ['MSEdge pt=1']`，`type(info.playback_type)` =
  `<enum 'MediaPlaybackType'>`（`probe3_noflag` 实测）。
- `probe_collectall`：加 `--collect-all winrt` → 同样 `pt=1`。
- 结论：**不需要新增打包登记**。原 `requirements.txt` 里"winrt 是 namespace
  package，需在 hiddenimports 里登记子模块"的说法在本仓库从来没有对应的实现
  （构建脚本里没有任何 winrt 条目），且本包此前打包版 SMTC 一直可用——本批把它
  改成实测口径（依赖必须声明，collect 不需要），见 §二 requirements.txt 那行。

**4）聚焦测试（全部在本机跑；数字为第二轮修正后的最终快照）**

```
$ QT_QPA_PLATFORM=offscreen python -m pytest <16 个文件> -q -p no:randomly
383 passed   # now_playing_media_type(50) / now_playing_session_probe(8) /
             # now_playing_session / music_detect / music_lyric / music_sing_grace /
             # music_sing_timer / overlay_music_sing / music_player_cache /
             # music_player_settings / config_schema / config_instance /
             # architecture / menu_layout / settings_interaction_tabs /
             # pr_report_discipline
$ QT_QPA_PLATFORM=offscreen python -m pytest <再加 4 个文件> -q -p no:randomly
515 passed   # 追加 behavior_detector / feature_gating / app_lazy_imports /
             # desktop_pet_features
$ QT_QPA_PLATFORM=offscreen python -m pytest tests -q -k "music or now_playing or settings or overlay_music or config or architecture"
671 passed, 3793 deselected   # 广选（含既有 7 条"只桩 is_music_playing"的唱歌用例）
$ python -m ruff check .     → All checks passed!
$ git diff --check           → 干净
```

**红→绿证据**：

- 原 15 例（A 腿）在**任何产品改动之前**即红：`10 failed, 5 passed`，失败断言示例
  `AssertionError: [('', '我在唱《什么？deepseek v4.1…哔哩哔哩视频》')]`（工单现象被
  逐字复现）；产品改动后 15/15 绿。
- B 腿（浏览器开关）+ 门改口径与实现同批交付，因此没有"功能前的语义红"：
  它们在基线上无法运行（`AttributeError: music_detect.set_browser_media_enabled`，
  基线整文件 errors，属夹具前置缺失而非语义红）。它们的防回归意义由
  `test_table_external_app_is_not_treated_as_browser`、
  `test_non_video_session_still_counts_as_song`、
  `test_no_smtc_session_keeps_volume_trigger`、`test_gate_allows_while_verdict_missing`
  等"必须继续绿"的守卫承担。
- 既有 7 条"只桩 `is_music_playing`"的唱歌用例（grace 5 / timer 1 / overlay 1）
  **未做任何修改即保持绿**——这是否决只留在 `music_detect` 一处的原因（见 §三·4）。
- **第二轮（6.1sol 审查）的 5 条语义缺陷**：P1 同播误伤、P2 传输控制、P2 挂起无界、
  P2 平台契约、P2 往返次数全部**先复现**（`/tmp/repro_review.py`，
  与 HEAD 基线对照），修后各有专门回归；线程与生命周期那 4 项**无测试覆盖**的退化，
  由新增的探针契约用例 ＋ 8/8 消融矩阵钉住（见 §七）。

## 六、遗留与未验证

1. **原生播放器上报 VIDEO(2) 在本机未实测**：本机没有安装任何原生视频播放器
   （VLC / PotPlayer / MPV 均无），且唯一能造出视频播放的途径是浏览器（恒报 MUSIC）。
   即"类型否决"这条路在本机**零命中**，工单标题现象靠 B 腿（浏览器开关）解决。
   建议在有原生播放器的机器上补一次探针。
2. **网页版音乐平台用户需要打开开关**：默认关意味着浏览器里的音乐（含网页版网易云）
   不再显示歌词，这是产品取舍（口径已拍板）。设置页提示文案已写明。
3. **未跑全量**：按本阶段分工，全量 pytest 由主代理统一执行；本批只跑聚焦集（当前
   快照：16 文件聚焦 **383 passed**，广选 `-k` **671 passed**）。`window.py` 无改动，但 `music_detect` / `window_alerts` 是共享面，
   全量仍是合并前门禁。
4. **暂停的浏览器/视频会话不否决**：这是刻意选择（见 §三·1）。副作用：后台挂着一个
   暂停的 B 站页签时，桌宠对游戏声音仍会唱歌（= 旧行为）。
5. **`session_vetoed()` 的"无数据=放行"窗口**：功能刚开启的前一两拍（探针首拍之前）
   可能按旧行为唱一下再停；判定过期窗口 4s。设计上以"不误伤"优先。

---

## 七、第二轮修正（6.1sol 审查，2026-10-06）

审查提出的 6 条问题**全部先独立复现、再修**（复现脚本 `/tmp/repro_review.py`；
传输控制另与 HEAD 基线对照跑，基线代码取自 `git show HEAD:pet/now_playing.py`）。
结论：P1、P2-传输、P2-挂起、P2-往返、P2-平台 五条属实并已修；P2-线程约束属
**测试盲区**（当前实现行为本身正确，但没有用例能拦住退化），已补 8 例并对全部
8 项机制做了消融验证。

### 7.1 逐条：复现 → 修法 → 回归

| # | 问题 | 复现证据（修前） | 修法 | 回归用例 |
|---|---|---|---|---|
| P1 | 同播误伤：分层先选出浏览器（报 MUSIC）再否决，压住同播的表外音乐播放器 | 浏览器(MUSIC,在播)+LX Music(Unknown,在播)、开关关 → **两种枚举顺序都返回 `None`**（音乐在播却"没有歌"，歌词/动画整条消失）；浏览器+QQ音乐两种顺序结果不一致（`None` vs QQ音乐） | 新增 `_pick_singing_session`：**被否决会话在选择阶段出局**，只在可接受候选里分层；只否决赢家的写法彻底删除 | `test_rejected_browser_does_not_shadow_unknown_type_player`、`…_music_type_player`、`test_browser_video_does_not_shadow_paused_music`（断言改为"选中网易云那条会话"） |
| P2 | 传输控制语义被传递改变：VLC视频+网易云同播，HEAD 控制 VLC、工作树控制网易云 | HEAD 基线：VLC 在前→`vlc.exe`、网易云在前→`cloudmusic.exe`、tracked=VLC 在播→`vlc.exe`；工作树（修前）：两种顺序**都**→`cloudmusic.exe` | `_pick_playing_session` 恢复 HEAD 原始逻辑（不分层、不否决），`_pick_playback_session`（`skip_track`/`toggle_play_pause`）继续用它；唱歌链路独享 `_pick_singing_session` | `test_transport_control_keeps_head_semantics`（3 例：两种枚举顺序 + tracked 粘在视频上） |
| P2 | WinRT 挂起无界：`asyncio.run(_facts_async())` 无超时，探针被钉死到进程结束 | 持续询问 1s 让探针进采样，再停问 3s（空闲上限 0.3s）→ **线程仍存活**；线程列表仍有 `smtc-session-probe` | 新增 `_facts_async_bounded`（`asyncio.wait_for`，`SESSION_PROBE_TIMEOUT_SECONDS=3.0`＝正常采样 ~5ms 的 600 倍余量）；超时/异常一律写"无会话"（放行）并**把控制权交回探针循环** | `test_hung_os_request_is_bounded_and_probe_can_exit`（挂起下采样在超时量级内收口；空闲后退出） |
| P2 | 线程约束无测试：把 `_ensure_session_probe` 换成同步查、空闲退出改 `inf`，原 45 例仍全绿 | 消融验证：A1/A2a/A2b 在补测前**无任何用例变红** | 新增 `tests/test_now_playing_session_probe.py`（8 例）＋常量契约断言（有限性/次序） | 见 7.2 消融矩阵（A1–A4 全部 RED） |
| P2 | 平台契约：非 Windows 该开关显示可用但无效果 | 设置行附近无任何平台条件（脚本检查 False） | 控件与设置行**只在 Windows 创建**（`settings_pet_controls` 条件建 ＋ `settings_music.browser_media_rows` 平台闸门），非 Windows 保存路径安全跳过；与 `cursor_hidden_passthrough` 同一先例 | `test_browser_media_row_is_absent_on_non_windows`、`…_when_widget_missing`、`test_browser_media_widget_is_windows_only` |
| P2 | 保存契约不实：报告写 immediate，实际 on_finish | 读 `_save()`：写入发生在「保存并退出」（`_write_config` ＋ `accept`），与同组音乐键一致 | **改报告如实为 on_finish**（选"随大流"而不是改行为），并写清"落盘后两条消费链每拍重读 cfg，无需重启/刷新钩子" | 报告 §三·5 已更正 |

### 7.2 消融矩阵（8/8 逐条可判别）

做法：在**仓库副本**里（`/tmp/dsh-ablate`，不动工作区）逐条把机制改回退化版，
跑其守护用例，期望变红。命令：
`python /tmp/run_ablation_full.py`（每项 `pytest <case> -q -p no:randomly`，
每项 150s 上限，超时按"用例挂住 = 红"计）。

| # | 消融（把机制改回退化版） | 守护用例 | 结果 |
|---|---|---|---|
| A1 | 门不再起探针线程，改成调用线程**同步采样** | `test_os_request_happens_on_probe_thread_not_the_caller` | **RED ✓** 1 failed |
| A2a | 去掉空闲退出分支（`if False: break`） | `test_probe_exits_after_idle_deadline` | **RED ✓** 1 failed |
| A2b | 空闲期限改成 `math.inf` | `test_probe_constants_are_finite_and_ordered` | **RED ✓** 1 failed |
| A3 | 采样去掉有界超时（`wait_for` → 直调） | `test_hung_os_request_is_bounded_and_probe_can_exit` | **RED ✓** 1 failed（5.5s，快速失败而非挂死进程） |
| A4 | 采样异常不再兜住（让异常打死线程） | `test_probe_survives_sampling_errors_and_still_exits` | **RED ✓** 1 failed |
| A5 | 唱歌选择退回"先选赢家、不过滤候选" | `test_rejected_browser_does_not_shadow_unknown_type_player` | **RED ✓** 1 failed |
| A6 | 传输控制退回"按媒体类型分层"（即 P2 原缺陷） | `test_transport_control_keeps_head_semantics` | **RED ✓** 1 failed |
| A7 | 平台闸门失效（非 Windows 也出设置行） | `test_browser_media_row_is_absent_on_non_windows` | **RED ✓** 1 failed |

两条由消融逼出来的加固（都已落地）：

- A2b 第一次跑是 **GREEN**——行为用例靠 `monkeypatch` 把期限调快，所以"默认值被
  改成 `inf`"根本进不到断言里（而它等价于"探针永不退出"）。补 `test_probe_constants_
  are_finite_and_ordered`：用 **import 期抓下的真实默认值**断言有限性 + 次序
  （`ttl < idle`、`timeout < idle`、`stale >= ttl`）。
- A3 第一次跑是 **TIMEOUT**（用例自己挂在无超时的采样里）——把那次调用放进工作
  线程、`join(预算)` 后断言"跑完了"，于是消融变成 5.5s 的**失败**而不是挂死进程。

### 7.3 报告修正项（②–⑤）

| 项 | 原文 | 更正为 |
|---|---|---|
| ① `requirements.txt:28` | 「winrt 是 namespace package，需在 hiddenimports 里登记子模块，否则 PyInstaller 会漏收」——与 §五·3 的实测结论自相矛盾 | 删除该断言，改成实测口径（winrt 子模块由静态 import 连带收集；复验证据指向 `winrt-Windows.Media` 条） |
| ② WinRT 往返陈述 | `_read_media_type` 注释称"不增加任何 WinRT 往返"——**不实**：单会话一次采样实测 5 次 `get_playback_info`（HEAD 基线 2 次：类型排名重复读 2 次 + 否决再读 1 次 + …） | 引入 `_SessionSnapshot`（每会话只读一次、类型/状态共用），**实测降到 1 次**（比 HEAD 还少：选会话时那次读取的结果被 `_read_async` 复用）；注释与报告同步为实测口径，并加回归 `test_session_read_count_is_not_inflated` |
| ③ 文件计数 | 「9 个文件（实现 6、测试 4、依赖 1）」 | 「17 个文件（实现 8、测试 6、依赖 1、文档 2）」（按 `git diff --numstat` 快照） |
| ④ 新测试行数 | 732 行 | 834 行（本轮追加 P1/P2 回归后；另有新增的探针契约文件 280 行） |
| ⑤ 聚焦集用例数 | 300 passed | **383 passed**（16 个文件：now_playing×3 / music×7 / config×2 / architecture / menu_layout / settings_interaction_tabs / pr_report_discipline） |

### 7.4 诚实边界（本轮新增）

- **`asyncio.wait_for` 只能中断 `await`，不能抢占同步阻塞在 C 层的 WinRT 调用**：
  若某个 WinRT 调用在扩展模块里硬阻塞不返回，超时对它无效（协程已被取消，但那个
  本地调用仍占着线程度过）。此时探针线程仍会随进程退出（daemon），且该情形下
  "空闲自行退出"不再成立。本机无法构造这种真实调用，故只做了 `await` 挂起的
  复现与收口；这条限制在此如实登记。
- 修 P1 后，`_read_async` 在"只有暂停的可接受会话"时返回的是那条**暂停**会话
  （而不是 `None`）——与 HEAD 的"没在播就留在跟踪对象上"一致，歌词不会凭空消失，
  只是不推进。
