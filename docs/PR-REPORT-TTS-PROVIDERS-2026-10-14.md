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

   > **2026-10-17 更正（结论已被推翻，原文保留作对照）**：这条结论**当时就错了**。
   > 合并 `main`（含 #287）后的同日同机 A/B 证明 403 是 **`edge-tts` 版本问题**，
   > 不是服务端不可修：7.2.8 → `WSServerHandshakeError 403`，**同网络 7.3.1 → 正常
   > 出音频**（26,640 字节，ffprobe 认出 mp3/24 kHz/单声道/4.44 s）。因此依赖下限已由
   > `main` 提到 `edge-tts>=7.3.1,<8`，构建期加版本门禁（不满足退出码 6）。复测数字与
   > 证据见本报告 **§五**。当日之所以判成「不可修」，是只把「PyPI 最新版」当作判据，
   > 没有试 7.3.x——**教训：拿「已经是最新版」当前提之前，先确认上游确实发过修复版**。
2. 离线后端把「首句 435 ms / 复句 99 ms」变成**零网络、零 Key**的兜底：在线后端
   不可用时用户至少还有声音，而不是只剩气泡。
3. 在线两家的真实延迟未在本分支测（要各自 API Key，凭据只进用户自己的钥匙串，
   仓库与 CI 里拿不到）。这是**本次未验到的一格**，如实登记；转发链的切换成本已由
   用例钉住（第一个后端成功即返回、失败按顺序换下一个）。**edge 这一格已于 §五
   用真实网络补测**（7.3.1 成功 3.4 s / 26,640 字节）；doubao 与 MiMo 仍未测（无 Key）。

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

   > **2026-10-17 更正**：前半句已作废——403 是 `edge-tts` 7.2.8 的版本问题，7.3.1
   > 正常出音频；edge 的真实网络合成已在 §五 补测。doubao / MiMo 仍然未测（无 Key），
   > 这条**剩下一半依旧成立**。
2. **设置页在打包产物里的实机观感**未在本分支验证：本 PR 只动源码与用例，
   打包与部署按既有流程单独走（产物构建时间约 1.5–2 分钟，见本地部署口径）。
3. **故障注入**未做：本次是结构搬运，承重由既有用例覆盖（`test_tts_edge.py` 钉住
   重试/换音色/空文件三条失败路径，`test_voice_chime_service.py` 钉住回退链与
   播放侧不变量），没有对每个后端逐个注入缺陷。

---

## 五、第二轮：集成 `origin/main` 后的收口与复测（2026-10-17）

- **基线**：`056dc2a`（`origin/main`：#291 汽水歌词直连 / #288 每屏合成窗 / #287 edge-tts 门禁）
- **分支**：`integration/pr267`（作者 tip `29a87be` + merge `056dc2a`；**未 push 作者 fork、未开替代 PR**）
- **范围**：对 `origin/main` 的净差 **39 文件 `+5776/−968`**（含本报告与 `ADDING-A-TTS-PROVIDER.md`）
- 这一节只写**本轮新做的**（冲突收口、迁移、复测）；第一轮的内容保留在上面，不改写。

### 5.1 修改文件说明（本轮）

四处文本冲突，按「合成链路用本支的 provider 架构、main 的新能力照迁」收口：

| 冲突文件 | 取法 | 为什么 |
|---|---|---|
| `pet/voice_chime_service.py` | 取本支（`--ours`），再把 main 的 `missing_dependency_hint()` 一处调用接回 | edge 合成整段已进 `pet/tts/edge.py`，main 在服务层加的 edge 实现属于被接管的旧位置；但 287 的**缺组件提示**（认得出打包版，不再让用户 `pip install`）必须留下 |
| `tests/test_architecture.py` | 两侧注释历合并，预算按 merge 后**实测**重设为 2533 | 该支的 2508 与 main 的 2526 都已被取代：`wc -l pet/modern_settings_dialog.py` = 2526 + 净增 7 = **2533** |
| `.gitignore` | 两侧条目并集 | 该支的 `dist-onedir-alt/` 与 main 的 android 构建/签名产物都要继续忽略 |
| `tests/test_voice_chime_edge_voice.py` | 取删除（本支已按 provider 拆分删掉它），把 main 改过的那条断言迁进 provider 层用例 | main 只改了它一条断言（失败消息要说人话），本支把该文件拆进了 `test_tts_edge.py` |

**没有文本冲突、但语义要跟着搬**的两处（最容易漏的正是这类）：

