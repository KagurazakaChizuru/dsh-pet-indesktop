# 语音报时接入小米 MiMo TTS（PR 报告，2026-09-22）

- 分支：`feat/media-window-fallback`（合并 origin/main #173 之后）
- 目标：把桌宠语音报时的合成后端从 edge-tts 扩成「可切换」，并**默认走小米 MiMo**
- 用户原话：> 「我想把tts换成小米的，你看看怎么处理。」

---

## 一、为什么是这套接口

小米 MiMo 的语音合成走**开放平台的 OpenAI 兼容接口**（`mimo.mi.com` /
`platform.xiaomimimo.com` 文档）：

| 项 | 值 |
|---|---|
| 端点 | `POST https://api.xiaomimimo.com/v1/chat/completions` |
| 鉴权 | `api-key: <KEY>`（官方 curl）；OpenAI SDK 走 `Authorization: Bearer <KEY>`；两个都带 |
| 模型 | `mimo-v2.5-tts`（内置音色）/ `mimo-v2.5-tts-voicedesign`（文字描述生成音色）/ `…-voiceclone` |
| 内置音色 | 中文：冰糖（默认）/ 茉莉 / 苏打 / 白桦；英文：Mia / Chloe / Milo / Dean |
| 文本位置 | **待合成文本必须放在 `assistant` 消息**；`user` 消息是可选风格指令（音色设计模型下必填） |
| 音频 | 响应 `choices[0].message.audio.data`（base64）；非流式请求 `audio.format=wav` |
| 计费 | 官方标注「限时免费」 |

据此，音色/风格/模型都成了**配置**，而请求体构造与响应解析是**纯函数**——可离线单测。

## 二、设计要点

1. **后端不清零，只加成一条链**：`synth_attempts(cfg)` 产出「主后端 → 后备后端」的
   尝试序列。默认 `voice_chime_tts_backend=mimo`、`voice_chime_tts_fallback=True`，
   即「先试小米，失败自动回退 edge-tts」。用户把回退关掉、或把后端切回 edge，
   行为与改造前完全一致。
2. **缺 Key 不白打网络**：`_usable_attempts()` 在 GUI 线程先摘掉「缺库 / 缺 Key」的
   后端——没填 Key 时不发那次注定 401 的请求，直接走 edge。
3. **缓存键按后端隔离**：`cache_key(text, cfg)` 的后端分支参与哈希。edge 分支
   **保持历史格式逐字节不变**（老 mp3 缓存升级后仍命中）；MiMo 分支带
   `model|voice|style`。缓存文件扩展名随后端：edge `.mp3`、MiMo `.wav`。
4. **缓存裁剪覆盖两种产物**：`_prune_cache` 原来只 glob `*.mp3`，MiMo 的 wav 会永远
   不被裁——已改为同时统计 `.mp3` / `.wav`（新增回归用例）。
5. **凭据只进钥匙串**：新增 `pet/tts_secrets.py`（服务名与 chat 的 `SecretStore` 一致
   `dsh-pet-standalone`，ref = `tts/mimo`）。**不复用 `pet.chat.models.SecretStore`**：
   no-chat 打包变体会 exclude 掉 `pet.chat`，而语音报时设置页两条链路都要能打开。
   keyring 不可用时退化为进程内存（本次运行有效），设置页据此提示。
6. **降级文案可操作**：新增错误码 `MIMO_KEY_MISSING`，提示写清「设置 → 语音 → 语音报时
   里填一次即可」，而不是笼统的「合成失败」。
7. **网络走 `pet/http_util`**：先按系统代理试、传输失败改直连（同一批歌词/余额修复的
   教训——她的系统代理曾被加速器留下一个没人监听的端口）。

## 三、改动清单

