# -*- coding: utf-8 -*-
"""Agent 事件协议：bounded_data 修剪语义 + schema 版本白名单。"""

import json
import logging

import pytest

from pet.agent_event_protocol import (
    MAX_DATA_BYTES,
    MAX_STRING_CHARS,
    MIN_CONTENT_STRING_CHARS,
    SCHEMA,
    AgentEvent,
    EventPayloadTooLarge,
    bounded_data,
    parse_agent_event,
)


def _size(raw: dict) -> int:
    return len(json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def test_bounded_data_small_payload_unchanged():
    payload = {"a": 1, "b": "text", "c": [1, 2, 3]}
    assert bounded_data(payload) == payload


def test_bounded_data_trims_oversized_value_instead_of_emptying():
    """单个大值超限时应修剪到预算内，而不是把整本 dict 删空。"""
    payload = {"tool": "read_file", "content": "x" * 200_000}
    raw = bounded_data(payload)
    assert raw, "超限不应清空整个 dict"
    assert "tool" in raw and "content" in raw
    assert _size(raw) <= MAX_DATA_BYTES


def test_bounded_data_single_huge_nested_value_keeps_outer_key():
    """单个键承载的嵌套结构超限时：必须修剪内容，而不是把这个键整个删掉。

    旧实现从最后插入的键开始 pop，单键超限 → 返回 {}（整个 dict 清空），
    调用方拿到的 data 为空，事件语义全部丢失。
    """
    payload = {"tool": "read_file", "content": {f"k{i:03d}": "v" * 2000 for i in range(128)}}
    raw = bounded_data(payload)
    assert "tool" in raw, "单键超限不应把整个 dict 清空"
    assert "content" in raw
    assert _size(raw) <= MAX_DATA_BYTES


def test_bounded_data_many_keys_stays_within_budget_and_keeps_keys():
    payload = {f"k{i:03d}": "v" * 2000 for i in range(128)}
    raw = bounded_data(payload)
    assert _size(raw) <= MAX_DATA_BYTES
    # 值先修剪：大多数键应保留，而不是从尾部删到空
    assert len(raw) >= 32


def test_bounded_data_non_mapping_returns_empty():
    assert bounded_data("not a mapping") == {}
    assert bounded_data(None) == {}


def test_parse_agent_event_accepts_current_schema():
    ev = parse_agent_event({"schema": SCHEMA, "event": "AgentStatus"})
    assert isinstance(ev, AgentEvent)
    assert ev.schema == SCHEMA


def test_parse_agent_event_missing_schema_defaults_to_current():
    ev = parse_agent_event({"event": "AgentStatus"})
    assert ev.schema == SCHEMA


def test_parse_agent_event_unknown_schema_rejected(caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ValueError):
            parse_agent_event({"schema": "agent-event/v99", "event": "AgentStatus"})
    assert "agent-event/v99" in caplog.text


# --------------------------------------------------------------------------
# 超限修剪必须保护"消费依赖的短值"（枚举 / ID / 错误状态）
#
# 反例（全局 str_cap 一路压到 1 的实现，本批实测）：一个 34KB 的 tool/result
# 负载会把 ok:'error' 剪成 'e'、tool:'write' 剪成 'w'、
# failure.code:'429' 剪成 '4'、failure.message:'rate limit exceeded' 剪成 'r'。
# 后果不是"内容少了"，是控制流被改：ModelAccessTracker._resets 判
# `data['ok'] not in (False,0,'false','error')` → 失败被当成成功；
# is_model_access 认不出 429 → 限流连续计数不涨。
# --------------------------------------------------------------------------

_FILLER = {f"k{i:03d}": [0] * 128 for i in range(128)}  # 纯数字，无字符串可压


def test_bounded_data_protects_short_enums_ids_and_error_state():
    payload = {
        "ok": "error",
        "tool": "write",
        "sessionId": "4f9c1e2a-3b7d-4a51-9c8e-77aa11bb22cc",
        "failure": {"code": "429", "message": "rate limit exceeded"},
        "content": _FILLER,
    }
    assert _size(payload) > MAX_DATA_BYTES, "前置：该负载必须真的超限"

    raw = bounded_data(payload)

    assert raw["ok"] == "error", f"ok 被剪坏：{raw.get('ok')!r}"
    assert raw["tool"] == "write", f"tool 被剪坏：{raw.get('tool')!r}"
    assert raw["sessionId"] == "4f9c1e2a-3b7d-4a51-9c8e-77aa11bb22cc"
    assert raw["failure"] == {"code": "429", "message": "rate limit exceeded"}, \
        f"failure 被剪坏：{raw.get('failure')!r}"
    assert _size(raw) <= MAX_DATA_BYTES


def test_bounded_data_keeps_semantic_keys_when_tool_is_last():
    """语义字段排在最后也不得被"从尾部删键"删掉（旧实现按插入顺序删）。"""
    payload = {"content": _FILLER, "big2": {f"j{i}": "z" * 3000 for i in range(64)},
               "ok": "error", "tool": "write"}
    raw = bounded_data(payload)
    assert raw.get("ok") == "error" and raw.get("tool") == "write"
    assert _size(raw) <= MAX_DATA_BYTES


def test_bounded_data_budget_is_utf8_bytes_with_cjk():
    """预算按 UTF-8 字节算，不是字符数（中文 3 字节）。"""
    payload = {"content": {f"k{i:03d}": "中" * 2000 for i in range(64)},
               "ok": "error", "tool": "write"}
    raw = bounded_data(payload)
    assert raw["ok"] == "error" and raw["tool"] == "write"
    assert _size(raw) <= MAX_DATA_BYTES
    assert _size(raw) == len(json.dumps(raw, ensure_ascii=False,
                                        separators=(",", ":")).encode("utf-8"))


def test_oversized_failure_still_counted_by_model_access_tracker():
    """回归走真实消费链：parse -> normalize -> ModelAccessTracker.consume。

    只断言"键还在"是不够的：`_resets` 读 data['ok']，`is_model_access` 读
    failure.code/message —— 值被剪坏时键依然存在，但语义已经反了。
    """
    from pet.agent_event_normalizer import RetryEvent, normalize_event
    from pet.model_access_tracker import ModelAccessTracker

    tracker = ModelAccessTracker()
    retry = {
        "ts": 1.0, "agent": "dsh", "sessionId": "s1", "event": "llm/retry",
        "failure": {"code": "429", "message": "rate limit exceeded"},
        "content": _FILLER,
    }

    semantic = normalize_event(parse_agent_event(dict(retry)))
    assert isinstance(semantic, RetryEvent)
    assert semantic.code == "429", f"限流码被剪坏：{semantic.code!r}"

    streak = tracker.consume(semantic)
    assert streak is not None, "429 必须被识别为模型访问失败"
    assert streak["consecutiveRetryCount"] == 1

    # 中间来一个失败的 tool/result（ok=error）：不得复位连续计数
    failed = {"ts": 2.0, "agent": "dsh", "sessionId": "s1", "event": "tool/result",
              "ok": "error", "tool": "write", "content": _FILLER}
    tracker.consume(normalize_event(parse_agent_event(dict(failed))))

    again = tracker.consume(normalize_event(parse_agent_event(dict(retry))))
    assert again is not None and again["consecutiveRetryCount"] == 2, \
        f"ok='error' 被剪坏成成功语义，连续计数被复位：{again}"


# --------------------------------------------------------------------------
# 长语义值（message / 身份 ID）：超限修剪必须**完整**保留语义字段
#
# 旧实现把 64 当成所有字符串的下限（`value[:max(64, str_cap)]`），而 64 是按
# "最短枚举字面量"定的**内容侧**口径。它一旦作用到语义字段，剪掉的不是字节而是
# 控制流：errorMessage 尾部的限流/超时关键字、审批收尾用的身份 ID。
# 本组用例把"完整保留 + 装不下时明确拒收"钉在真实消费链上。
# --------------------------------------------------------------------------

#: 真实事故口径的超时消息（2026-09-11：llm/retry 连续 5 次 TIMEOUT 却零提醒）。
#: 关键字 ETIMEDOUT 落在第 64 个字符之后，旧实现剪到 64 字符后 tracker 认不出。
_LONG_MSG = ("HTTP request to the model endpoint failed after 2 attempts: "
             "fetch failed with ETIMEDOUT")


def test_long_error_message_survives_trimming_and_still_counts_as_model_access():
    from pet.agent_event_normalizer import RetryEvent, normalize_event
    from pet.model_access_tracker import ModelAccessTracker

    assert _LONG_MSG.index("ETIMEDOUT") > MIN_CONTENT_STRING_CHARS, \
        "前置：关键字必须落在旧下限之后，否则本用例不成立"
    record = {
        "ts": 1.0, "agent": "dsh", "sessionId": "s1", "event": "llm/retry",
        "failure": {"code": "", "message": _LONG_MSG}, "content": _FILLER,
    }
    assert _size(record) > MAX_DATA_BYTES, "前置：负载必须真的超限"

    event = parse_agent_event(dict(record))
    assert event.data["failure"]["message"] == _LONG_MSG, \
        f"errorMessage 被剪短：{event.data['failure']['message']!r}"

    semantic = normalize_event(event)
    assert isinstance(semantic, RetryEvent)
    assert semantic.message == _LONG_MSG

    streak = ModelAccessTracker().consume(semantic)
    assert streak is not None, "关键字被剪掉 → 模型访问失败漏计（连续计数不涨、提醒不发）"
    assert streak["consecutiveRetryCount"] == 1


def test_long_identity_ids_survive_trimming_so_interaction_still_pairs():
    """审批收尾靠身份字符串**相等**配对（agent_link._on_normalized_event:2633、
    _on_approval_resolved:3608），而待办登记端存的是**未修剪**的原始 payload
    （_register_interaction(rpc_id=payload.get("rpcId")):3383）。桥接写出的收尾帧是
    `interaction/resolved` + 顶层 rpcId/approvalId（integrations/dsh-pet-bridge
    index.js:1283），这两个键不在 from_record 的排除表里 → 进 data → 受修剪。
    身份被剪短 = 两侧永不相等 = 审批永久挂在待办里（或错配到别的审批）。
    """
    from pet.agent_event_normalizer import InteractionResolvedEvent, normalize_event

    rpc = "rpc-" + "9" * 96
    approval = "appr-" + "8" * 96
    record = {
        "ts": 2.0, "source": "dsh", "agentName": "dsh", "sessionId": "s1",
        "event": "interaction/resolved", "kind": "approval",
        "rpcId": rpc, "approvalId": approval, "outcome": "approved", "content": _FILLER,
    }
    assert _size(record) > MAX_DATA_BYTES, "前置：负载必须真的超限"

    event = parse_agent_event(dict(record))
    assert event.data.get("rpcId") == rpc, f"rpcId 被剪短：{event.data.get('rpcId')!r}"
    assert event.data.get("approvalId") == approval, \
        f"approvalId 被剪短：{event.data.get('approvalId')!r}"

    resolved = normalize_event(event)
    assert isinstance(resolved, InteractionResolvedEvent)
    pending_ids = (rpc, approval)  # 登记端存的是原始（未修剪）值
    assert resolved.rpc_id in pending_ids and resolved.approval_id in pending_ids, \
        "身份被剪短 → 配对失败（审批关不掉）"
    assert resolved.outcome == "approved", "语义标量同样要活下来"


def test_long_ids_survive_in_legacy_approval_resolved_frame_too():
    """旧的审批收尾帧（approval/resolved）同样只经 bounded_data：身份也不得被剪。"""
    rpc = "rpc-" + "7" * 96
    approval = "appr-" + "6" * 96
    record = {
        "ts": 3.0, "source": "dsh", "sessionId": "s2", "event": "approval/resolved",
        "rpcId": rpc, "approvalId": approval, "outcome": "approved", "content": _FILLER,
    }
    assert _size(record) > MAX_DATA_BYTES, "前置：负载必须真的超限"
    event = parse_agent_event(dict(record))
    assert event.data.get("rpcId") == rpc and event.data.get("approvalId") == approval, \
        f"身份被剪短：{event.data.get('rpcId')!r} / {event.data.get('approvalId')!r}"


def test_oversize_semantic_value_is_rejected_not_truncated():
    """语义字段本身装不下预算时：明确拒收（抛错），不得用截断值/占位符冒充。

    "剪短了但还在"是最坏结果：normalizer 对异值 ok 一律按成功处理
    （`data.get("ok", True) not in (False, 0, "false", "error")`），
    ModelAccessTracker._resets 同口径——失败事件会被剪成成功事件。
    调用方（agent_link._emit_unified_event:1563）已把解析包在 except 里：
    拒收只丢语义层，原始记录转发不受影响（同未知 schema 的处理口径）。
    """
    huge = "E" * (2 * MAX_DATA_BYTES)
    with pytest.raises(EventPayloadTooLarge):
        bounded_data({"ok": "error", "tool": "write", "errorMessage": huge})
    with pytest.raises(EventPayloadTooLarge):
        parse_agent_event({"ts": 1.0, "agent": "dsh", "sessionId": "s1",
                           "event": "tool/result", "ok": "error", "errorMessage": huge})


def test_fittable_long_semantic_value_is_kept_whole_while_content_is_squeezed():
    """装得下就必须完整保留（不受内容侧 str_cap 约束），超限一律从 content 里挤。"""
    msg = "middle-" + "M" * 3000 + "-tail ETIMEDOUT"
    assert len(msg) > MAX_STRING_CHARS, "前置：必须长于内容侧上限"
    raw = bounded_data({"failure": {"code": "X", "message": msg}, "content": _FILLER})
    assert raw["failure"]["message"] == msg, "语义 message 不得被压到内容侧上限"
    assert _size(raw) <= MAX_DATA_BYTES


def test_trimming_never_flips_an_outcome():
    """修剪前后的语义结局必须一致：基线是**未修剪**负载（直接构造 AgentEvent），
    对照是走真实 parse 的修剪结果。"""
    from pet.agent_event_normalizer import normalize_event

    raw_data = {"ok": "error", "tool": "write", "errorMessage": _LONG_MSG, "content": _FILLER}
    baseline = AgentEvent(SCHEMA, 1.0, "dsh", "dsh", "", "", "s1", "", None, None,
                          "tool/result", dict(raw_data))
    trimmed = parse_agent_event({"ts": 1.0, "agent": "dsh", "sessionId": "s1",
                                 "event": "tool/result", "data": raw_data})
    base_ev, trim_ev = normalize_event(baseline), normalize_event(trimmed)
    assert type(base_ev) is type(trim_ev)
    assert base_ev.ok is False and trim_ev.ok is False, f"失败被剪成成功：{trim_ev}"
    assert (base_ev.tool, base_ev.target) == (trim_ev.tool, trim_ev.target)


def test_content_only_payload_success_is_a_preexisting_default():
    """content-only（无 ok 字段）解析成"成功"是 normalizer 的**既有默认**
    （`data.get("ok", True)`），不是本批修剪引入；这里钉住"修剪不改变它"。

    这不妨碍反面口径成立：不允许修剪把**原本失败**的事件剪成成功
    （见 test_trimming_never_flips_an_outcome）。
    """
    from pet.agent_event_normalizer import EvidenceEvent, ToolResultEvent, normalize_event

    raw_data = {"tool": "read", "content": _FILLER}
    baseline = AgentEvent(SCHEMA, 1.0, "dsh", "dsh", "", "", "s1", "", None, None,
                          "tool/result", dict(raw_data))
    trimmed = parse_agent_event({"ts": 1.0, "agent": "dsh", "sessionId": "s1",
                                 "event": "tool/result", "data": raw_data})
    base_ev, trim_ev = normalize_event(baseline), normalize_event(trimmed)
    assert isinstance(base_ev, EvidenceEvent) and not isinstance(base_ev, ToolResultEvent)
    assert type(base_ev) is type(trim_ev), "既有默认不得被修剪改变"
    assert _size(trimmed.data) <= MAX_DATA_BYTES and "content" in trimmed.data


# --------------------------------------------------------------------------
# 条目配额只作用**内容项**：语义容器不得被 `[:keep]` 按插入次序切掉
#
# 反例（本批实测）：`_bounded` 的 `[:keep]` 对 semantic=True 的 Mapping/list
# 同样生效，且先按插入次序截取——语义键排在配额之后就整体消失：
# - 64 个噪声键 + ok/tool 的根负载 → 条目配额把 ok/tool 切掉，normalizer 的
#   `data.get("ok", True)` 取到默认成功 → 失败的工具结果变成成功证据；
# - failure 内第 129 个键才是 code:'429' → 限流漏计；
# - 30KB 的语义容器被偷偷截成 16 项（而不是按预算拒收）。
# 这三条都是"键还在但语义没了"的同类缺陷：配额是给内容定的，不是给控制流定的。
# --------------------------------------------------------------------------


def test_content_item_quota_never_drops_semantic_keys():
    """语义键排在噪声键之后：条目配额只能裁内容项，语义项一个不丢。"""
    payload = {f"k{i:03d}": [0] * 128 for i in range(64)}
    payload["ok"] = "error"
    payload["tool"] = "write"
    payload["content"] = {f"c{i:03d}": [0] * 128 for i in range(64)}
    assert _size(payload) > MAX_DATA_BYTES, "前置：该负载必须真的超限"

    raw = bounded_data(payload)

    assert raw.get("ok") == "error", f"ok 被条目配额切掉：{sorted(raw)[:6]}…"
    assert raw.get("tool") == "write", f"tool 被条目配额切掉：{sorted(raw)[:6]}…"
    assert _size(raw) <= MAX_DATA_BYTES

    from pet.agent_event_normalizer import ToolResultEvent, normalize_event

    event = parse_agent_event({"ts": 1.0, "agent": "dsh", "sessionId": "s1",
                               "event": "tool/result", "data": payload})
    semantic = normalize_event(event)
    assert isinstance(semantic, ToolResultEvent) and semantic.ok is False, \
        f"ok 被配额切掉后失败被读成成功证据：{semantic}"


def test_content_quota_shrink_keeps_semantic_keys_inside_content_container():
    """预算二次收缩（① 压内容长串 → ② 收紧条目数）之后，内容容器里的语义键仍要活。

    `_FILLER` 这类纯数字容器压不动字符串，所以一定走到第 ② 级收缩；第 ② 级把
    item_limit 减半时，语义键（它们是控制流）不在收缩范围内。
    """
    inner = {f"c{i:03d}": [0] * 128 for i in range(128)}
    inner["ok"] = "error"
    inner["tool"] = "write"
    payload = {"content": inner}
    assert _size(payload) > MAX_DATA_BYTES, "前置：该负载必须真的超限"

    raw = bounded_data(payload)
    content = raw["content"]

    assert content.get("ok") == "error", f"二次收缩把 ok 拉走了：{sorted(content)[:6]}…"
    assert content.get("tool") == "write"
    assert _size(raw) <= MAX_DATA_BYTES


def test_semantic_container_is_not_sliced_by_content_quota():
    """语义容器（failure）不受内容条目配额约束：尾部语义键必须完整保留。

    配额是给"内容还能留多少"定的；作用到 failure 上就变成"错误码能不能被看见"。
    """
    failure = {f"f{i:03d}": 1 for i in range(128)}
    failure["code"] = "429"
    failure["message"] = "rate limit exceeded"
    payload = {"failure": failure,
               "content": {f"c{i:03d}": [0] * 128 for i in range(128)}}
    assert _size(payload) > MAX_DATA_BYTES, "前置：该负载必须真的超限"

    raw = bounded_data(payload)

    assert raw["failure"]["code"] == "429", "failure.code 被内容配额切掉"
    assert raw["failure"]["message"] == "rate limit exceeded"
    assert _size(raw) <= MAX_DATA_BYTES

    from pet.agent_event_normalizer import RetryEvent, normalize_event
    from pet.model_access_tracker import ModelAccessTracker

    event = parse_agent_event({"ts": 1.0, "agent": "dsh", "sessionId": "s1",
                               "event": "llm/retry", "data": payload})
    semantic = normalize_event(event)
    assert isinstance(semantic, RetryEvent) and semantic.code == "429", \
        f"限流码丢了：{semantic}"
    streak = ModelAccessTracker().consume(semantic)
    assert streak is not None and streak["consecutiveRetryCount"] == 1, \
        "限流被漏计（连续计数不涨、提醒不发）"


def test_oversized_semantic_container_is_rejected_not_truncated():
    """语义容器本身装不下预算：明确拒收，不得偷偷截几个条目冒充"还在"。

    两种形态同一个出口：
    - 语义*列表*（30 × 1000 字符 = 30KB）→ 拒收（旧口径按条目配额悄悄截到 16 项）；
    - 语义*映射*被噪声键撑爆（128 个噪声键 + code/message = 17.5KB）→ 拒收。
      容器里没有"该丢哪一项"的正确答案：丢噪声没用（还是超），丢 code 就是把
      限流读成没事。真实 failure 容器只有 code/message 几个短键，走不到这里；
      删掉整个统一语义层（调用方已 catch）比悄悄改写控制流安全。
    """
    payload = {"failure": ["s" * 1000 for _ in range(30)]}
    assert _size(payload) > MAX_DATA_BYTES, "前置：该负载必须真的超限"

    with pytest.raises(EventPayloadTooLarge):
        bounded_data(payload)
    with pytest.raises(EventPayloadTooLarge):
        parse_agent_event({"ts": 1.0, "agent": "dsh", "sessionId": "s1",
                           "event": "llm/retry", "data": payload})

    noise = {f"f{i:03d}": [0] * 64 for i in range(128)}
    noise["code"] = "429"
    noise["message"] = "rate limit exceeded"
    mapping = {"failure": noise}
    assert _size(mapping) > MAX_DATA_BYTES, "前置：该负载必须真的超限"

    with pytest.raises(EventPayloadTooLarge):
        bounded_data(mapping)


# --------------------------------------------------------------------------
# 根级 message：两个消费端在 failure 非 dict 时读它当错误消息
#
# model_access_tracker.py:52-54 与 agent_event_normalizer.py:107-108 都是
# `failure = data if not isinstance(data.get("failure"), dict) else data["failure"]`，
# 然后读 `failure.get("message")`——failure 不是 dict 时读到的就是**根级 message**。
# 它不是展示内容（展示走 text/content），是限流/超时正则的输入。
# --------------------------------------------------------------------------


def test_root_level_message_is_error_semantics_not_display_content():
    """根级 message 必须与 errorMessage 同口径保护：剪短它等于把超时读成没事。"""
    record = {"ts": 1.0, "agent": "dsh", "sessionId": "s1", "event": "llm/retry",
              "message": _LONG_MSG, "content": _FILLER}
    assert _size(record) > MAX_DATA_BYTES, "前置：该负载必须真的超限"

    event = parse_agent_event(dict(record))
    assert event.data.get("message") == _LONG_MSG, \
        f"根级 message 被剪短：{event.data.get('message')!r}"

    from pet.agent_event_normalizer import RetryEvent, normalize_event
    from pet.model_access_tracker import ModelAccessTracker

    semantic = normalize_event(event)
    assert isinstance(semantic, RetryEvent) and semantic.message == _LONG_MSG

    streak = ModelAccessTracker().consume(semantic)
    assert streak is not None, "ETIMEDOUT 被剪掉 → 连接类失败漏计"
    assert streak["consecutiveRetryCount"] == 1


# --------------------------------------------------------------------------
# 键也是标识符：语义容器内的键不得按内容口径砍到 120 字符
#
# 反例（本批实测）：`_bounded` 对**所有** Mapping 键执行 `str(k)[:120]`，包括
# semantic=True 的容器内部——两个只在前 120 字符之后才不同的 failure 键静默
# 碰撞成同一个键，后写的覆盖先写的（4 项变 3 项，无日志、无异常）。
# 取舍：键是标识符不是内容。内容剪短了还能读，键剪短了就是"两条记录并成一条"；
# 语义侧的既有口径是"装不下就明确拒收"（EventPayloadTooLarge），键同样适用——
# 靠砍键把容器塞进预算，换来的是一份看起来还在、实际已被合并的语义。
# --------------------------------------------------------------------------

_SHARED_KEY_PREFIX = "f" * 130


def test_semantic_container_keys_are_identifiers_not_content():
    """语义容器内的长键必须完整保留：共享前 120 字符的键不得碰撞合并。"""
    payload = {"failure": {
        _SHARED_KEY_PREFIX + "-A": "first",
        _SHARED_KEY_PREFIX + "-B": "second",
        "code": "429",
        "message": "rate limit exceeded",
    }}
    assert all(len(k) > 120 for k in list(payload["failure"])[:2]), \
        "前置：两个键必须共享前 120 字符（否则本用例不成立）"

    keys = bounded_data(payload)["failure"]

    assert len(keys) == 4, f"语义容器键被截断后碰撞合并：实得 {len(keys)} 项"
    assert keys[_SHARED_KEY_PREFIX + "-A"] == "first"
    assert keys[_SHARED_KEY_PREFIX + "-B"] == "second"
    assert keys["code"] == "429" and keys["message"] == "rate limit exceeded"

    event = parse_agent_event({"ts": 1.0, "agent": "dsh", "sessionId": "s1",
                               "event": "llm/retry", "data": payload})
    assert len(event.data["failure"]) == 4, "真实解析入口同样不得合并语义容器内的键"
    assert event.data["failure"]["code"] == "429"


def test_oversized_semantic_key_is_rejected_not_collapsed():
    """语义容器的**键**本身装不下预算：明确拒收，不得靠砍键（=合并）糊过去。"""
    payload = {"failure": {("k" * 2000) + str(i): i for i in range(20)}}
    assert _size(payload) > MAX_DATA_BYTES, "前置：该负载必须真的超限"

    with pytest.raises(EventPayloadTooLarge):
        bounded_data(payload)
    with pytest.raises(EventPayloadTooLarge):
        parse_agent_event({"ts": 1.0, "agent": "dsh", "sessionId": "s1",
                           "event": "llm/retry", "data": payload})


def test_content_mapping_keys_keep_the_120_char_trim():
    """反向约束：**内容**侧容器的键维持既有的 120 字符截断（本次只放语义侧）。"""
    long_key = "c" * 300
    content = bounded_data({"content": {long_key: "value"}})["content"]
    assert list(content) == ["c" * 120], "内容键的截断行为不得被这次改动带走"
    assert content["c" * 120] == "value"