- `tests/test_tts_diagnostics.py`（main 新增 40 行）：用例驱动的是本支**已删除**的
  `_TTSWorker(text, voice, rate, pitch, out_path, on_done)` 形态与 `service.refresh_voice_list`，
  合并后必红。改为只测分类表本身（`describe_failure` / `missing_dependency_hint`），
  端到端（错误串 + 日志 + 半截产物清理）放到 provider 层的 `test_tts_edge.py`。
- `pet/tts/edge.py`（**287 的脱敏失败诊断随合成链路迁入**）：异常原文可能带签名 URL、
  令牌与代理凭据，迁之前它们会原样进用户气泡与日志。现在——
  - 用户可见的错误串只给分类后的人话（`HTTP 403` / 连接超时 / 代理失败 / 未返回音频）；
  - 细节只以脱敏行（`type=` / `version=` / `http=` / `route=`）进日志；
  - 系统代理只解析一次（既喂 `Communicate`，也作为诊断的 `route` 口径）；
  - 缺组件文案改由 `missing_dependency_hint()` 单一来源；
  - 空音频改用 `_EmptyAudio` 标记，失败产物统一 `_discard()` 清理（原来两条分支各写一遍）。
- `pet/tts/sapi.py` 模块文档：原文写着「edge-tts 7.2.8 已是最新版，我们这边无从修」——
  **该结论已作废**（见 §二 更正框与 5.2），改成「7.2.8 的版本问题，7.3.1 起正常」，
  并写明 SAPI5 到今天仍值得留（零网络兜底，不是「edge 修好了就该删」）。
- `tests/test_architecture.py` 另补一条守卫：`pet/tts/*.py` **顶层**不得 import Qt 或
  可选/重量级依赖（`edge_tts` / `aiohttp` / `requests`）。`pet/tts/base.py` 的模块文档一直
  宣称「违反即红」，但本支的 `test_architecture.py` 里**并没有**这条守卫（`git grep` 零命中）——
  要么改文档、要么补守卫，本轮选择补守卫让那句话成真（函数体内的延迟 import 不受影响）。

**本轮提交**：

```
7960ac4 merge: origin/main（#291 汽水歌词 / #288 跨屏 / #287 edge-tts 门禁）进 PR267 feat/tts-providers
518d726 tts(edge): main 287 的脱敏失败诊断随合成链路迁进 provider
〈本次文档收口〉docs(tts): 第二轮报告 + INDEX 登记 + 「403 不可修」结论更正 + provider 守卫口径
```

（`518d726` 里还顺带把 `_save()` 的代理入参改成 `_PROXY_UNRESOLVED` 哨兵——原来 `proxy=None`
兼作「没传」与「已确认直连」，会让无代理时每次重试都重复解析一次系统代理。）

### 5.2 性能分析（本轮实测）

**环境**：Windows 11 24H2 (26100)、Ryzen 7 5800X、32GB、Python 3.13.7（`D:\dsh-pet-src\.venv`）；
依赖用**隔离目录**装出、不装进任何全局环境：`pip install --target D:\dsh-pet-pr267-deps edge-tts==7.3.1`
（另装一个 `D:\dsh-pet-pr267-deps-728` 装 7.2.8 做 A/B）。测试日 2026-10-17。

**命令**：`PR267_REPO=D:/dsh-pet-wt-pr267 PYTHONPATH=D:/dsh-pet-pr267-deps python bench_pr267.py`
（脚本与原始输出都在 `D:/dsh-pet-pr267-artifacts/`：`bench_pr267.py` / `bench-synth.txt`）

**纯层单次开销（n=20000 或 5000，预热后取均值）**：

| 路径 | 单次 |
|---|---|
| `provider.plan()`（edge） | 0.918 µs |
| `provider.flavor()`（edge） | 0.858 µs |
| `voice_chime.normalize_chime_config()` | 16.148 µs |
| `voice_chime.synth_attempts()` | 4.039 µs |
| `voice_chime.cache_key()` | 2.976 µs |
| `tts_diagnostics.describe_failure()`（**本轮新增路径**） | **0.538 µs** |

**真实合成墙钟（22 字句：「现在是下午三点整，顺便说一句，今天天气不错。」）**：

