# 歌词显示审计修复 PR 报告（2026-09-18）

- 分支：`feat/media-window-fallback`（从 `1ff3c39` 起，已 `merge origin/main` @ `1b81fea`）
- base：`main`
- 提交：9 个（`b79add5` … `6708091`）；本轮自有修复 = `e6d5437`（33 files +1305/-203），
  与上游 #134/#135 合并 = `7beac9c` + `6708091`
- 实机验证：重建 webm-chat onedir 并安装到 `H:\dsh-pet-standalone-webm-chat` 后放歌确认

---

## 一、用户现象

> 「歌词确实没有跟着显示，显示了一半就剩下歌名了。每次都是这样。」

拆开是**三个独立问题**，之前只修掉了其中一个，所以现象反复：

1. **只剩歌名**（取词层）：三个歌词源全部失败 ⇒ 每首都被记成「无词」；
2. **只显示一半**（显示层）：多页歌词永远只画第一页；
3. **放着放着没了**（状态层）：单拍采样抖动把整条链路复位、时间轴从 0 秒重唱。

## 二、根因与修复

### 2.1 取词层：系统代理指向一个没在跑的进程（根因）

实机 `ProxyEnable=1`、`ProxyServer=127.0.0.1:33210`，而该进程并未运行。`urllib.request.urlopen`
仍会照系统代理走 ⇒ `ConnectionRefused` ⇒ QQ音乐 / lrclib / 网易云三源全灭 ⇒ `fetch_lyrics`
返回 `None` ⇒ 控制器把这首歌记进 `_no_lyric_keys` ⇒ 气泡只剩「正在听《…》」。

- 新增 `pet/http_util.py`：先按系统代理试一次（尊重用户的加速器/VPN），**只在传输失败时**改直连，
  并把结论固化在进程内（后续请求不再撞死代理）；`HTTPError` 视为链路通，不重试。
- 迁移六处调用：`music_lyric`、`balance`、`vision`、`updater`、`dsh_responder`、`chat/providers`。
  这几处同样会因死代理废掉（余额查询、识屏、AI 对话、更新检查）。
- 实机对照：同一首歌，走代理 0 行；直连 52 / 44 / 31 行（QQ音乐 / lrclib / 网易云）。

### 2.2 显示层：续期把翻页重置了（「只显示一半」的直接原因）

控制器每 500ms 把同一句歌词重发一次用于续期。`PetSpeechBubble.show_text` 每次都
`_reset_paging()` + 从第一页重排，而页码计时器最短 2500ms ⇒ **永远等不到翻页** ⇒ 多页文本只画第一页。

- 新增 `_same_content()` 早退：内容/标题/排版参数都没变时只续隐藏计时器，不重建、不重置翻页。
- 锁宽真正生效：首句量出的列宽存入 `_locked_column`，后续句子沿用（原先 `min_width` 被
  `min(column, 最宽+slack)` 覆盖，长短句宽度不同 ⇒ 气泡左右上下跳）。
- 显示时长与 tick 解耦：`LYRIC_BUBBLE_MS=3000` / `LYRIC_HOLD_SECONDS=3.0`（原先写死 `POLL_MS*2/3`，
  tick 收到 500ms 后缩成 1.0/1.5s ⇒ 抖动一下就「隐藏 → 重现」闪一次）。
- 间奏空行保持上一句：新增 `_lyric_for_index()`，**tick 与取词完成时的即时刷新两个入口都走它**
  （实测撞上的正是后者：刷新那一刻的进度恰好落在空行上）。
- 分页后为空（如 `***`）时回退原始文本单页，正文不留空。

### 2.3 状态层：单拍抖动不再复位

`_MISS_RESET_TICKS` 去抖 + 兜底样本 20s 粘滞（`_WINDOW_STICKY_S`）：单拍 `None` 不再
`_reset()` → 重新取词 → 时间轴从 0 重唱。

### 2.4 选曲：只校验歌手会取到现场版

`_pick_song()`：歌名与歌手**都必须匹配**；同分优先非 Live/重制/伴奏，其次更贴近目标。
实机候选中紧跟着「十年 (Live)」「富士山下 (Live)」。

### 2.5 气泡契约：调用方必须知道「到底显示了没有」

`PetWindow.show_bubble -> bool`（窗口隐藏 / 气泡被抑制 / 提醒占用 ⇒ False），多窗代理透传；
歌词控制器只在返回 True 时记账。否则被提醒让路丢弃的那一拍会被当成「已显示」，
让路与重试逻辑跟着错。

### 2.6 菜单 / 配置 / 日志 / 采样

