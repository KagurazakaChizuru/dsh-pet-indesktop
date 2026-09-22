# 接入一个新的 TTS 后端（provider 指南）

语音报时的合成后端是**注册表 + 声明式 provider**：核心代码（调度、缓存、设置页、
服务层）只认接口，不认具体厂家。接入新 TTS 的标准动作是「加一个模块 + 在包里注册
它」，**不需要改** `voice_chime.py` / `voice_chime_service.py` / `voice_chime_settings.py`
（配置键由 provider 自己声明，`config.py` 会自动收编）。

> 代码位置：接口与注册表 `pet/tts/base.py`；内置实现 `pet/tts/edge.py`（edge-tts）、
> `pet/tts/mimo.py`（小米 MiMo）。契约由 `tests/test_voice_chime_mimo.py::
> test_every_registered_provider_satisfies_the_contract` 机器化守卫。

---

## 一、四步接入

### 1. 写 provider 模块 `pet/tts/<name>.py`

```python
from .base import TtsField, TtsProvider, TtsUnavailable, register


class MyTtsProvider(TtsProvider):
    id = "mytts"                     # 配置里存这个 id（小写、稳定，别改名）
    label = "某家 TTS（需 Key）"      # 设置页下拉里的展示名
    is_fallback = False              # True = 别人失败时可回退到它
    availability_code = "mytts-key-missing"   # 不可用原因码（见第 3 步）
    unavailable_message = "某家 TTS 未配置 API Key：设置 → 语音 → 语音报时 里填一次"

    fields = (
        TtsField("voice", "voice_chime_mytts_voice", "音色",
                 kind="select", default="默认音色",
                 options=(("默认音色", "默认音色"), ("另一种", "另一种"))),
        TtsField("api_key", "voice_chime_mytts_api_key", "API Key",
                 kind="secret", default="", secret_ref="tts/mytts"),
    )

    def plan(self, values):          # 纯：产出合成描述，ext 决定缓存扩展名
        return {"provider": self.id, "voice": values.get("voice"), "ext": "mp3"}

    def flavor(self, values):        # 纯：进缓存键的片段（只放影响音频内容的参数）
        return f"mytts|{values.get('voice')}"

    def availability(self, values):  # 纯：空串=可用；不联网，只看配置/依赖探测
        return "" if values.get("api_key") else self.availability_code

    def synth(self, text, plan, out_path):   # IO：后台线程里跑，失败就抛
        try:
            import my_tts_sdk
        except Exception as exc:
            raise TtsUnavailable(self.availability_code, f"依赖不可用：{exc}") from exc
        data = my_tts_sdk.render(text, voice=plan["voice"], key=plan["api_key"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)


PROVIDER = register(MyTtsProvider())
```

### 2. 在 `pet/tts/__init__.py` 里 import 它

```python
from . import edge, mimo, mytts  # noqa: F401 —— import 即注册
```

注册顺序决定设置页下拉顺序；被标了 `is_fallback = True` 的会进回退链，
所以**别把多个后端都标成 fallback**，除非你确实想要一条多级链。

### 3. 在 `pet/config.py` 里什么都不用做

`Config.__init__` 与 `reload()` 会遍历 `tts.providers()` 把每个字段的 `key`
自动收进默认值与 reload 白名单——只要你按第 2 步 import 了，键就不会漏。
**唯一要改的测试**是 `tests/test_config_schema.py` 的快照集合（那是刻意的门禁）。

### 4. 补测试

- 抄 `tests/test_voice_chime_mimo.py` 的骨架：纯逻辑（plan/flavor/清洗）+ 服务层
  （`synth` 用 monkeypatch 假掉 HTTP，不打真网络）；
- 契约用例会自动把你的 provider 一起验（字段键前缀、`plan["ext"]`、secret_ref…）。

---

## 二、接口契约（写之前先看）

| 成员 | 层级 | 要求 |
|---|---|---|
| `id` / `label` | 声明 | 必填；`id` 会进用户配置，改名等于丢配置 |
| `fields: tuple[TtsField, ...]` | 声明 | 每个可配置项一条；`key` 必须是 `voice_chime_` 前缀的顶层配置键 |
| `values(config)` | 纯 | 有默认实现（按 `fields` 读 + `clean`）；键既支持正式配置键也支持短名 |
| `clean(spec, raw)` | 纯 | 有默认实现（按 `kind` 清洗）；要更严的校验就覆写 |
| `plan(values) -> dict` | 纯 | **必须**含 `provider` 与 `ext`；其余字段由 `synth` 自解释 |
| `flavor(values) -> str` | 纯 | 进缓存键；**不得**含密钥、时间戳等不稳定内容 |
| `availability(values) -> str` | 纯 | 空串=可用；否则返回原因码（离线判定，不许联网） |
| `preflight(values) -> (values, note)` | 纯 | **不许联网**；把「配置里已失效的东西」换成能用的（如被下架的音色 → 默认音色），`note` 会作为一次性气泡转达给用户。默认原样返回 |
| `synth(text, plan, out_path)` | IO | 在后台线程跑；缺依赖/凭据抛 `TtsUnavailable(code)` |

字段类型（`kind`）与设置页控件对应：

| kind | 控件 | 额外声明 |
|---|---|---|
| `select` | 下拉 | `options=((value,label),...)`；`allow_custom` 控制是否补「自定义：<值>」 |
| `number` | 数字框 | `minimum` / `maximum` / `suffix` |
| `flag` | 开关 | `default=True/False` |
| `text` | 单行输入 | `placeholder` / `max_length` |
| `secret` | 密码框 + 清除按钮 | `secret_ref`（存系统钥匙串，**绝不进 config.json**） |

字段间依赖用 `hidden_when=(另一个字段的 name, 值)` 声明（例：MiMo 选「音色设计」
模型时隐藏内置音色行），设置页自动处理，不需要写 UI 代码。

---

## 三、红线

0. **对「配置里已不成立的东西」必须兜底**：在线音色会被厂家下架、模型名会被改名——
   用户配的是**当时有效**的值，之后失效时不能只表现为「没声音」。做法：
   ``preflight(values)`` 在 GUI 线程（**不联网**，只看缓存/内置清单）把失效值换成可用的
   并返回一句面向用户的说明；``synth()`` 里再重试 + 退默认值兜一层。范例见
   ``pet/tts/edge.py``（晓涵等 10 款音色 2026-09-22 被微软下架那次事故）。
1. **`pet/tts/*.py` 模块顶层不得 import Qt**，也不得 import 重量级/可选依赖
   （`edge_tts` 这种惰性到 `synth()` 里）——`tests/test_architecture.py::
   test_pure_logic_modules_do_not_import_qt` 会红。
2. **密钥只走 `secret_ref` → 钥匙串**；`config.json`、日志、缓存键里都不许出现。
3. **缓存键必须只依赖 `flavor()`**：换音色/换风格要换键，换密钥/换展示文案不该换键
   （否则同一个声音会被重复合成、旧音频被当成新后端的声音播放）。
4. **失败要抛 `TtsUnavailable`**，不要静默产出空音频：服务层据此回退到链上的下一个
   后端，并给出 provider 自己声明的 `unavailable_message`。
5. 新增 provider 后**跑一次全量 pytest**：契约用例、配置快照、设置页行数断言都会跟着动。
