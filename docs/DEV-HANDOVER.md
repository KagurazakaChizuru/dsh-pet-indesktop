---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: e1503192c50cbf4a9392ca071882b90f_2224d681b1ac11f18304525400aeaaa3
    ReservedCode1: TrlaPk8+8DyPYWqqXjy/EmDYoYvGBu/wSMjmQpPImYGkIToIR0wv2LQdmKwTxfOMK9N5B7W9+qUE59uhRk4OEB0s1ORks5uevjNiDa/QhBzR21+azdIhQN+GEoKpWz4WqQAMt+DAnEi80ETLWFZUuvr6YeSXxoomEQ6vNKjkzaOYzZL+YNBv5BL8RDY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: e1503192c50cbf4a9392ca071882b90f_2224d681b1ac11f18304525400aeaaa3
    ReservedCode2: TrlaPk8+8DyPYWqqXjy/EmDYoYvGBu/wSMjmQpPImYGkIToIR0wv2LQdmKwTxfOMK9N5B7W9+qUE59uhRk4OEB0s1ORks5uevjNiDa/QhBzR21+azdIhQN+GEoKpWz4WqQAMt+DAnEi80ETLWFZUuvr6YeSXxoomEQ6vNKjkzaOYzZL+YNBv5BL8RDY=
---

# dsh-pet 开发交接文档（DEV-HANDOVER）

> 面向对象：接手本项目（含「语音报时」「节日提醒」定制功能）的开发者。
> 目标：通读本文即可完成本地运行、改配置、加功能、跑测试、重新打包的全流程，不踩已知的坑。
> 基线：上游 `main` @ `1b81fea`（#135 合并提交，内含 #134）。**已合并**的自有功能：语音报时 #118（`3cf70bc`）、语音报时 v2 #125（`eeb29bb`）、节日提醒 #127（`be9a6d0`）。
> 上一轮（2026-09-17，节日动画 + 用户生日）：分支 `feat/festival-reminder-v2`，提交 `b79add5`，PR #131。
> 本轮（2026-09-18，「歌词显示审计修复」）：分支 `feat/media-window-fallback`（从 `1ff3c39` 起，已 `merge origin/main`），
> 9 个提交（`b79add5` … `6708091`）：自有修复见 `e6d5437`（33 files +1305/-203），承接上游 #134/#135 见 `6708091`。
> 详见 `docs/PR-REPORT-LYRIC-DISPLAY-AUDIT-2026-09-18.md`（含根因、验证与合并口径）。
> 生成日期：2026-09-17（本行于 2026-09-18 校准基线与本轮信息）。文档内的数字均为实测值，代码改动后请同步校准。

---

## 〇、最近一轮：歌词显示审计修复（2026-09-18）

用户现象：「歌词确实没有跟着显示，显示了一半就剩下歌名了。每次都是这样。」

根因与修复（本地两批 + 与上游 #134/#135 合并）：

1. **取词全军覆没（根因）**：系统代理被加速器打开但进程没在跑（实机 `ProxyEnable=1` → `127.0.0.1:33210` 无人监听），
   `urllib` 仍照代理走 ⇒ QQ音乐 / lrclib / 网易云三个源全部 `ConnectionRefused` ⇒ 每首歌都被记成「无词」⇒ 气泡只剩歌名。
   新增 `pet/http_util.py`（先按系统代理试，传输失败改直连并把结论固化在进程内），歌词、余额、识屏、AI 对话、
   更新检查六处统一改走它。
2. **显示层**：歌词每拍续期不再重置翻页（`_same_content`）——这是「只显示一半」的直接原因；锁宽真正生效
   （`_locked_column`）；显示时长与 tick 解耦（`LYRIC_BUBBLE_MS=3000`，原先随 `POLL_MS` 缩到 1s 会闪）；
   间奏空行保持上一句（`_lyric_for_index`，tick 与取词完成即时刷新两个入口都走它）；分页为空时回退原始文本。
3. **选曲**：新增 `_pick_song`，歌名与歌手都必须匹配，同分优先非 Live/重制/伴奏（原先只校验歌手，
   实机候选中紧跟「十年 (Live)」，取到现场版时间轴整首错位）。
4. **气泡契约**：`PetWindow.show_bubble -> bool`（隐藏/被抑制/提醒占用 = False），多窗代理透传；
   歌词控制器只在 True 时记账，不再把「没显示」当「已显示」。
5. **菜单 / 配置 / 日志 / 采样**：暂停与切歌不再随歌词开关隐藏（改看 `now_playing.available()`）；
   切歌直达播放器（原先绕歌词控制器，歌词关着时**静默无效**）；`music_player_paths` 与
   `music_lyric_cache_limit` 接线生效；取词失败提升为 WARNING（同因只报一次）；多宠物空转降档
   （0.3s → 1.2s）；删死接缝 `clear_cache` / `resume_playback` / `shutdown`。
6. **与上游合并**：收下 #134 的「气泡跟随桌宠」（`_bubble_anchor`，拖桌宠时气泡不再停在原地）与
   「上一首」菜单项、#135 的 psutil 进程预判 + 依赖声明 + `tests/test_runtime_dependencies.py` 守卫；
   **不采纳**上游「每窗一条常驻采样线程 + `_playback_ready`」的第二套采样（本地已在 `now_playing` 内做
   进程级单例 + 快照 + 空闲收摊 + 卡死摘牌），其 `shutdown()` 亦不需要。

验证：定向回归 **507 passed / 2 skipped**；`ruff check pet/ tests/` 全绿；缺陷注入 **13/13** 变红。
构建：`$env:PATH = 'D:\dsh-pet\.venv\Scripts;' + $env:PATH` 后执行
`& .\scripts\build_onedir.ps1 -Variant webm-chat -SkipZip`（不挂 venv 会让 `python` 命中商店占位符 ⇒
`make_icon failed: 9009`），安装到 `H:\dsh-pet-standalone-webm-chat`（旧目录先改名做回滚点）。

---

## 一、项目概况

### 1.1 项目定位

- **形态**：Windows 桌面宠物（桌宠），角色「深深」——蓝色大肥鱼；PySide6 编写的无边框透明窗口，播放 WebM/GIF 动画，支持拖动、碰撞、边缘探头、彩蛋、气泡说话、AI 对话（Chat 版）、待办提醒、**语音报时（本次定制重点）**。
- **语言/框架**：Python 3.11+（`pyproject.toml` 的 ruff target 为 `py313`），UI 全部 PySide6（Qt6）。
- **源码位置**：`D:\dsh-pet`（本文档所在仓库）。
- **上游**：`dsh-pet-indesktop`（开源项目，见 `README.md`、`LICENSE`、`THIRD_PARTY_NOTICES.md`），本项目在其基础上做定制扩展。

### 1.2 运行环境与依赖

`requirements.txt`（运行时 + 开发依赖）：

```
PySide6>=6.5
imageio-ffmpeg>=0.6
Pillow>=10
keyring>=25
certifi>=2024.0.0
pycaw>=0.0.13; platform_system == "Windows"
tzdata>=2024.1
pytest>=8      # 开发依赖
ruff>=0.5      # 开发依赖（仅 F 级规则，见 pyproject.toml）
```

- **语音合成额外依赖 edge-tts**：代码运行时按需导入（`voice_chime_service.py` 内惰性导入），未安装时功能降级为「只有气泡、没有声音」。若需完整语音能力：

  ```powershell
  pip install edge-tts
  ```

- **重要环境注意**：本机控制台默认 GBK，直接用 `Get-Content` 读 UTF-8 源码会显示乱码（文件本身正常）。排查源码请加编码参数：

  ```powershell
  Get-Content pet\voice_chime.py -Encoding UTF8
  ```