| 项 | 旧行为 | 现在 |
|---|---|---|
| 暂停 / 切歌 | 随 `music_lyric_enabled` 隐藏 | 随 `now_playing.available()`（关掉歌词气泡照样能用） |
| 切歌 | 绕道歌词控制器，控制器没装配时**点了没反应** | 直达 `now_playing.skip_track()` |
| `music_lyric_cache_limit` | 只在 config 里躺着 | `set_cache_limit()`（下限 50）+ `sync_music_lyric` 接线 |
| `music_player_paths` | 只读、没登记 | 默认值 + 重载白名单 + schema 快照 |
| 设置页歌词开关 | 非 Windows / 没 winrt 也能打开（静默无效） | 按 `available()` 置灰并说明原因 |
| 取词失败 | 只落 DEBUG（发布版看不到） | 全部源失败 WARNING（同因只报一次）、部分失败 INFO |
| 多宠物采样 | 固定 0.3s，每拍窗口枚举 + WASAPI | 无会话超 3s 降到 1.2s，一有会话立刻回快节拍 |
| 死接缝 | `clear_cache` / `resume_playback` / `shutdown` 零调用 | 删除 |

## 三、与上游 #134/#135 的合并口径

上游把同类问题做成了**独立修复线**（同源于 `1ff3c39`），并已 squash 进 `origin/main`（`1b81fea`）。

收下：
- **气泡跟随桌宠**（`_bubble_anchor`）：拖桌宠时气泡不再被钉在旧坐标（实机 bug）。
- **「上一首」菜单项**：改用本分支的 `_skip_track("previous")`（直达播放器）+
  `_media_session_available` 门控。
- **psutil 进程预判 + 依赖声明 + 依赖守卫**：`player_process_running()` 让
  `_play_session_async` 在播放器进程不在时提前返回，绕开那次会永久阻塞的 SMTC 请求；
  #135 顺带把它写进 `requirements.txt`、三个构建脚本 `--collect-all psutil`，并新增
  `tests/test_runtime_dependencies.py`（`pet/` 里 import 了第三方却没声明 ⇒ 红灯）。

不收：
- 上游「控制器内常驻采样线程 + `_playback_ready` 信号 + `shutdown()`」：本分支的采样已在
  `now_playing` 内做成**进程级单例 + 快照**（不阻塞主线程、空闲收摊、卡死摘牌），
  再来一层「每窗一条线程」等于 N 窗 N 线程 + 双份 SMTC 调用；`shutdown()` 也因此不需要。
- 上游 `_run_off_main()`：本分支 `now_playing.toggle_play_pause / skip_track` 内部已是
  `_run_bounded`（工作线程 + 1.5s 上限），主线程本来就不会被 WinRT 卡住。

## 四、测试与验证

- 定向回归（21 个受影响测试文件）：**507 passed / 2 skipped**
- `ruff check pet/ tests/`：全绿
- **缺陷注入 13/13 全部如预期变红**：
  间奏空行保持、同内容续期、歌词锁宽、分页为空回退、选曲歌名匹配、提醒让路返回 False、
  菜单门控、切歌直达、取词日志级别、自适应采样、桌宠移动不钉回、上一首方向、进程预判。
- 测试接缝随传输层迁移：`test_balance` / `test_updater` / `test_vision` / `test_proactive` /
  `test_chat_service` / `test_chat_subsystem` 由打桩 `urllib.request.urlopen` 改为
  `<module>.http_util`（不是产品回归，是接缝过期）。
- 新增测试文件：`tests/test_http_util.py`、`tests/test_music_menu_actions.py`、
  `tests/test_settings_pet_controls.py`。
- 行数预算：`tests/test_architecture.py` 的 `WINDOW_PY_LINE_BUDGET` 4513 → 4518（实测 4517，
  按仓库约定只校准常量并注明日期与理由，不压行）。

### 4.1 实机验证

1. 重建：`build_onedir.ps1 -Variant webm-chat -SkipZip`（须先挂 venv，见交接文档）
2. 安装：旧目录改名做回滚点 → 拷贝 `_internal` + exe → 启动 `--slot 0`
3. 日志确认：`窗口标题监听：…（playing=True）` → `歌词取词完成: Boyce Avenue - Perfect -> 52行`
4. 产物符号确认：`pet.http_util.urlopen` / `_pick_song` / `_lyric_for_index` /
   `_media_session_available` / `_next_sample_interval` / `_report_source_failures`
   全部在 PYZ 内；`_internal/psutil` 在包内。

## 五、已知限制与后续

- 冷门曲目三个源确实可能都没有歌词（日志显示 `0行` 是正常结果，不是失败）；
  这种歌只显示常驻标题。
- 窗口标题兜底会把个别 Electron 应用的窗口标题当成歌曲（多一次无效取词，无副作用），
  后续可加「看着不像歌名就跳过」的过滤。
- `_user_mode_off` 与配置的双数据源按用户要求**不动**。
- LRC `[offset:]` 的符号方向未验证（实机只见过 `[offset:0]`）。

## 六、风险与回滚

- 传输层从「只走系统代理」变成「失败即直连」：若用户依赖代理访问外网（加速器），
  首次失败会切直连并固化；重启进程即恢复「先试代理」。日志有明确 INFO 记录
  （`网络请求改走直连：系统代理不可用（…）`）。
- 显示层改动集中在 `speech_bubble` / `music_lyric_controller`，均有独立单测；
  非歌词气泡（审批/提问/sticky）路径未改语义。
- 安装包回滚：安装前旧目录改名为 `H:\dsh-pet-standalone-webm-chat.bak-<时间戳>`，
  改回名字即可。
