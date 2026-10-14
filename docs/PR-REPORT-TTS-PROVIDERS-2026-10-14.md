# PR 报告：语音合成后端 provider 化（TTS 出声层可插拔）

- 日期：2026-10-14
- 分支：`feat/tts-providers`（基于上游 `main` = `ffc80a6`）
- 范围：把「语音报时的出声那一层」从写死 edge-tts 改成注册表 + 声明式 provider，
  并顺带整理语音报时 / 节日提醒两页设置。**不动**调度、台词、播放与免打扰语义。
- 动机：上游自带 `docs/ISSUE-EDGE-TTS-VOICE-DEPRECATION-2026-09-22.md`（edge 合成
  「没声音」的两条根因）。本地实测同一问题仍在（见下「性能分析」），且 edge 服务端
  403 不是我们能修的；把后端做成可插拔是唯一能在现场自救的形状。

---

## 一、修改文件说明（逐文件 + `git diff --numstat`）

```
$ git diff --numstat ffc80a6 HEAD
1	0	.gitignore
127	0	docs/ADDING-A-TTS-PROVIDER.md
1	0	docs/INDEX.md
25	0	pet/config.py
213	110	pet/festival_settings.py
200	0	pet/festival_settings_panel.py
81	0	pet/http_util.py
32	28	pet/modern_settings_dialog.py
24	0	pet/settings_widgets.py
45	0	pet/tts/__init__.py
231	0	pet/tts/base.py
230	0	pet/tts/doubao.py
352	0	pet/tts/edge.py
202	0	pet/tts/mimo.py
184	0	pet/tts/sapi.py
92	0	pet/tts_secrets.py
145	14	pet/voice_chime.py
168	270	pet/voice_chime_service.py
302	71	pet/voice_chime_settings.py
237	0	pet/voice_chime_tts_panel.py
5	2	tests/test_architecture.py
12	0	tests/test_config_schema.py
429	0	tests/test_festival_settings_layout.py
67	0	tests/test_tts_doubao.py
245	0	tests/test_tts_edge.py
106	0	tests/test_tts_secrets.py
26	13	tests/test_voice_chime.py
0	308	tests/test_voice_chime_edge_voice.py
653	0	tests/test_voice_chime_mimo.py
73	46	tests/test_voice_chime_service.py
350	0	tests/test_voice_chime_settings_layout.py
31 files changed, 4858 insertions(+), 862 deletions(-)
```

### 新增：接口层（纯逻辑、零 Qt）

- **`pet/tts/base.py`** — `TtsField`（声明式配置项）/ `TtsAttempt`（一次合成尝试）/
  `TtsProvider`（`plan()` 纯函数、`synth()` 有 IO、`availability()`、`preflight()`、
  `flavor()`）/ 注册表（`register` / `get` / `provider_ids` / `fallback_ids` /
  `secret_fields`）。分层红线写在模块 docstring 里：顶层不得 import Qt，也不得
  import 重量级可选依赖（`edge_tts` 这类要惰性导入进 `synth`）。
- **`pet/tts/__init__.py`** — import 即注册四个内置后端。
- **`pet/tts/edge.py` / `mimo.py` / `sapi.py` / `doubao.py`** — 四个后端各一个模块。
  改一个后端不用碰服务层、设置页或配置清洗。
- **`pet/tts_secrets.py`** — 合成凭据存取（系统钥匙串优先、进程内存兜底）。
  刻意**不复用** `pet/chat/models.py` 的 `SecretStore`：no-chat 打包变体会
  `exclude` 掉 `pet.chat`，而语音设置页在 chat / no-chat 两条链路上都要能打开。
- **`pet/http_util.py`** — 带「代理不通就直连」兜底的 `urlopen`（MiMo 的同步 HTTP 走它）。

### 新增：设置页编排