### 1.3 目录结构总览

```text
D:\dsh-pet\
├── AGENTS.md                     # 工程纪律（必读：变更纪律、CI 成本纪律、context pointers）
├── CONTEXT.md                    # 领域术语表（Shared UX Contract / Settings System / Menu Action Model）
├── README.md                     # 用户向说明 + 开发结构 + 测试与验证 + 打包发布
├── requirements.txt / pyproject.toml / pytest.ini
├── run.bat                       # 本地源码启动脚本
├── dsh-pet-standalone-webm-chat.spec   # PyInstaller 规格（onedir）
├── pet\                          # 应用源码（128 个 .py，含子包）
│   ├── __main__.py               # 入口：python -m pet
│   ├── app.py                    # AppShell / PetInstance：进程级与每窗装配（2751 行）
│   ├── window.py                 # 桌宠主窗口（组合根，4507 行，顶满行数预算红线 4507）
│   ├── config.py                 # 配置读取/清洗/迁移/持久化（1436 行）
│   ├── config_domains.py         # 配置域 facade（chat/agent_link/proactive/collision/menu）
│   ├── modern_settings_dialog.py # 现代设置主对话框（2311 行，预算 2311，零余量）
│   ├── settings_widgets.py       # 设置控件库（ToggleSwitch / SettingRow / ModernSelect …）
│   ├── speech_bubble.py          # 气泡绘制与交互（1160 行）
│   ├── speech_bubble_text.py     # 气泡分页/定位纯函数（272 行）
│   ├── voice_chime.py            # ★ 语音报时纯逻辑层（460 行，零 Qt / 零 edge_tts）
│   ├── voice_chime_service.py    # ★ 语音报时服务层（506 行，tick + 合成 + 播放）
│   ├── voice_chime_settings.py   # ★ 语音报时设置页（250 行）
│   ├── voice_chime_quotes.py     # ★ 台词/歌词纯数据库（96 行，中英各 40 条）
│   ├── festival.py               # ★ 节日提醒纯逻辑层（395 行，零 Qt）
│   ├── festival_data.py          # ★ 节日定义表 + 动态生日节日（158 行）
│   ├── festival_animations.py    # ★ 节日 -> 动画映射（226 行，零第三方依赖；三级降级）
│   ├── festival_service.py       # ★ 节日提醒服务层（279 行，30s tick + 气泡/语音/动画）
│   ├── festival_settings.py      # ★ 节日提醒设置页（379 行；13 个配置键行 + 试听行）
│   ├── context_menus\            # 右键菜单（registry.py 动作注册 + legacy/modern/fun_entry）
│   ├── menu_templates\           # 菜单布局 JSON（modern-default-v1.json 为默认模板）
│   ├── chat\                     # AI 对话子系统（Chat 版打包变体）
│   └── persona_presets\          # 角色台词预设
├── scripts\                      # 构建/校验脚本（build_onedir.ps1、slim_bundle.py 等 20 个）
├── packaging\                    # PyInstaller 入口 + Inno Setup 脚本（dsh-pet.iss）
├── tests\                        # 129 个 py 测试文件 + tests\helpers\ 辅助模块 + 7 个 bridge js 测试
├── docs\                         # 46 篇工程文档（含本文件）
├── assets\                       # 动画素材、图标
└── dist-onedir\                  # 构建产物：dsh-pet-standalone-webm-chat\（目录）+ portable zip（146.53 MB，2026-09-16 18:06 生成）
```

