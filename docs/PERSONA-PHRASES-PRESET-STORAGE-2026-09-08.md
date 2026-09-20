# 台词预设存储与加载架构（2026-09-08，persona-presets-data）

本文描述桌宠「表达风格 / Agent 联动文案」（dialogue）子系统的**存储与加载**
架构：哪些是代码、哪些是数据、何时加载、按什么路由。字段/参数对齐审计见
`docs/PERSONA-TEMPLATE-FIELD-ALIGNMENT-2026-09-05.md`（本文不重复）。

## 1. 三类内容的归属（一句话版）

| 内容 | 归属 | 位置 | 加载时机 |
|---|---|---|---|
| 内置预设文案（legacy / whale_maid） | **数据文件**，随代码分发 | 仓库 `pet/persona_presets/<mode>.json` | 启动/模块导入一次；重设/切回内置时重新读盘 |
| 用户台词（custom） | **用户数据** | `%APPDATA%/dsh-pet-standalone/config.json` 的 `dialogue_phrases`（打包变体目录/多开 `config-<instance>.json` 同理） | 随 Config 加载/归一化 |
| 便携模板（导出文档） | **运行时生成**，不落盘 | `pet/persona_template.py` `build_persona_template()` | 设置页导出时生成给用户复制 |

原则：**台词文案不写死在代码里**。改内置口吻 = 改 `pet/persona_presets/` 下
的 JSON；用户编辑只写 config.json；不要新增任何内嵌文案的 Python 常量。

## 2. 内置预设：数据文件 + 注册表

- 数据：`pet/persona_presets/legacy.json`（默认模式/正式口吻）、
  `whale_maid.json`（鲸鱼娘女仆模式）。均为扁平
  `{event_key: [文案…]}`，36 个事件 key，每 key ≤8 条、每条 ≤240 字
  （载入时清洗）。键集合即事件词表（无独立硬编码词表）。
- 加载：`pet/persona_phrases.py`
  - `load_builtin_presets()`：模块导入（启动）时读盘全部内置预设 →
    模块级注册表 `_presets`。
  - `reload_builtin_presets()`：重新读盘入口（数据契约由测试锁定；当前无生产
    调用方，待设置页提供「重设/恢复内置」后再接线）；已持有的
    `PhrasePicker` 无需重建（渲染每次实时读注册表）。
  - `builtin_phrases(mode)`：取某模式当前预设（未知/未加载 → 空 → 调用方 fallback）。
  - 触发点：模块导入即加载（设置页 `pet/exploration_watchdog_settings.py` 等
    界面改版后，运行时「切换内置风格重载」入口已随孤儿方法移除）。
- 渲染：`PhrasePicker.get(mode, key, fallback, autohide=None, **values)`
  —— 命中预设即取变体渲染（轮换避免同 key 连续重复）；缺失/未知模式原样回退。
- 事件词表 `phrase_keys()` = 内置预设键并集；`default_phrases()` = 每个 key
  首个非空变体（legacy 优先、whale_maid 兜底），仅供设置页默认填充。
- 打包：`pet/persona_presets` 目录整体随 `scripts/build_onedir.ps1`、
  `build_linux.sh`、`build_macos.sh` 以 add-data 打入（`*.spec` 是 gitignore
  的本地构建产物，不入库）。加载用 `Path(__file__).with_name("persona_presets")`，
  冻结版同路径成立。

## 3. 表达风格（dialogue_mode）语义

取值 `legacy / whale_maid / custom`（`config.py` 归一化，非法回 `legacy`）。

- `legacy`（默认模式）：命中 `persona_presets/legacy.json` 的预设文案。
  ⚠️ 2026-09-08 起**不再透传调用方原文案**——legacy 与 whale_maid 一样是
  JSON 预设（用户拍板），默认模式可见气泡文案因此由数据文件决定。
- `whale_maid`（鲸鱼娘）：命中 `persona_presets/whale_maid.json`（2026-09-08
  换用完整 3 句/事件版本，含 `llm_error.api`）。
- `custom`（自定义台词）：渲染 **用户预设**（config `dialogue_phrases`），
  两级：`global`（默认+全部非 Agent 事件）+ `agents[agent_key]`（delta 覆盖）。