| 文件 | 变动 |
|---|---|
| `pet/voice_chime.py` | 纯逻辑层（644 行，仍零 Qt / 零 edge_tts）：后端与 MiMo 常量、`clean_backend/clean_mimo_*`、`synth_ext`、`synth_attempts`、`mimo_messages/mimo_payload/parse_mimo_audio`、`normalize_chime_config` 与 `cache_key` 扩展 |
| `pet/tts_secrets.py` | 新增（92 行）：钥匙串优先、进程内存兜底的凭据存取，不依赖 Qt / pet.chat |
| `pet/voice_chime_service.py` | `_TTSWorker` 改为「按尝试链合成，首个成功者写盘回调」；新增 `_synthesize_mimo`（HTTP + base64）、`_usable_attempts`、`_cache_path`、`_clear_precache`、`_notify_unavailable`；缓存裁剪覆盖 wav |
| `pet/voice_chime_settings.py` | 新增「合成后端」卡片域 6 行：语音引擎 / 失败自动回退 / MiMo 模型 / MiMo 音色 / 风格指令 / MiMo API Key（含「清除」按钮）；切后端时 edge 的语速/音调/音色行与 MiMo 行互显隐；音色设计模型下隐藏内置音色行 |
| `pet/config.py` | 新增 5 个顶层键（默认值 dict + `reload()` 白名单） |
| `tests/test_voice_chime_mimo.py` | 新增 17 用例：纯逻辑（清洗/尝试链/缓存键隔离/请求体/响应解析）+ 服务层（请求形状、写盘、缺 Key、回退接棒、主错误上报、可用性预判、wav 裁剪）+ 设置页与凭据 |
| `tests/test_tts_secrets.py` | 新增 6 用例：钥匙串往返 / 内存兜底 / 写失败保内存 / 空值清除 / 读异常降级 / ref 命名 |
| `tests/test_voice_chime.py` / `test_voice_chime_service.py` / `test_config_schema.py` / `test_menu_layout.py` | 按新契约校准：默认键快照 +5、`_WorkerSpy` 与 `_TTSWorker` 构造签名、语音报时行数 12 → 18 |

## 四、验证

- `ruff check pet/ tests/` 干净。
- 全量 `pytest -q`：**2895 passed / 11 skipped / 0 failed**（改造前 2871，新增 24 用例）。
- 网络与凭据在测试中一律 monkeypatch：**没有任何用例打真网络或写真钥匙串**。
- 打包版冒烟见 `docs/DEV-HANDOVER.md`（构建门禁全过、安装到 D: live 与 H: 副本）。

## 五、已知限制与后续

1. **真实 API 已验证**（2026-09-22，同日第二轮之后）：用钥匙串里已保存的 `tts/mimo`
   凭据直接走 provider 的 `plan()` + `synth()` 打真接口，返回 **199,724 字节、文件头 `RIFF`**
   的 wav（`mimo-v2.5-tts` / 冰糖 / 风格指令「轻快、带点笑意」）。请求形状与响应解析均确认无误。
2. 流式接口（`stream=true` + `pcm16`）未接入：报时是「一句话」场景，非流式一次拿
   wav 更简单；将来要做边说边播再评估。
3. `mimo-v2.5-tts-voiceclone`（声音克隆）未开放到界面：需要音频样本与上传流程，
   与「零额外步骤」的偏好冲突，先不做。
4. 音色设计模型的 `optimize_text_preview` 参数未使用（该模型已要求 user 消息描述音色）。

## 六、风险与回滚

- 影响面：仅语音报时的合成路径；`voice_chime_enabled` 默认关闭，报时本身也只在
  命中调度时才走这条链。
- 失败即回退：没配 Key / 接口报错 / 网络不通 → 自动用 edge-tts；两个都不行 → 只出
  气泡不出声（与改造前的缺依赖降级同款）。
- 回滚：把 `voice_chime_tts_backend` 设为 `edge`（或关掉 `voice_chime_tts_fallback`
  观察主后端错误）即可；代码级回滚到本次提交之前的 `dist-onedir` 备份
  （`*.bak-<时间戳>`）也能立刻恢复旧声音。

---

## 七、第二轮：把 TTS 抽象成接口（2026-09-22 同日）