**目录状态说明**：`build-onedir\`、`build\`、`dist\`、各 `__pycache__`、`.pytest_cache`、`.ruff_cache` 等可再生中间产物已在交付后清理（释放约 43.8 MB）；仅保留 `dist-onedir\` 交付包。重新构建时这些目录会自动再生。

**profile 产物默认位置**：运行期配置与语音缓存位于 `%APPDATA%\dsh-pet-standalone-<variant>\`（例如 `%APPDATA%\dsh-pet-standalone-webm-chat\voice_chime_cache`）。

---

## 二、架构说明

### 2.1 模块分层

| 层 | 职责 | 代表文件 | 约束 |
|---|---|---|---|
| 纯逻辑层 | 可无 GUI 直接导入测试的纯函数/纯数据 | `collision.py`、`physics.py`、`collision_codec.py`、`speech_bubble_text.py`、**`voice_chime.py`**、**`voice_chime_quotes.py`** | 禁止 import Qt；`voice_chime.py` 另禁 edge_tts |
| 服务层 | 调度、线程、IO、播放，Qt 惰性导入 | `voice_chime_service.py`、`todo_reminder.py`、`proactive.py`、`agent_link.py` | 不继承 QObject 的服务需由 AppShell 持引用保证生命周期 |
| UI 层 | 窗口、设置、菜单、气泡绘制 | `window.py`、`modern_settings_dialog.py`、`speech_bubble.py`、`context_menus\*`、`settings_widgets.py` | 受行数预算约束；跨线程只经 queued 信号 |

### 2.2 核心文件职责

| 文件 | 职责要点 |
|---|---|
| `pet/__main__.py` | 入口，构造 `PetApp` 并进入 Qt 事件循环 |
| `pet/app.py` | `PetInstance`（单窗装配）+ `AppShell`（进程级：托盘、多窗共享、配置、可选服务启停）。语音报时服务的懒创建/启停/收口都在这里（`_chime_wanted` / `_ensure_chime_service` / `_sync_chime_service`，1107-1130 行；菜单回调 `trigger_voice_chime_now` / `toggle_voice_chime`，2307-2319 行） |
| `pet/window.py` | `PetWindow` 组合根：透明窗口、鼠标穿透、拖拽、动画切换、气泡位、碰撞钩子。**新功能优先拆控制器，不要往这里塞**（见第三章） |
| `pet/config.py` | `Config` 类：默认值 dict、`reload()` 白名单、迁移、`set/get/save`。语音报时 11 键默认值在 693-703 行，reload 白名单在 913-923 行 |
| `pet/modern_settings_dialog.py` | 现代设置主对话框：域导航（`_rebuild_domain_navigation`，1591 行起）、`SettingRow` 收集机制、`_write_config` 写回（2133 行起）。控件库/AI 设置页/菜单编辑器/主题 QSS 已拆出 |
| `pet/settings_widgets.py` | 设置控件库（`ModernSelect` 等），被 `modern_settings_dialog` re-export |
| `pet/context_menus/registry.py` | 菜单动作注册表：`MenuActionSpec` + `add_action`；语音报时两项在 125-133 / 219-224 行 |
| `pet/menu_templates/modern-default-v1.json` | 默认菜单布局树（右键菜单「工具」段含语音报时节点） |
| `pet/speech_bubble.py` / `speech_bubble_text.py` | 气泡绘制/交互 与 分页定位纯函数（报时气泡复用该通道） |
| `pet/chat/*` | AI 对话子系统（独立打包变体启用），`modern_settings_dialog` 顶层禁止 import 它 |
| `pet/voice_chime*.py` | 本次定制：纯逻辑 / 服务 / 设置页 / 台词库（详见第五章） |

### 2.3 关键调用链

**（1）应用启动与语音报时服务装配**

```text
python -m pet
  → pet/__main__.py
  → PetApp.start()                       # app.py
  → AppShell.start()                     # aboutToQuit 只绑一次
  → AppShell._sync_chime_service()       # 读 config.voice_chime_enabled
      ├─ 需要：_ensure_chime_service() → VoiceChimeService(app) → service.start()
      └─ 不需要：service.stop() 并丢弃对象
  → win.on_voice_chime_now / on_toggle_voice_chime 赋值（窗口实例属性，供菜单回调）
```

**（2）定时报时（核心链）**

```text
VoiceChimeService.start()  →  QTimer(20s)  →  _on_tick(now)
  ├─ voice_chime.is_chime_minute(now, cfg)     # 六种调度判定
  ├─ voice_chime.chime_slot(now, cfg)          # "YYYY-MM-DDTHH:MM#模式"，同分钟只报一次
  ├─ _consume_precache(slot)                   # 命中则直接拿到已合成 mp3（近零延迟）
  │     └─ 消费前先取 _precache_bubble（气泡文本，与语音文本解耦）
  ├─ 未命中：voice_chime.build_chime_sentence(now, cfg)  # 中文数字口播（TTS 输入 + 缓存键）
  │            voice_chime.build_bubble_sentence(now, cfg) # 阿拉伯数字气泡文本
  ├─ cache_key(text, cfg) → config.dir/voice_chime_cache/<16位哈希>.mp3
  │     ├─ 缓存命中：直接 _play_and_bubble()
  │     └─ 未命中：_TTSWorker（threading.Thread，edge-tts asyncio）
  │            → 完成后经 _AudioBridge（QObject，queued 信号）回到 GUI 线程
  │            → _on_synthesized(path, text, error)
  │            → _play_and_bubble() → QMediaPlayer + QAudioOutput 播放
  │                                 + _bubble(bubble_text) 走桌宠气泡
  └─ _maybe_precache(now)                       # 距下一报时点 ≤60s 提前合成下一次
```

**（3）右键菜单 → 手动报时 / 开关**

```text
menu_templates\modern-default-v1.json（tools 段节点 voice_chime_now / voice_chime_toggle）
  → context_menus\registry.py：MenuActionSpec(_build_voice_chime_now / _build_voice_chime_toggle)
      → pet.on_voice_chime_now()            # 窗口实例属性（app.py 装配时赋值）
      → AppShell.trigger_voice_chime_now()  # 或 toggle_voice_chime()
      → VoiceChimeService.say_now()         # 无视总开关，懒创建服务
```

**（4）设置页 → 配置写回 / 试听**

```text
modern_settings_dialog.py
  ├─ 构造：VoiceChimeSettingsPage(config, self)（约 928-931 行，automation 域）
  ├─ 收集：_rebuild_domain_navigation() 取 voice_chime_page.findChildren(SettingRow)（约 1777-1791 行）
  │         聚合成共享卡片域「语音报时」
  ├─ 保存：_write_config() → voice_chime_page.apply_to_config()（约 2133-2135 行）
  │         → config.set(11 个 voice_chime_* 键) → 保存后 _sync_chime_service()
  └─ 试听：preview_requested 信号 → _on_voice_chime_preview()（约 2221 行）
            → parent().on_voice_chime_now 回调 → 立即播报
```

---

## 三、架构红线与开发约束

> 这些规则**由测试机器化守卫**，违反即本地/CI 直接红。对应测试：`tests/test_architecture.py`（220 行，7 个用例）。

### 3.1 行数预算（绊线，不是红线）

| 文件 | 预算常量 | 当前预算 | 当前实测 |
|---|---|---|---|
| `pet/window.py` | `WINDOW_PY_LINE_BUDGET` | **4507** | 4507 |
| `pet/modern_settings_dialog.py` | `MODERN_SETTINGS_DIALOG_PY_LINE_BUDGET` | **2311** | 2311 |

> `window.py` 预算于 2026-09-15 由 4478 上调到 4507：issue #98「点击桌宠导致全局复制粘贴失效」修复（`_apply_windows_no_activate()` 在 `showEvent` 置位 `WS_EX_NOACTIVATE`，window.py +29，原生样式操作本体在 `pet/platform_win.py`）。

**触发预算时的正确动作（优先级从高到低）**：

1. **首选拆分**：新功能拆到独立模块/控制器（`window.py` 见 `docs/WINDOW_PY_SPLIT_GUIDE.md`；设置页拆到 `settings_*` / `chat/*` / 独立 `*_settings.py`）。
2. **实在拆不动**：把预算常量校准到新实测值，**带日期 + 理由注释**，并在 PR 说明。例如 `modern_settings_dialog.py` 于 2026-09-15 因「语音报时设置页接入」由 2018 上调到 2270（实测 2255）；`window.py` 于同日因 issue #98 焦点修复由 4478 上调到 4507（实测 4507）。
3. **禁止反向优化**：靠压缩行宽 / 合并语句 / 删注释把行数塞回预算内——比超预算更伤维护性。

### 3.2 依赖方向

- **纯逻辑层零 Qt**：`collision.py` / `physics.py` / `collision_codec.py` 源码中出现 `PySide6` 即红（`test_pure_logic_modules_do_not_import_qt`）。语音报时的 `voice_chime.py`、`voice_chime_quotes.py` 同样保持零 Qt、零 edge_tts（约定，人工与 review 共同守护）。
- **单向依赖**：`decode_fanout.py` 禁止反向 import `pet.window` / `pet.webm_clip`（钩子经 `movie` 属性注入）。
- **窗口私有面冻结**：`app.py` / `agent_link.py` / `context_menus/*.py` 中不得出现 `win._xxx` / `pet._xxx` / `window._xxx` 形式的私有成员访问（`test_window_private_surface_frozen`）。语音报时的窗口钩子因此走**公有属性赋值**（`win.on_voice_chime_now = ...`），而非私有成员。
- **打包变体隔离**：`modern_settings_dialog.py` 的**模块顶层**禁止 import `pet.chat.*`（no-chat 变体 excludes 掉 `pet.chat`，顶层 import 会让打包版设置界面整体打不开）；chat 依赖必须延迟到 `include_ai` 分支内的函数级 import。

### 3.3 顶层配置键三处登记（最易踩）

新增一个顶层配置键（如 `voice_chime_*`）必须**同时**改三处，漏一处 `tests/test_config_schema.py` 立刻红：

1. `pet/config.py` → 默认值 dict（语音报时在 693-703 行）；
2. `pet/config.py` → `reload()` 白名单元组（语音报时在 913-923 行）；
3. `tests/test_config_schema.py` → `DEFAULTS_SNAPSHOT` 与 `RELOAD_WHITELIST_SNAPSHOT` 快照集合（护栏用例：`test_every_defaults_key_is_whitelisted_or_special_cased` 等；特殊键走 `SPECIAL_CASED_KEYS`）。

`pet/config_domains.py` 只做「取子键 / 聚合成域 dict」的编排，**不允许写第二份清洗逻辑**。

### 3.4 孤儿文件禁令

`test_settings_widgets_orphan_cluster_guard`：`pet/settings_widgets.py`、`pet/settings_styles*.qss` 不允许「存在且零引用」—— 要么删除，要么被 `pet/` 内模块 import / read_text 读取。

### 3.5 菜单：模板 + registry + 两处测试断言必须同步

新增/修改右键菜单动作时，四件套缺一即红（语音报时两个动作为范例）：

| 序号 | 位置 | 语音报时对应 |
|---|---|---|
| ① | `pet/context_menus/registry.py`（`MenuActionSpec` + builder + `_callback_available`） | `voice_chime_now` / `voice_chime_toggle`（125-133、219-224 行） |
| ② | `pet/menu_templates/modern-default-v1.json`（布局节点） | tools 段两个节点 |
| ③ | `tests/test_menu_layout.py`（节点顺序、resolve 期望、populate 根标签） | 已补两项 |
| ④ | `tests/test_desktop_pet_features.py`（期望标签列表） | 「立即报时」「关闭语音报时」排在「桌宠设置」前 |

### 3.6 设置页控件必须包在 `SettingRow` 内

现代设置对话框的域聚合机制只认 `SettingRow` 为可移植控件：`_rebuild_domain_navigation()` 通过 `findChildren(SettingRow)` 收集，再 reparent 进共享卡片域；页面自带的普通布局子项（含根布局里的按钮）**不会**被并入，原页面被移出 `pages` 后按钮就消失（历史事故：打包版看不到「立即试听」）。

- 正确写法：`SettingRow(key, title, hint, control)`，按钮也可作为 `control` 收纳（如 `voice_chime_preview` 行的试听按钮）。
- **`SettingRow` 的键在 `objectName`**：`settingRow_<key>`，不是 Python 属性 `key`。校验收集性请用 `w.objectName().startswith("settingRow_")`。
- 新增设置项前必读 `docs/SETTINGS-CHANGE-GATES.md`（准入 6 条 / 准出 5 类：契约、TDD、布局、跨平台、视觉）。

### 3.7 其他工程纪律（摘自 `AGENTS.md`）

- 保留 dirty worktree 中的用户改动；构建产物不入提交。
- 行为修复 test-first，在公开接缝处补回归测试；Qt/IPC 回归用真实事件循环与进程边界，只 mock 无法确定性运行的 OS/网络边界。
- 涉及共享模型/配置迁移/生命周期/线程 IPC/打包依赖/平台分支/跨测试域的改动，**必须跑全量测试**。
- 诊断类排查能本地复现就不派付费子代理。

---

## 四、配置体系

### 4.1 配置对象与分组

- `pet/config.py` 的 `Config` 负责读取、清洗、迁移、持久化；键以**顶层平铺**为主，复杂功能用嵌套 dict（chat / agent_link / proactive_screen / collision / menu）。
- `pet/config_domains.py` 提供只读域 facade：`ChatConfig`、`AgentLinkConfig`、`ProactiveConfig`、`CollisionConfig`、`MenuConfig`，`normalize` 全部复用 `config.py` 既有清洗函数。
- 配置落盘位置：运行期 `config.dir/config.json`（打包版为 `%APPDATA%\dsh-pet-standalone-<variant>\`）；仓库内 `pet/persona_presets/*.json` 属角色台词预设，不属运行期配置。

### 4.2 语音报时配置键（本项目的主要定制，11 个）

| 键 | 含义 | 默认值 | 校验/清洗 |
|---|---|---|---|
| `voice_chime_enabled` | 语音报时总开关 | `True` | `clean_flag`（兼容 `"1"/"true"/"开"` 等字符串） |
| `voice_chime_schedule` | 调度模式 | `"hourly"` | `clean_schedule`：`hourly` / `every_30` / `every_15` / `every_5` / `every_minute` / `custom`，非法回落 `hourly` |
| `voice_chime_custom_times` | 自定义时间点 | `""`（空串） | `clean_custom_times`：逗号/中文逗号/分号/空白分隔的 `HH:MM`，归一化为 `08:30` 形式，非法项丢弃 |
| `voice_chime_voice` | edge-tts 音色名 | `"zh-CN-XiaoxiaoNeural"` | `clean_voice`：去空白、截断 64 字符，空值回落默认 |
| `voice_chime_rate` | 语速偏移（%） | `0` | `clean_rate`：钳制到 `[-100, 100]` |
| `voice_chime_pitch` | 音调偏移（Hz） | `0` | `clean_pitch`：钳制到 `[-50, 50]` |
| `voice_chime_volume` | 播放音量 | `80` | `clean_volume`：钳制到 `[0, 100]` |
| `voice_chime_show_bubble` | 报时气泡开关 | `True` | `clean_flag` |
| `voice_chime_show_quote` | 台词/歌词开关 | `True` | `clean_flag` |
| `voice_chime_custom_quotes_zh` | 自定义中文台词/歌词（一行一条） | `""` | `clean_custom_quotes`：按行拆分、去控制字符、单条截断 120 字、去重保序；空则回退内置中文库 |
| `voice_chime_custom_quotes_en` | 自定义英文台词/歌词（一行一条） | `""` | 同上；空则回退内置英文库 |

统一清洗出口：`voice_chime.normalize_chime_config(config)` 返回 `enabled / schedule / custom_times / voice / rate / pitch / volume / show_bubble / show_quote / custom_quotes_zh / custom_quotes_en`。

**手工改配置的注意**：运行中的进程**不会热加载** `config.json`（见第九章坑位 1）。要么改完重启，要么通过设置对话框保存（走 `Config.set/save` 并触发服务同步）。

---

## 五、语音报时功能（本项目主要定制点）

涉及四个文件（均为本次定制新增）：

| 文件 | 行数 | 层 | 职责 |
|---|---|---|---|
| `pet/voice_chime.py` | 460 | 纯逻辑 | 配置清洗、调度判定、槽位幂等、报时/气泡文本、台词批次轮换、edge 参数与缓存键。**零 Qt、零 edge_tts**，可脱离 GUI 直接单测 |
| `pet/voice_chime_service.py` | 506 | 服务 | 20s tick、预合成、`edge-tts` 后台合成、`_AudioBridge` 信号桥、`QMediaPlayer` 播放、气泡落地、缓存裁剪、降级 |
| `pet/voice_chime_settings.py` | 250 | UI | 设置页（全部控件包 `SettingRow`），`apply_to_config` / `refresh_from_config` |
| `pet/voice_chime_quotes.py` | 96 | 数据 | 中英台词/歌词库各 40 条（`CHINESE_QUOTES` / `ENGLISH_QUOTES`），纯数据零依赖 |

### 5.1 六种调度与「槽位幂等」

| `voice_chime_schedule` | 含义 | 命中判定 |
|---|---|---|
| `hourly` | 每小时的 `:00` | 分钟 == 0 |
| `every_30` | 每 30 分钟 | 分钟 % 30 == 0 |
| `every_15` | 每 15 分钟 | 分钟 % 15 == 0 |
| `every_5` | 每 5 分钟 | 分钟 % 5 == 0 |
| `every_minute` | 每分钟（冒烟/调试用） | 恒真 |
| `custom` | 自定义时间点（`voice_chime_custom_times`） | 当前 `HH:MM` 在清洗后的集合内 |

- `is_chime_minute(now, cfg)`：判定当前分钟是否命中（上表）。
- `chime_slot(now, cfg)`：命中时返回幂等槽位 `"YYYY-MM-DDTHH:MM#<schedule>"`，否则返回空串。服务用它做盖戳，**同一分钟只报一次**，天然免疫 20s tick 与设置保存/服务重启造成的重复触发；切换调度模式后模式名进槽位，不会与上一模式互相压盖。
- `next_chime_in_seconds(now, cfg)`：距下一次报时的秒数（预合成窗口判定用）。

### 5.2 edge-tts 合成与信号桥播放

```text
_on_tick(now)
  └─ 未命中缓存 → _TTSWorker(text, voice, rate, pitch, out_path, on_done)
        threading.Thread，内部 asyncio.run(edge_tts.Communicate(...).save(out_path))
        超时保护 _SYNTH_TIMEOUT_S = 45s；结束回调经 _AudioBridge 的 Qt 信号跨线程回主线程
  └─ _AudioBridge.on_synthesized(path, text, error)   # QObject，信号连接为 queued
        → VoiceChimeService._on_synthesized()
             ├─ 成功：写缓存 → _play_and_bubble(path, text, bubble_text)
             │        QMediaPlayer + QAudioOutput，音量 = voice_chime_volume
             └─ 失败：记日志，气泡照常显示（有文字无声音）
```

**线程纪律**：`_TTSWorker` 是普通 `threading.Thread`，绝不允许在其中触碰任何 QWidget/QMediaPlayer；跨线程只经 `_AudioBridge`（Qt 信号）回到 GUI 线程。`_AudioBridge` 是唯一的桥。

### 5.3 预合成降延迟（≤60s 提前合成）

- 常量：`PRECACHE_WINDOW_S = 60`。每个 tick 调 `_maybe_precache(now)`：若距下一报时点 ≤60s，且该槽位未报过、未在合成中，则**提前**在后台合成并写盘，同时记下 `_precache_slot / _precache_text / _precache_bubble / _precache_path`。
- 到点 `_consume_precache(slot)`：槽位匹配且有文件 → 直接返回 mp3 路径，**零合成延迟**直接播放。
- **易错点**：`_consume_precache` 无论命中与否都会**清空整组预合成状态**，因此气泡文本必须在消费**之前**取出（`_on_tick` 里先取 `bubble_text = self._precache_bubble` 再 consume）。这是历史缺陷修复点（预合成气泡残留）。
- 预合成窗口内合成未完时，下个 tick（20s 内）会重试，60s 窗口足够。

### 5.4 气泡与 TTS 文本解耦（阿拉伯数字 vs 中文口播）

| 用途 | 函数 | 输出示例 |
|---|---|---|
| TTS 输入 + 缓存键 | `build_chime_text(now, cfg)` | `现在是上午九点整` / `现在上午九点05分` |
| 气泡报时行 | `build_chime_bubble_text(now)` | `现在上午 09:05` / `现在下午 15:45` |
| TTS 完整句 | `build_chime_sentence(now, cfg)` | `现在是上午九点整。生活就像一盒巧克力…`（`show_quote=False` 时无台词） |
| 气泡完整句 | `build_bubble_sentence(now, cfg)` | `现在上午 09:05。生活就像一盒巧克力…` |

- 缓存键 `cache_key(text, cfg)` = `sha1("文本|音色|+r%|+pHz")[:16]`，**只按语音文本**计算，因此同一时刻的气泡文本变化不会污染语音缓存。
- 两者在同一时刻调用同一条 `pick_quote`，所以**语音与气泡台词一致**，仅时间表示不同。

> **v2 定稿点（本项目现状）**：气泡文本（`build_chime_bubble_text` / `build_bubble_sentence`）与语音文本（`build_chime_text` / `build_chime_sentence`）**彻底解耦**——气泡走「中文时段词 + 24 小时制阿拉伯数字」（如 `现在晚上 18:25`），语音走中文数字口播（如 `现在是上午九点整`），彻底避免「下午一点05分」这类阿拉伯数字与中文数字混排；缓存键只认语音文本，气泡文案调整不会污染已合成语音。

### 5.5 台词/歌词：8 小时整批轮换 + 周期内顺序轮换

- 常量：`QUOTE_ROTATION_HOURS = 8`；`_QUOTE_SLOTS_PER_DAY = 3`；`_QUOTE_BATCHES_PER_DAY = 3`。
- `split_quote_batches(pool, 3)`：把当前生效的库**按序均分 3 批**（前几批各多 1 条，空批过滤）。内置 40 条即 14/13/13。
- `quote_slot_serial(now)`：全局 8 小时周期序号 = `date.toordinal() * 3 + hour // 8`，相邻周期序号恰差 1（含跨天 16-24 → 次日 0-8 连续），取模即顺序换批、跨天不跳乱。
- `chime_index_in_period(now, cfg)`：当前周期内的第几次报时（0 起，从周期起点逐分钟回溯统计命中数）。
- `pick_quote(now, cfg)`：**批次 = 库的第 `serial % 批数` 批；条目 = 批次内第 `index % 批长` 条**。即「每 8 小时整体换一批，批内按报时次序轮换」。

> **v2 定稿点**：早期实现语义为「每 8 小时顺序取下一句」（周期切换与批内轮换纠缠，语义含混）；v2 明确为**整批换批 + 批内顺序轮换**，由 `split_quote_batches`（按序均分 3 批）/ `quote_slot_serial`（全局 8 小时周期序号）/ `chime_index_in_period`（周期内第几次报时）三个纯函数合力实现，可脱离 GUI 直接单测。实测：源码版连续 12 次报时台词全不同、相邻零重复；打包 exe 同场景指纹与源码版一致。
- 语言选择：`voice` 以 `zh` 开头用中文库，否则用英文库。
- 自定义：`voice_chime_custom_quotes_zh/en` 非空时**整体替换**对应语言内置库（单条上限 120 字，去控制字符、去重保序）；只填 1 条时仅 1 批，等价于固定台词。
- 新增台词只需往 `voice_chime_quotes.py` 的元组里加行，**无需登记任何配置**（批次数由库长自动均分）。

### 5.6 缓存与清理策略

- 目录：`<config.dir>/voice_chime_cache/<16位哈希>.mp3`（打包版即 `%APPDATA%\dsh-pet-standalone-<variant>\voice_chime_cache`）。
- 上限：`MAX_CACHE_FILES = 200`，超出按 `mtime` 从旧到新删除。
- 节流：`_prune_cache()` 全量 glob+stat 属纯 IO，`_PRUNE_MIN_INTERVAL_S = 300`（5 分钟）内最多执行一次；服务启动时也会清一次。
- 缓存目录不可访问（权限/磁盘）时静默降级（`logger.debug`），不影响报时逻辑与气泡。

### 5.7 降级路径与用户可见行为

| 场景 | 行为 |
|---|---|
| 未安装 `edge-tts` | 合成直接失败 → `_notify_missing_tts()` 给出提示，**气泡照常**显示报时与台词，无声 |
| 网络/代理异常导致合成失败 | 同上：有气泡无声音，日志留痕；已缓存的文本仍可直接播 |
| `voice_chime_enabled=False` | AppShell 不创建服务；但右键「立即报时」与设置页试听仍可用（走 `trigger_voice_chime_now` → `say_now`，无视总开关） |
| `voice_chime_show_bubble=False` | 只出声不出气泡 |
| `voice_chime_show_quote=False` | 只报时间，不带台词/歌词 |
| 设置窗口打开导致 `window.show_bubble` 被抑制 | 报时属用户主动关注事件，`_bubble()` 检测到抑制时**直接经桌宠气泡位（`win._speech_bubble`）展示**，避免闪一下就丢 |

### 5.8 设置页（`VoiceChimeSettingsPage`）

- 11 个 `SettingRow`：总开关、调度模式（`ModernSelect`）、自定义时间点、音色（常用音色清单 `VOICE_OPTIONS`，中英双语）、语速、音调、音量、气泡开关、台词开关、自定义中文台词、自定义英文台词，外加**试听按钮**（作为 `SettingRow` 的 control 位，键 `voice_chime_preview`）。
- 试听链路：`preview_requested(str)` → `modern_settings_dialog._on_voice_chime_preview()` → `parent().on_voice_chime_now`（窗口由 AppShell 赋值）。
- 写回：`apply_to_config()` 只写 11 个 `voice_chime_*` 键；`refresh_from_config()` 按当前配置回滚控件显示。
- 域归属：在 `_rebuild_domain_navigation()` 中被收集为共享卡片域「语音报时」（排在灵动岛/主动识屏/探索看门狗之后）。

---

## 六、测试体系

### 6.1 组织方式

- `tests/` 下 125 个 `.py` 测试文件 + `tests/helpers/` 辅助模块（`foreground_holder.py`，另含 7 个 bridge 的 JS 测试）；`pytest.ini` 指定 `testpaths = tests`。
- `tests/conftest.py`（275 行）提供 autouse fixture：**静音音频**（测试不出声）、模态框直通、`no-real-dsh`（禁止真实拉起外部 dsh）、Qt 资源收口（防 offscreen 泄漏）等。
- 打包与桥接验证脚本另存于 `scripts/`（如 `verify_bundle_qt.py`）、`tests/` 内的 smoke/手动校验脚本（如 `manual_ssl_proxy_check.py`，代理/证书诊断用）。

### 6.2 关键测试族

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_voice_chime.py`（937 行） | 57 个 def / 参数化后 149 用例 | 11 键默认值与清洗、六种调度数学、`chime_slot` 幂等、`build_chime_text`/`build_chime_bubble_text` 解耦、8 小时批次轮换（`split_quote_batches`/`quote_slot_serial`/`chime_index_in_period`/`pick_quote`）、自定义台词清洗、预合成状态机、缓存裁剪、edge 参数格式化与 `cache_key` |
| `tests/test_voice_chime_service.py`（444 行） | 15 | 服务层：tick 幂等、预合成消费顺序、失败降级、缓存裁剪节流 |
| `tests/test_config_schema.py`（209 行） | 5 | 三处登记护栏：`DEFAULTS_SNAPSHOT`、`RELOAD_WHITELIST_SNAPSHOT`、`SPECIAL_CASED_KEYS`，代表用例 `test_every_defaults_key_is_whitelisted_or_special_cased` |
| `tests/test_architecture.py`（220 行） | 7 | 纯逻辑零 Qt、依赖方向、窗口私有面冻结、`window.py` / `modern_settings_dialog.py` 行数预算、孤儿簇守卫 |
| `tests/test_menu_layout.py`（2108 行） | 65 | 菜单模板节点顺序、动作 resolve、populate 标签（含语音报时两项） |
| `tests/test_desktop_pet_features.py`（3118 行） | 94 | 桌宠能力集成（含菜单标签断言） |
| `tests/test_bundle_slim.py`（202 行） | 10 | `plan_removals` / `verify_no_live_reference` / `verify_required` / dry-run / 实际应用 / 拒绝越界 |

### 6.3 运行方式

```powershell
cd D:\dsh-pet
pip install -r requirements.txt
$env:QT_QPA_PLATFORM = "offscreen"     # 无头环境必须
python -m pytest -q                     # 全量
python -m pytest tests\test_voice_chime.py -q            # 语音报时族
python -m pytest tests\test_architecture.py tests\test_config_schema.py tests\test_menu_layout.py -q
python -m ruff check pet/ tests/        # 静态检查（仅 F 级规则）
python -m compileall pet packaging scripts
```

需要**真实窗口**验证时不要设 `offscreen`，直接 `python -m pet`（或运行 `run.bat`），重点看：透明穿透与拖动无回归、气泡位于角色正上方、报时气泡与语音内容一致、设置页试听按钮可见可点。

### 6.4 已知环境性 flaky 与测试纪律

- **`test_drag_move_coalescing.py::test_drag_coalesce_timer_is_about_120hz`（拖拽合并定时器）**：断言 `1000 / interval >= 120`（即 interval ≤ 8ms 档），环境调度抖动下 Qt 报 7ms / 8ms 边界值会假红（与语音报时无关）。**已在 `origin/main`（上游 `6626e4e`）独立 worktree 复现同样失败**，确认为既有环境性 flaky、非本分支引入；重跑单测确认即可，不要为它改产品逻辑。
- 写时序测试的硬纪律（`AGENTS.md`）：用事件同步（Event/Condition）+ 宽预算，禁止固定 `sleep` 猜时序、禁止赌目录枚举顺序、禁止用 `monotonic` 绝对值做回拨算术。
- CI 中 webm 生命周期族、低优预热族被**隔离出主套件**并单独复跑（`.github/workflows/pr-test.yml`），避免概率性红污染 PR 门禁。
- 最近实测记录（2026-09-17，`feat/festival-reminder-v2` @ `112a327`）：全量 **2376 passed / 10 skipped / 0 failed**（CI 三平台全绿）、`ruff` 干净；节日族（本轮新增 17 用例）+ 架构/配置/菜单/报时守卫族 226 passed；`.\run-gates.ps1` 汇总 ALL GATES PASSED。
- 上一轮实测记录（2026-09-16，`feat/voice-chime-v2`，已合入上游 `main` `6626e4e`）：全量 **2181 passed / 8 skipped**（无 failed）、`ruff` 干净；语音报时族 `test_voice_chime.py`（参数化 149 用例）+ `test_voice_chime_service.py`（15 用例）全绿。对照上一轮（2026-09-15，`feat/voice-chime`）：全量 2166 passed / 7 skipped / 1 failed（即上述 flaky）。更早基线：`main`（PR #76 合并后，2026-09-06）为 1322 passed / 7 skipped。

---

## 七、打包与交付

### 7.1 一键构建（Windows onedir + 绿色版 zip）

```powershell
cd D:\dsh-pet
pip install pyinstaller
powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1 -Variant webm-chat
```

- 入口与规格：`packaging/pet_entry.py`（Chat 版）、`packaging/pet_entry_no_chat.py`（无 Chat 版）、`dsh-pet-standalone-webm-chat.spec`。
- 产物：`dist-onedir\dsh-pet-standalone-webm-chat\`（目录）+ `dist-onedir\dsh-pet-standalone-webm-chat-portable.zip`（绿色版，**146.53 MB**，2026-09-16 18:06 生成；同一轮 `slim_bundle.py` 瘦身前为 176.2 MB）。
- 其他平台/变体：`scripts/build_linux.sh`、`scripts/build_macos.sh`；GIF 变体用 `scripts/convert_to_gif.py` 同步生成；安装包用 Inno Setup 脚本 `packaging/dsh-pet.iss`（`/D` 参数选变体，免管理员）。
- **onedir 特性**：运行期零解压，**不产生 `_MEI` 临时缓存**；历史 onefile 版遗留缓存可用 `scripts/cleanup_mei_cache.py` 检查/清理。

### 7.2 `build_onedir.ps1` 的校验门禁（顺序执行，任一失败即中止）

| 步骤 | 门禁 | 作用 |
|---|---|---|
| 1 | `PYTHONUTF8=1` 环境隔离 | 保证中文路径/源码/产物编码一致 |
| 2 | bridge 零依赖检查 | `integrations/dsh-pet-bridge` 不得引入第三方 node 依赖 |
| 3 | DLL 冲突预检 + PATH 剔除 | 剔除会与 PyInstaller 抢 DLL 的目录 |
| 4 | PyInstaller `--onedir` | 产出程序目录 |
| 5 | Qt runtime 复制与验证 | `platforms` / `styles` / `imageformats` / `multimedia` 等插件齐全（语音播放依赖 multimedia） |
| 6 | DLL 冲突自检 | 构建后目录内不得有重名冲突库 |
| 7 | `scripts/slim_bundle.py` 瘦身 | 见 7.3 |
| 8 | `scripts/check_bundle_encoding.py` | 产物中文编码自检（历史 issue #26） |
| 9 | `scripts/verify_bundle_qt.py` + 启动冒烟 | 进程存活 >8 秒，且程序目录与系统临时目录**均无新增 `_MEI`** |
| 10 | 打包 portable zip | 生成绿色版压缩包 |

### 7.3 `slim_bundle.py` 瘦身白名单

- **删除项（`REMOVAL_GLOBS`）**：Qt Quick/Qml、VirtualKeyboard、QtPdf、`opengl32sw.dll`、非 `zh`/`en` 的 `.qm` 翻译、PIL 的 AVIF 插件等（最近一轮实测移除 **124 个文件 / 53.03 MB**，zip 176.2 MB → 146.53 MB）。
- **必需项（`REQUIRED_GLOBS`）**：删除后逐一复检仍在。
- **依赖闭包校验**：用 `pefile` 解析被删 DLL 的导入关系，确认无「活引用」（`verify_no_live_reference`），避免删掉仍被加载的库。
- **安全兜底**：默认 dry-run（`plan_removals` 只输出计划），越界路径直接拒绝；`tests/test_bundle_slim.py` 的 10 个用例覆盖以上全部行为。

### 7.4 冒烟验证要求

打包完成后至少验证：

1. 启动进程存活 >8 秒，无新增 `_MEI`。
2. 设置页可见「语音报时」域全部行（含**试听按钮**）——这是 `SettingRow` 收集机制的历史事故点。
3. 把 `voice_chime_schedule` 临时设为 `every_minute`，观察 1-2 分钟内：`%APPDATA%\dsh-pet-standalone-<variant>\voice_chime_cache\` 出现 mp3，气泡与语音内容一致，随后缓存文件数随裁剪策略收敛。
4. 右键菜单「立即报时」「启用/关闭语音报时」可用且状态同步。
5. 断网（或卸载 edge-tts）时仍有气泡、无崩溃。

---

## 八、开发流程规范

### 8.1 分支与提交

- 命名：`feat/<slug>`、`fix/<slug>`、`docs/<slug>`；从 `main` 起分支。示例：`feat/voice-chime-v2`（承接已合并的 `feat/voice-chime`，见 8.2）。
- 提交信息：`<type>: <中文描述>`，必要时补范围，如
  - `feat: 新增语音报时功能（voice_chime）`
  - `fix: 语音报时预合成气泡文本残留`
- 构建产物（`dist-onedir/`、`dist/`、`build/`）与 `__pycache__` 不入提交；保留 worktree 中用户的未提交改动。

### 8.2 fork + PR 流程

1. fork 上游仓库，本地切 `feat/<slug>` 开发；
2. 提交前过**三道本地门**（见 8.4）；
3. push 到自己的 fork，向上游 `main` 开 PR；
4. PR 描述必须包含：变更点清单、验证证据（命令 + 结果数字）、风险门与回滚方式；
5. 合并前阅读 `docs/PR-MERGE-LESSONS-2026-09-12.md`：叠放 PR 在父 PR squash 后的冲突、两个 PR 合并后才越线的预算/红线、时序测试写法。

> **本仓库当前 PR 状态（2026-09-17）**：语音报时 #118（`3cf70bc`）、语音报时 v2 #125（`eeb29bb`）、节日提醒 #127（`be9a6d0`）以及 #128/#129/#130 均已合并。**注意 #124 本身未合并**——它被上游以 #125（`eeb29bb`，内容同、提交不同）接管落 main，这是"叠放 PR 在父 PR squash 后冲突"的已知陷阱（见教训 1）。当前 open 的自有 PR：[#131](https://github.com/MerZlin/dsh-pet-indesktop/pull/131)（`feat/festival-reminder-v2` @ `1ca34af`，承接 #127，11 files +844/-11）。后续同类改动沿用这一模式：**父 PR 合并后新建承接分支 + 承接 PR，PR 正文写明与前一 PR 的承接关系**。

### 8.3 PR 报告文档写法与存放位置

- 存放：`docs/PR-REPORT-<主题>-<YYYY-MM-DD>.md`，示例：
  - `docs/PR-REPORT-VOICE-CHIME-2026-09-15.md`（语音报时，含九轮改进章节）
  - `docs/PR-REPORT-GATES-2026-09-10.md`、`docs/PR-REPORT-PR76-2026-09-10.md`
- 结构建议：
  1. **核心特性**：一句话定位 + 能力清单；
  2. **修改文件清单**：逐文件说明改动意图（含新增/删除）；
  3. **实现要点**：关键算法、数据结构、线程与信号模型；
  4. **测试与验证**：命令、通过数、构建冒烟结果；
  5. **已知限制与后续**：明确未完成项；
  6. **风险与回滚**：影响面、开关、回滚步骤。
- **迭代写法**：后续轮次在同一文档**追加新章节**（如「第二轮改进」「第九轮修正」），保留新旧逻辑对照表，不要重写覆盖——评审依赖历史对照。

### 8.4 变更门禁

- **本地三道门（推送前必过）**：① `ruff check pet/ tests/`；② 全量 `pytest -q`；③ 受影响时序测试族高负载复跑（本地 CPU 打满跑 3 遍）。缝合/脚本化改动后**必须重跑 ruff**（重复定义、残留 import 不许交给 CI 发现）。
- **设置相关变更门禁**：`docs/SETTINGS-CHANGE-GATES.md` —— 准入 6 条（是否必须持久化、是否有默认值、是否进 reload 白名单、是否包 `SettingRow`、是否有测试、是否跨平台）+ 准出 5 类验证（契约、TDD、布局、跨平台、视觉）。
- **配置键变更**：同步三处（第三章 3.3）。
- **菜单变更**：同步四件套（第三章 3.5）。
- **行数预算变更**：优先拆分；确需校准则带日期 + 理由注释 + PR 说明（第三章 3.1）。
- **改前必读的 context pointers**（`AGENTS.md`）：`docs/WINDOW_PY_SPLIT_GUIDE.md`（动 `window.py`）、`docs/SETTINGS-CHANGE-GATES.md`（动设置）、`docs/ONEDIR_PACKAGING.md`（动打包）、`docs/ISSUE-111-WINDOWS-SESSION-END-FFMPEG-2026-09-12.md`（动 ffmpeg/关机路径）等。

---

## 九、已知问题、坑位清单与后续待办

### 9.1 坑位清单（按踩坑频率排序）

1. **运行中的进程不热加载 `config.json`**：外部直接改文件对已运行实例无效，需重启；通过设置对话框保存才即时生效（并触发 `_sync_chime_service`）。
2. **顶层配置键三处登记**：默认 dict + reload 白名单 + `test_config_schema.py` 快照，漏一处立刻红（记忆中最常见失误）。
3. **设置页控件必须包 `SettingRow`**：普通布局里的按钮在打包版**不可见**；且 `SettingRow` 的键在 `objectName`（`settingRow_<key>`），校验收集性要用 `objectName().startswith("settingRow_")`，不要按属性 `key` 查。
4. **`modern_settings_dialog.py` 顶层禁止 import `pet.chat`**：no-chat 变体会 exclude `pet.chat`，顶层 import 会让设置界面整体打不开。
5. **菜单动作四件套同步**：registry + 模板 JSON + 两处测试断言，缺一即红。
6. **`window.py`「只许瘦不许胖」**：当前 4507 行已顶满预算（4507），下一个功能必须先拆控制器，再校准预算（并写日期+理由）。
7. **纯逻辑层禁 Qt / 禁 edge_tts**：`voice_chime.py`、`voice_chime_quotes.py` 不得 import Qt 与 edge_tts；`edge-tts` 只在服务层惰性导入（缺失即降级为纯气泡）。
8. **跨线程纪律**：`_TTSWorker` 中禁止触碰 QWidget/QMediaPlayer；一律经 `_AudioBridge` queued 信号回 GUI 线程。
9. **预合成状态的清理时机**：`_consume_precache` 会清空整组状态，气泡文本必须先取后用（历史缺陷点）。
10. **缓存 IO 静默降级**：缓存目录不可访问时不报错、只记 debug 日志，排查报时无声时先看目录权限与磁盘。
11. **在线依赖与代理**：edge-tts 依赖微软在线语音服务，企业代理/证书异常会合成失败（`certifi` 已入依赖）；离线场景只能靠已有缓存或纯气泡。诊断脚本见 `tests/manual_ssl_proxy_check.py`。
12. **编码坑**：目标机控制台 GBK，用 `Get-Content` 读 UTF-8 源码会乱码（文件无问题，加 `-Encoding UTF8` 或 `PYTHONUTF8=1`）；打包链有 `check_bundle_encoding.py` 门禁。
13. **并发编辑同一文件互相覆盖**：同一文件的多处并行编辑会互相冲掉，必须串行改。
14. **时序测试纪律**：禁止固定 `sleep`、赌目录顺序、`monotonic` 绝对值算术；用事件同步 + 宽预算。
15. **变体差异**：Chat 版含 `pet.chat`，no-chat 版 exclude；新功能若依赖 chat 需在两条链路都验证。
16. **历史遗留清理**：旧 onefile 的 `_MEI*` 缓存、安装版旧自启项需 `scripts/cleanup_mei_cache.py` 等脚本清理，否则会出现「改了没生效」的错觉。
17. **ruff 仅 F 级**：格式/风格问题不会让 CI 变红，别指望 CI 帮你抓格式。
18. **环境性 flaky**：`test_drag_move_coalescing.py::test_drag_coalesce_timer_is_about_120hz` 等定时精度用例偶发假红（Qt 7ms vs 8ms），已在 `origin/main` 复现，重跑确认即可，不要改产品逻辑。
19. **可再生中间产物及时清理**：`build-onedir/`、`build/`、`dist/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/` 交付后应清理（本轮释放约 43.8 MB），仅保留 `dist-onedir/` 交付包与运行中的用户实例数据。

### 9.2 后续待办

| 优先级 | 事项 | 说明 / 切入点 |
|---|---|---|
| 高 | 承接 PR [#131](https://github.com/MerZlin/dsh-pet-indesktop/pull/131) 的评审与 CI 跟进 | 当前 open（`feat/festival-reminder-v2` @ `1ca34af` → `main`，11 files +844/-11，承接 #127）；合并后再有增量改动时，按 8.2 重新起承接分支 + 承接 PR |
| 高 | `window.py` 增量拆分 | 预算已顶满（4507）；按 `docs/WINDOW_PY_SPLIT_GUIDE.md` 域地图拆控制器 |
| 高 | `modern_settings_dialog.py` 再拆分 | 预算与实测同为 2311（**零余量**）；新设置页一律先拆到独立 `*_settings.py` |
| 中 | 节日动画素材缺口补齐（复活节/母亲节/父亲节） | 补素材后从 `festival_animations.KNOWN_GAPS` 移除，对应用例会变红提醒 |
| 中 | 离线音色兜底（候选：Windows SAPI / pyttsx3） | 当前 edge-tts 不可用时仅气泡；可评估本地离线音色作为第二合成后端 |
| 中 | 任务栏隐藏模式下的报时行为验证 | 隐藏/自动隐藏场景下气泡与播放位置的体验待专项验证 |
| 中 | 报时缓存管理入口 | 设置页可加「清理语音缓存」按钮（当前仅自动裁剪 200 文件） |
| 中 | 时区/系统时间变更下的槽位与批次行为 | 夏令时、手动回拨时钟时 `chime_slot` 与 8 小时批次的表现可补测试 |
| 低 | 自定义台词批量导入 | 当前仅文本域手填（一行一条）；可考虑文件导入与数量上限提示 |
| 低 | GIF 变体与语音报时共存验证 | GIF 变体走 `convert_to_gif.py`，需回归报时链路 |
| 低 | flaky 用例收口 | `test_drag_move_coalescing` 等定时精度问题根治 |

---

## 附录 A：常用命令速查

```powershell
# 源码运行
cd D:\dsh-pet
pip install -r requirements.txt
pip install edge-tts                # 需要语音合成时
python -m pet                        # 或 run.bat

# 测试与检查
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m pytest tests\test_voice_chime.py tests\test_voice_chime_service.py -q   # 语音报时纯逻辑 + 服务层（149 + 15 用例）
python -m ruff check pet/ tests/
python -m compileall pet packaging scripts

# 打包
powershell -ExecutionPolicy Bypass -File scripts\build_onedir.ps1 -Variant webm-chat
# 产物：dist-onedir\dsh-pet-standalone-webm-chat-portable.zip

# 运行期目录（配置 + 语音缓存）
explorer "%APPDATA%\dsh-pet-standalone-webm-chat"
```

## 附录 B：关键位置索引

| 内容 | 位置 |
|---|---|
| 语音报时 11 键默认值 | `pet/config.py` 693-703 行 |
| 语音报时 reload 白名单 | `pet/config.py` 913-923 行 |
| 配置键三处登记护栏 | `tests/test_config_schema.py`（`DEFAULTS_SNAPSHOT` / `RELOAD_WHITELIST_SNAPSHOT`） |
| 语音报时纯逻辑总入口 | `pet/voice_chime.py`（`normalize_chime_config` 226 行、`chime_slot` 299 行、`build_chime_text` 314 行、`quote_slot_serial` 329 行、`chime_index_in_period` 339 行、`split_quote_batches` 361 行、`pick_quote` 382 行、`build_chime_bubble_text` 417 行、`build_bubble_sentence` 427 行、`cache_key` 455 行） |
| 语音报时服务 | `pet/voice_chime_service.py`（常量 126-130 行、`_on_tick` 213 行、`_maybe_precache` 237 行、`_consume_precache` 295 行、`_play_and_bubble` 394 行、`_bubble` 430 行、`_prune_cache` 487 行） |
| 语音报时设置页 | `pet/voice_chime_settings.py` |
| 语音报时设置页接入 | `pet/modern_settings_dialog.py` 928-931（构造）、1777-1791（域收集）、2133-2135（写回）、2221（试听） |
| 语音报时服务启停 | `pet/app.py` 1107-1130（`_chime_wanted` / `_ensure_chime_service` / `_sync_chime_service`）、2307-2319（`trigger_voice_chime_now` / `toggle_voice_chime`） |
| 菜单动作注册 | `pet/context_menus/registry.py` 125-133、219-224 行 |
| 菜单模板节点 | `pet/menu_templates/modern-default-v1.json` |
| 行数预算常量 | `tests/test_architecture.py`（`WINDOW_PY_LINE_BUDGET` = 4507 / `MODERN_SETTINGS_DIALOG_PY_LINE_BUDGET` = 2311） |
| 构建脚本 | `scripts/build_onedir.ps1`、`scripts/slim_bundle.py`、`scripts/check_bundle_encoding.py`、`scripts/verify_bundle_qt.py` |
| 交付包与 PR | `dist-onedir\dsh-pet-standalone-webm-chat-portable.zip`（146.53 MB，2026-09-16 18:06）；[PR #131](https://github.com/MerZlin/dsh-pet-indesktop/pull/131)（承接 #127；#118/#125/#127 均已合并） |
| 相关工程文档 | `docs/ONEDIR_PACKAGING.md`、`docs/SETTINGS-CHANGE-GATES.md`、`docs/WINDOW_PY_SPLIT_GUIDE.md`、`docs/PR-REPORT-VOICE-CHIME-2026-09-15.md`、`docs/PR-MERGE-LESSONS-2026-09-12.md` |

*（内容由AI生成，仅供参考）*