渲染分派（`pet/agent_link.py` `_dialogue()`；`pet/app.py` `_persona_text()` 同构）：

```
mode == custom : agents[agent_key][key] → global[key] → 调用方原文案
mode ∈ {legacy, whale_maid} : 内置预设[key] → 调用方原文案
```

## 4. 用户台词（custom）持久化与 agent 路由

- 持久化：config.json `dialogue_mode` + `dialogue_phrases`。加载时
  `Config._normalize_pet_settings()`（`config.py`）清洗：
  - 双层 `{global: {…}, agents: {agent_key: {…}}}` 逐事件校验值类型并保留结构；
  - 旧式扁平 `{event: [...]}` 视为 global 层；
  - 每 key ≤8 条、每条 ≤240 字；agents 里无有效覆盖的 key/agent 会被清理。
- 运行路由（`persona_phrases.py`）：`phrase_for_agent()` /
  `PhrasePicker.custom_for_agent()`：`agents[agent_key][key] → global[key]`；
  `agent_key=""`（非 Agent 场景，如自言自语/余额）只读 global。
- 专属层覆盖范围：只有渲染点把 `agent_key` 传给 `_dialogue()` 的事件才走
  per-Agent 专属层，且**专属层只在 custom 模式读**。当前带路由的转述事件：
  `start / thinking / activity.* / done.success / done.attention /
  agent.attention / agent.error`。审批/提问/失败/模型访问失败/卡住/模式等「对你说」
  的事件与 `bridge.*`、`agent.missing` 只走 global。
  （2026-09-08 用户确认：**不做**「内置风格 + per-Agent 覆盖」叠加，保持现状。）
- 结构引导不随台词覆盖：自由文本问题/含文本分支的「请到 DSH 界面输入文本
  回答」由 `agent_link._with_dsh_input_hint()` 兜底补上。

## 5. 模板导出/导入（persona-phrases/v1）

- 导出：`persona_template.build_persona_template(config)` 以当前
  `dialogue_phrases`/`dialogue_mode` 为数据源生成文档，`_说明` 段导入时忽略；
  设置页「一键复制模板」导出纯字段参考模板（phrases 留空供 AI 从零撰写）。
- 导入：校验 `template` 前缀 `persona-phrases/` 后把 `phrases` 写回编辑区 /
  `agents` 写回专属层 scope buffer，随保存写入 config；顶层 `mode` 仅提示。
- 事件 schema 真源在 `persona_template.py`（`PARAMETERS`/`EVENT_SOURCES`/
  `DISPLAY_HINTS`/`CONDITIONAL_PARAMETERS`）；不变量（有测试）：
  `set(PARAMETERS) == phrase_keys() == entries` key 集合。

## 6. 历史遗留（已删除，勿恢复）

- `pet/persona_phrases.py` 内 ~150 行硬编码 `_PHRASES` 与导入时
  `persona_phrases.json` 的合并逻辑（2026-09-08 删除）。
- `pet/persona_phrases.json`（旧 whale_maid 2 句版，已被
  `persona_presets/whale_maid.json` 取代，2026-09-08 删除）。
- `pet/persona_phrases_templates/{legacy,whale_maid,custom}.json`（无代码加载
  的孤立文件，内容迁入 `persona_presets/`，2026-09-08 删除目录）。

## 7. 维护约定

- 改某模式口吻：编辑对应 `pet/persona_presets/*.json`（不要动代码）。
- 新增/删除事件 key：需同步 `persona_template.PARAMETERS/EVENT_SOURCES/
  DISPLAY_HINTS/CONDITIONAL_PARAMETERS` 与两份内置预设 JSON 的键
  （`tests/test_persona_presets.py` 锁键一致；`test_persona_template.py`
  锁 schema==词表==entries）。
- 预设文案占位符只能使用该事件 `PARAMETERS` 声明的字段（保证或条件注入），
  越界会原样露出 `{xxx}`——`tests/test_persona_presets.py` 有契约测试。
- 测试防线：`tests/test_persona_presets.py`（数据契约/加载/轮换/回退）、
  `tests/test_persona_settings.py`（config 清洗与 phrase_for_agent/custom_for_agent
  路由）、`tests/test_persona_template.py`（schema 对齐）、
  `tests/test_agent_link.py`（气泡文案族）。