> 用户追加要求：**「TTS的相关部分应该抽象为接口化。以便后续随意接入其他tts」**

第一轮虽然做成了「可切换后端」，但后端知识散在四处：`synth_attempts` 里写死两家、
`_TTSWorker` 里 if/else 分派、设置页硬编码 MiMo 的四行、错误码与提示也各写一遍。
**接入第三个 TTS 仍要改 5 个文件**——这正是第二轮要消掉的东西。

### 7.1 分层

新增 `pet/tts/` 包（接口 + 注册表 + 内置 provider）：

| 文件 | 行数 | 职责 |
|---|---|---|
| `tts/base.py` | 219 | `TtsField`（声明式配置项）、`TtsProvider`（values/plan/flavor/availability/synth）、注册表 |
| `tts/edge.py` | 171 | edge-tts 实现（音色表、rate/pitch、`find_spec` 惰性探测、`is_fallback=True`） |
| `tts/mimo.py` | 201 | 小米 MiMo 实现（模型/音色/风格指令/密钥；HTTP 与 base64 解析都在这里） |
| `tts/__init__.py` | 43 | import 即注册；新 provider 加一行 |

边界就是**纯 / IO**：`values/plan/flavor/availability` 全是纯函数（可离线单测），
只有 `synth()` 有 IO 且允许惰性 import 依赖——`pet/tts/*.py` 一并纳入
`test_pure_logic_modules_do_not_import_qt` 的机器化守卫。

### 7.2 核心代码不再认得任何厂家

- `voice_chime.py`：`BACKENDS`/`BACKEND_LABELS` 来自注册表；`synth_attempts()` 按
  provider 的 `plan()` 产出尝试链；`cache_key()` 用 provider 的 `flavor()`；
  `normalize_chime_config()` 产出 `providers: {pid: 字段值}` 再加历史平铺键（兼容旧调用点）。
- `voice_chime_service.py`：`_TTSWorker` 只剩「逐条 call `provider.synth`，失败换下一条」；
  可用性预判、错误码、提示文案全部来自 provider 声明。
- `voice_chime_settings.py`：**设置页按 `fields` 生成控件**——「合成后端」卡片不再有
  MiMo 专用的四行代码；切后端显隐、字段间依赖（`hidden_when`）、密钥框 + 清除按钮
  都是通用的。新增 TTS 不需要碰 UI。
- `config.py`：provider 字段键由注册表遍历自动收编进默认值与 reload 白名单，
  以后加后端不用改 `config.py`。

### 7.3 「随意接入」的证据

不是口头承诺，而是三条用例 + 一份指南：

- `test_every_registered_provider_satisfies_the_contract`：把接口契约变成机器化清单
  （字段键前缀、`plan["provider"]`/`plan["ext"]`、`flavor` 稳定性、secret 必须给 ref…），
  新 provider 自动被它验；漏声明什么，它会指出来。
- `test_third_party_provider_plugs_into_registry_and_chain`：注册一个假后端后，
  它自动出现在引擎清单、进尝试链、拿到自己的扩展名与隔离的缓存键。
- `test_third_party_provider_renders_settings_rows_without_ui_edits`：假后端的字段行
  自动出现在设置页，普通字段写回 config、密钥字段按 `secret_ref` 进钥匙串、且不进 config。
- `docs/ADDING-A-TTS-PROVIDER.md`：四步接入流程 + 契约表 + 红线（已登记进 `docs/INDEX.md`
  与 `AGENTS.md` 的 Context pointers）。

**结论：接入一个新的 TTS = 写一个 provider 模块 + 在 `pet/tts/__init__.py` 加一行 import。**

### 7.4 验证

- `ruff` 干净；全量 **2899 passed / 11 skipped / 0 failed**（第二轮前 2896）。
- 真实接口验证见 §五.1。
- 打包与部署：重建 onedir（slim/编码/DLL/双启动冒烟全过）并同步到本机两处实例。