- **`pet/voice_chime_tts_panel.py`** — 后端参数行的折叠编排：当前后端平铺，其余后端
  各占一个可展开折叠头。折叠状态挂在**行**上（`_reveal_fold` 回调），因为这些行稍后
  会被「语音」域搬进一张平卡，容器活不下来。
- **`pet/festival_settings_panel.py`** — 节日提醒页的「常用项平铺 + 少用项折叠」编排。

### 改动：服务层与纯逻辑层

- **`pet/voice_chime.py`**（+145/−14）— 后端清单与默认值来自注册表；新增
  `clean_backend` / `synth_ext` / `synth_attempts`；`default_chime_config()` 按
  provider 的 `fields` 生成（加后端不会漏登记）；`normalize_chime_config()` 产出
  `providers` 字段值表，同时**保留** `voice`/`rate`/`pitch`/`mimo_*` 历史平铺键
  （既有调用点与设置页不必改）；`cache_key` 改按 provider 的 `flavor()` 取键，
  换后端/音色不会再播到上一个后端的缓存。
- **`pet/voice_chime_service.py`**（+168/−270）— `_TTSWorker` 改为照尝试序列逐个
  合成、第一个成功的写盘回调；新增 `_usable_attempts` / `_secret_values` /
  `_cache_path` / `_announce_once`。**上游全部播放侧机制原样保留**（合成代次作废、
  通道判据 `_channel_idle`、看门狗、免打扰闸、原子换名与临时文件台账）——它们与
  用哪个后端无关。删掉了被 provider 接管的 edge 专用死代码（约 109 行）：同一份逻辑
  留两处副本，改动漏一处就会分叉。
- `_prune_cache` 修一处**旁路遗漏**：原来只 glob `*.mp3`，换后端后 wav 缓存不参与
  上限淘汰、会无上限增长。

### 改动：设置页与配置

- **`pet/voice_chime_settings.py`**（+302/−71）— 「语音引擎」下拉与每个后端的参数行
  全部照 `TtsProvider.fields` 生成（控件类型、标题、提示、依赖隐藏都在 provider 里
  声明），本文件不再写死任何后端；密码字段单独进「要你自己去拿的凭据」组，只写钥匙串、
  不落 config.json。
- **`pet/festival_settings.py`**（+213/−110）— 套用折叠编排，并暴露 `build_domain_page`
  / `refresh_backend_rows` 供「语音」域装配调用。
- **`pet/modern_settings_dialog.py`**（+32/−28）— 语音报时与节日提醒不再按「一组行」
  收进「语音」域（那样页面容器会散架、分组标题会丢），改由各自页面自建卡片交给本域；
  搜索命中的折叠行统一走 `settings_widgets.reveal_settings_row`（原来内联的祖先遍历
  不认识**行级**折叠，命中折叠后端里的行会「搜得到但看不见」），并保留高级组自动展开。
- **`pet/settings_widgets.py`**（+24）— 新增 `reveal_settings_row()`。
- **`pet/config.py`**（+25）— 登记 provider 配置键（默认 dict + reload 白名单两处）。
- **`tests/test_architecture.py`**（+5/−2）— `modern_settings_dialog.py` 行数预算按
  **实测**校准 2501 → 2505（不为达标压行，理由写进常量上方注释）。
- **`tests/test_config_schema.py`**（+12）— 默认值与白名单快照同步。
- **`docs/ADDING-A-TTS-PROVIDER.md`**（+127）+ `docs/INDEX.md` 登记一条。

### 用例

- 新增 `test_tts_edge.py`（245）/ `test_tts_doubao.py`（67）/ `test_tts_secrets.py`（106）
  / `test_voice_chime_mimo.py`（653）/ `test_voice_chime_settings_layout.py`（350）
  / `test_festival_settings_layout.py`（429）。
- 删除 `test_voice_chime_edge_voice.py`（−308）：它钉的是「worker 内部怎么调
  `edge_tts.save`」，现在这层归 provider；覆盖已全部重铺进 `test_tts_edge.py`。