| 后端 | 结果 |
|---|---|
| `sapi`（离线本地，真 COM / 真 wav） | 3 轮全部成功：**首句 509.4 ms、复句 90.7 / 92.7 ms**，产物 270,708 字节 wav |
| `edge`（在线，edge-tts **7.3.1**） | **成功：3443 ms、26,640 字节 mp3**（ffprobe：mp3 / 24 kHz / 单声道 / 4.440 s / 48 kbps） |
| `edge`（在线，edge-tts **7.2.8**，同机同网络同代码） | **失败：`WSServerHandshakeError 403`**（分类后的用户可见串＝「在线语音握手被拒绝（HTTP 403）」；日志脱敏行 `type=WSServerHandshakeError version=7.2.8 http=403 route=system_proxy`） |
| `doubao` / `mimo` | 仍不可用（未配 Key），本轮同样未测 |

**逐条回答**：

1. **稳态开销**：本轮改动全部在「一次合成 / 一次失败」的路径上，**没有新增常驻线程、定时器、
   连接或后台循环**；报时预合成（`_maybe_precache`）、调度、播放侧语义一位未改
   （`_channel_idle`、看门狗、免打扰闸都逐字保留）。
2. **新增路径成本与触发频率**：`describe_failure()` **0.538 µs/次**，只在**合成失败**时调用
   （每条失败候选一次，最多 2 后端 × 2 次 = 4 次），相比一次合成（几百 ms ~ 数秒）可忽略。
   失败日志从「异常原文」改成「脱敏行」，字符串更短。
3. **有无新的系统调用/网络/磁盘/线程**：没有；**系统代理的解析次数还降了**——原实现
   每次 `_save()` 都问一次系统代理（重试 × 换音色最多 4 次），现在 `synth()` 解析一次、
   把结果显式传下去（用 `_PROXY_UNRESOLVED` 哨兵区分「没传」与「已确认直连」，
   所以无代理时也不再重复解析）。
4. **内存有无增长**：没有新增缓存/表；`_discard()`/`_EmptyAudio` 是函数与类型，无实例状态。
   （`describe_failure` 里的版本查询是 `lru_cache(maxsize=1)`，只查一次 `edge-tts` 元数据。）
5. **`modern_settings_dialog.py` 行数预算**：按实测 2533 校准（`wc -l`，见 5.1 表），
   不是为达标压行宽/合并语句。

### 5.3 实机运行记录（本轮）

```bash
# 1) 静态检查
$ python -m ruff check .
All checks passed!

# 2) 聚焦族（本轮改动的四个方向各跑一遍）
$ pytest -q tests/test_tts_edge.py tests/test_tts_diagnostics.py tests/test_tts_doubao.py \
        tests/test_tts_secrets.py tests/test_architecture.py
49 passed in 4.75s
$ pytest -q tests/test_voice_chime.py tests/test_voice_chime_service.py \
        tests/test_voice_chime_mimo.py tests/test_voice_chime_settings_layout.py
303 passed in 12.77s
$ pytest -q tests/test_festival.py tests/test_festival_settings_layout.py tests/test_config_schema.py \
        tests/test_settings_page_guide.py tests/test_menu_layout.py tests/test_settings_copy_lint.py \
        tests/test_desktop_pet_features.py
371 passed in 120.45s

# 2b) 代理解析改成「一次 + 哨兵」之后，TTS 三件套复跑（本报告的 5.2 第 3 条）
$ pytest -q tests/test_tts_edge.py tests/test_tts_diagnostics.py tests/test_voice_chime_service.py
137 passed in 6.20s

# 3) 全量（**按文件切 17 片、各起独立进程**——仓库口径：单进程全量会撞既存原生崩溃
#    0xC0000005，而分片崩一片只丢一片；PYTHONPATH=D:/dsh-pet-pr267-deps、QT_QPA_PLATFORM=offscreen）
$ python run_chunks_pr267.py 500          # 脚本：D:/dsh-pet-pr267-artifacts/run_chunks_pr267.py
collect 8026 用例 / 17 片（按文件切，每片 <= 500 用例）

==== 汇总 ====
c01  rc=0    107.6s  496 passed, 1 skipped          c10  rc=0     18.4s  376 passed
c02  rc=0     44.9s  486 passed, 6 skipped          c11  rc=0     64.0s  498 passed, 1 skipped
c03  rc=0    119.5s  499 passed                     c12  rc=1     24.1s  1 failed, 470 passed, 6 skipped
c04  rc=0     56.5s  403 passed, 6 skipped          c13  rc=0    242.0s  474 passed, 2 skipped
c05  rc=0     54.2s  498 passed                     c14  rc=0    142.6s  481 passed
c06  rc=0     64.4s  484 passed                     c15  rc=0     61.3s  496 passed
c07  rc=0     96.7s  481 passed, 2 skipped          c16  rc=0     21.3s  497 passed, 1 skipped
c08  rc=0     43.0s  470 passed                     c17  rc=0     62.1s  398 passed, 1 skipped
c09  rc=0     45.9s  492 passed

合计：passed 7999 / failed 1 / skipped 26（＝ 8026 用例全部跑到，17 片无原生崩溃）

# 3a) c12 那一条红的归因：**共享 venv 缺 requirements.txt 已声明的 omegaconf**，与代码无关
$ pytest -q tests/test_screen_capture_ocr.py::test_self_built_sessions_are_injected_into_the_engine_cfg
E   ModuleNotFoundError: No module named 'omegaconf'      # 调用发生在用例内部，所以不会被 skip

$ git diff --stat origin/main -- tests/test_screen_capture_ocr.py pet/screen_capture/
（空 —— 该用例与它测的产品代码与本支改动的并集逐字节相同，即 origin/main 的内容）

# 把缺的依赖装进**隔离目录**（不进全局）后，c12 整片 13 个文件全绿
$ pip install --target D:/dsh-pet-pr267-deps-ocr omegaconf
$ PYTHONPATH=D:/dsh-pet-pr267-deps:D:/dsh-pet-pr267-deps-ocr pytest -q <c12 的 13 个文件>
471 passed, 6 skipped in 23.94s
→ 补齐该声明依赖后的全量口径：**passed 8000 / failed 0 / skipped 26（8026 全跑到）**
```