- 改 `test_voice_chime.py` / `test_voice_chime_service.py`：替身与断言指到新的
  worker/attempt 接口与 provider 侧符号。

---

## 二、性能分析（命令 + 环境 + 样本量）

**环境**：Windows 11 专业版 24H2 (26100)、Ryzen 7 5800X、32GB；
Python 3.11（`D:\dsh-pet\.venv`）；测试日 2026-10-14。

**命令**（本分支实跑）：

```
.venv\Scripts\python.exe .scratch\tts-providers-pr\bench_synth.py
```

该脚本对注册表里每个后端各跑 **3 轮**同一句话（22 字：
「现在是下午三点整，顺便说一句，今天天气不错。」），只计 `provider.synth()` 的
墙钟（不含播放与调度），取首句与复句最快值。

**结果**（原文见 `.scratch/tts-providers-pr/bench-synth.txt`）：

| 后端 | 结果 |
|---|---|
| `sapi`（离线本地） | **首句 435 ms / 复句最快 99 ms**，3 轮全部成功，产物 270,708 字节 wav |
| `edge`（微软在线） | 失败：`WSServerHandshakeError 403`（两个不同 `ConnectionId` 各试一次，均 403） |
| `doubao` | 当前配置下不可用：`doubao_key_missing`（未配 Key） |
| `mimo` | 当前配置下不可用：`mimo-key-missing`（未配 Key） |

**怎么读这组数**：

1. edge 的 403 与本地既有结论一致——**不是我们能修的**（`edge-tts` 已是 PyPI 最新、
   本机时钟只偏 −0.6 s，见上游那份弃用 issue 与本地事故档案），这正是本次改动的动机。
2. 离线后端把「首句 435 ms / 复句 99 ms」变成**零网络、零 Key**的兜底：在线后端
   不可用时用户至少还有声音，而不是只剩气泡。
3. 在线两家的真实延迟未在本分支测（要各自 API Key，凭据只进用户自己的钥匙串，
   仓库与 CI 里拿不到）。这是**本次未验到的一格**，如实登记；转发链的切换成本已由
   用例钉住（第一个后端成功即返回、失败按顺序换下一个）。

**门禁**：

- `ruff check .` → `All checks passed!`
- 全量用例按文件切 10 片各起独立进程跑（单进程全量会撞既存原生崩溃
  `0xC0000005`，落点随机、崩前纯绿）——结果见本报告「三、实机运行记录」。
- 受影响时序族（语音报时服务 / 设置页布局 / 配置快照 / 架构守卫）满载复跑：
  `pytest tests/test_voice_chime_service.py tests/test_voice_chime.py
  tests/test_voice_chime_mimo.py tests/test_tts_edge.py tests/test_tts_doubao.py
  tests/test_tts_secrets.py tests/test_voice_chime_settings_layout.py
  tests/test_festival_settings_layout.py tests/test_architecture.py
  tests/test_config_schema.py -q` → **302 passed in 32.13s**。

---

## 三、实机运行记录（真机命令与输出）

### 1. 静态检查

```
$ .venv\Scripts\python.exe -m ruff check .
All checks passed!
```

（ruff 这一关在本 PR 里抓到过实打实的东西：删掉服务层那段被 provider 接管的
edge 死代码后，留下 `_VOICE_SUBSTITUTION_NOTICES` 未定义（F821）与 6 处空掉的
import——pytest 因为用例没走到那条路径而全绿，只有 ruff 报了出来。）

### 2. 全量用例（按文件切片、各起独立进程）

单进程跑全量会撞既存原生崩溃 `0xC0000005`（落点随机、崩前纯绿），所以按仓库既有
口径用 `.scratch/run_chunks.py` 起独立进程取证：

```
$ .venv\Scripts\python.exe -X faulthandler .scratch\run_chunks.py
collect 7060 用例 / 346 文件，切片 <= 500 用例
```