**迁移的「先红后绿」取证（本轮改动的两个语义点各一对）**：

```bash
# 4) 失败诊断：迁移前会把异常原文（含签名 URL / 令牌 / 代理凭据）漏进用户可见错误串
$ git show 29a87be:pet/tts/edge.py > pet/tts/edge.py     # 换回本支 merge 前的版本
$ python probe_leak.py                                   # 脚本：D:/dsh-pet-pr267-artifacts/probe_leak.py
== 用户可见的错误串 ==
edge-tts 合成失败 → zh-CN-XiaoxiaoNeural 第1次: CredentialedFailure: \
    wss://host/?token=PRIVATE_TOKEN http://user:PRIVATE_PASSWORD@proxy；…
凭据漏进用户可见错误串：True          # ← 红（日志里则一个字都没记，排查也无从下手）

$ cp <候选版> pet/tts/edge.py && python probe_leak.py
== 用户可见的错误串 ==
edge-tts 合成失败 → 在线语音握手被拒绝（HTTP 403）；在线语音握手被拒绝（HTTP 403）
== 日志 ==
edge-tts 合成失败（zh-CN-XiaoxiaoNeural 第1次）：在线语音握手被拒绝（HTTP 403）; \
    type=CredentialedFailure version=7.3.1 http=403 route=system_proxy
凭据漏进用户可见错误串：False         # ← 绿（分类后的人话 + 脱敏日志行）

# 5) main 那份 diagnostics 用例在**合并树上本来就是红的**（所以它必须跟着合成链路迁走）
$ pytest -q /d/dsh-pet-pr267-artifacts/red_test_tts_diagnostics.py   # = origin/main 的版本
E   AttributeError: … 'pet.voice_chime_service' has no attribute 'refresh_voice_list'
4 failed in 0.55s
```

**真实合成与 A/B（这一轮补上的「实机」部分）**：

```bash
$ PR267_REPO=D:/dsh-pet-wt-pr267 PYTHONPATH=D:/dsh-pet-pr267-deps \
      python bench_pr267.py            # 7.3.1
== 2. 离线后端 sapi ==
  round1:    509.4 ms  270708 bytes
  round2:     90.7 ms  270708 bytes
  round3:     92.7 ms  270708 bytes
== 3. 在线后端 edge ==
  edge-tts 版本： 7.3.1
  合成成功：3443 ms，26640 bytes -> D:\dsh-pet-pr267-artifacts\edge-probe.mp3

$ ffprobe -v error -show_entries stream=codec_name,sample_rate,channels edge-probe.mp3
codec_name=mp3  sample_rate=24000  channels=1

$ PYTHONPATH=D:/dsh-pet-pr267-deps-728 python -c "…edge_mod.PROVIDER.synth(…)…"
edge-tts = 7.2.8
edge-tts 合成失败（zh-CN-XiaoxiaoNeural 第1次）：在线语音握手被拒绝（HTTP 403）; \
    type=WSServerHandshakeError version=7.2.8 http=403 route=system_proxy
失败： RuntimeError edge-tts 合成失败 → 在线语音握手被拒绝（HTTP 403）；在线语音握手被拒绝（HTTP 403）

# 4) 构建期版本门禁（requirements 的 floor 真的会被执行）
$ PYTHONPATH=D:/dsh-pet-pr267-deps     python scripts/verify_bundle_tts.py --environment
[tts] build edge-tts 7.3.1 OK (<8,>=7.3.1)                       # exit 0
$ PYTHONPATH=D:/dsh-pet-pr267-deps-728 python scripts/verify_bundle_tts.py --environment
[tts] FAIL unsupported-edge-tts-build-version                     # exit 6
{"build_version": "7.2.8", "required_version": "<8,>=7.3.1", "error": "unsupported-edge-tts-build-version"}
```