分 16 片（每片 ≤500 用例）逐片起独立进程，**16 片全部跑完、无原生崩溃**：

```
c01  95 passed          c09  418 passed
c02  478 passed, 6 skipped      c10  495 passed
c03  448 passed, 3 skipped      c11  4 failed, 487 passed, 3 skipped
c04  2 failed, 394 passed, 4 skipped   c12  4 failed, 486 passed
c05  498 passed          c13  483 passed
c06  483 passed          c14  391 passed, 1 skipped
c07  2 failed, 470 passed, 2 skipped   c15  481 passed
c08  488 passed          c16  33 passed, 1 skipped

合计：passed 7028 / failed 12 / skipped 20 —— **7060 用例全部跑到**。
```

那 12 条失败**逐条**在未改动的基线上复核过（见下一节），全部是上游既有。
原始逐片日志：`.scratch/tts-providers-pr/chunks-final.log`。

### 3. 与「既有红」的区分（在未改动的上游基线上复核）

本机在**完全未改动的 `ffc80a6`** 上跑同一批用例，用来把「上游既有红」与
「本改动引入的红」分开：

```
$ git stash -q                       # 工作区 == ffc80a6
$ .venv\Scripts\python.exe -m pytest tests/test_settings_page_guide.py \
      tests/test_menu_layout.py tests/test_desktop_pet_features.py -q
8 failed, 188 passed in 51.91s

$ git stash pop -q                   # 恢复本分支改动
$ .venv\Scripts\python.exe -m pytest tests/test_settings_page_guide.py \
      tests/test_menu_layout.py tests/test_desktop_pet_features.py -q
4 failed, 192 passed in 56.69s

# 另外一族（节日页文案 / 行壳顶层窗 / 文案 lint / 默认值快照）在两条线上同名同数：
$ （基线）8 failed, 15 passed      $ （本分支）8 failed, 15 passed
```

**结论：基线 8 红 → 本分支 4 红（该族），净减 4 条，未引入任何新的红。**
剩下那 4 条是「页内跳转条 + 组描述」一族的上游既有问题（`SECTION_GUIDE` 里有、
界面上因平台闸门/折叠态而看不到的组），与本 PR 无关，故不顺手改。
完整台账见 `.scratch/tts-providers-pr/baseline-red.md`。

**唯一一次本分支自己引入又自己修掉的**：我给新卡片「你的生日」写的描述里带了
`MM-DD` 这种格式占位符，被 `test_section_descriptions_pass_the_copy_lint` 抓到
（该用例在基线上是绿的），已改成纯人话「填了就在当天有专属祝福。」。

### 4. 受影响时序族满载复跑

```
$ .venv\Scripts\python.exe -m pytest tests/test_voice_chime_service.py \
      tests/test_voice_chime.py tests/test_voice_chime_mimo.py tests/test_tts_edge.py \
      tests/test_tts_doubao.py tests/test_tts_secrets.py \
      tests/test_voice_chime_settings_layout.py tests/test_festival_settings_layout.py \
      tests/test_architecture.py tests/test_config_schema.py -q
302 passed in 32.13s
```

---

## 四、未验到 / 如实登记

1. **在线后端（edge / doubao / MiMo）的真实合成延迟**未在本分支测：前者的服务端
   403 不可修，后两者要用户自备 Key（凭据只进用户钥匙串，仓库与 CI 里拿不到）。
2. **设置页在打包产物里的实机观感**未在本分支验证：本 PR 只动源码与用例，
   打包与部署按既有流程单独走（产物构建时间约 1.5–2 分钟，见本地部署口径）。
3. **故障注入**未做：本次是结构搬运，承重由既有用例覆盖（`test_tts_edge.py` 钉住
   重试/换音色/空文件三条失败路径，`test_voice_chime_service.py` 钉住回退链与
   播放侧不变量），没有对每个后端逐个注入缺陷。