这三条合起来说明两件事：① 287 的**脱敏诊断在真失败里确实生效**（分类后的错误串 + 脱敏行，
未出现 URL / 令牌 / 代理凭据）；② 新链路在**真网络下真的能出音频**，不是只过了打桩。

**precaching 公有接口的兼容说明（给 PR290「每日一签」后续集成）**：写入
`D:/dsh-pet-pr267-artifacts/PRECACHE-COMPAT-NOTE-FOR-290.md`（与本报告同轮、不在仓库里，
不进候选 SHA）。要点：290 的 `precache()` 依赖的 `resolve_voice` / 平铺 `cache_key` /
`_EDGE_TTS_AVAILABLE` / `_announce_voice_substitution` 在本支已不在服务层，须改走
`_usable_attempts()` + `_cache_path(text, attempt)`；且它加在 `_fire` 命中分支的
「`role == "precache"` 不许起播」守卫在本支的 `for out_path in paths` 循环里**不会干净应用**，
不改就会出现「只想预合成、却偷偷播一次」。本轮**不与 290 合并远端**，顺序由主代理统一排。

### 5.4 未验到 / 边界（本轮）

1. **「无网络时合成」这一格仍未验**：本轮是真网络环境，edge 走通了；**断网 / 代理全灭时
   的现场行为**没有真实复现（只有打桩覆盖失败分类与降级文案）。能在无网络环境里真正出声的
   只有 `sapi`（离线，本轮实测 509/91/93 ms），而 `sapi` 依赖本机已装 SAPI5 中文语音包，
   换一台机器结论可能不同。
2. **设置页 / 语音域在打包产物里的实机观感**未复验：本轮只跑源码与用例，未重新出包。
3. **`doubao` / `MiMo` 在线后端仍未实测**：要用户自备 Key（凭据只进用户钥匙串，仓库与 CI
   里拿不到）——这一格从第一轮起就一直挂着，本轮没有变化。
4. **合成成功只到 `provider.synth()` 产出文件**：没有走「服务层 → QtMultimedia 播放」的
   真实出声路径（那要真的响一声），播放侧承重仍靠既有用例。
5. **`pet/tts/base.py` 声称的架构守卫**在第一轮其实不存在，本轮才补上（见 5.1）；
   说明这类「文档写了、机器没守」的缺口值得单独扫一遍。
6. **同一份音色真相仍有两份副本（已核实，本轮不改）**：`pet/voice_chime.py` 里还留着
   `VOICE_OPTIONS`（36 条）/ `DEPRECATED_VOICE_LABELS` / `voice_label()`，与
   `pet/tts/edge.py` 的那一份**逐条相同**（已用脚本逐项比对：条数 36 vs 36、集合相等、
   `voice_label` 对全部 36 条结果一致），且**产品代码已无人读它们**（只剩
   `tests/test_voice_chime.py` / `test_voice_chime_service.py` 按老路径导入做断言；
   `pet/` 之外零引用）。这正是本 PR 报告第一节所说的「同一份逻辑留两处副本，改动漏一处
   就会分叉」——今天还没分叉，但下一次改音色清单只改一处就会。**本轮不顺手删**：
   它超出了「合并 main」的范围，且会动 `pet.voice_chime` 的模块面；建议作为独立小刀处理
   （同文件第 84–98 行已有现成写法：`MIMO_VOICE_OPTIONS = _mimo_provider.MIMO_VOICE_OPTIONS`、
   `voice_label = _edge_provider.voice_label` 即可，消费方与用例一并指过去）。
