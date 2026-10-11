# -*- coding: utf-8 -*-
"""DSH 统一状态收敛（dsh_state.DshStateConverger）单元测试。

减法后（2026-10）dsh_state 只剩纯逻辑：不建 Qt 对象、不读文件、不探端口——
直接驱动收敛器的 handle_record / set_online / tick，验证 edge-trigger 去重、
离线恢复与审批/问题锁存。读方（DshMonitor）与消费侧的接线回归见
tests/test_agent_link_subtraction.py 的单读方/审批收敛测试族。
"""
from __future__ import annotations

from pet.dsh_state import APPROVAL_LATCH_TIMEOUT_S, DshState, DshStateConverger, candidate_ports


def _records_for(*events):
    """把事件名序列转为 AgentStatus(working/idle) 或原始事件记录。"""
    out = []
    for ev in events:
        if ev in ("idle", "working", "thinking", "waiting_approval", "waiting_question",
                  "success", "error"):
            out.append({"event": "AgentStatus", "state": ev})
        else:
            out.append({"event": ev})
    return out


def _feed(conv, *records):
    out = []
    for rec in records:
        out.extend(conv.handle_record(rec))
    return out


def _states(outputs):
    return [to for kind, _f, to, *_src in outputs if kind == "state"]


def test_offline_when_dsh_down(caplog):
    conv = DshStateConverger()
    with caplog.at_level("INFO"):
        out = conv.set_online(False)
    assert conv.current_state is DshState.OFFLINE
    assert _states(out) == ["offline"]
    assert any("[DSH STATE] offline" in r.getMessage() for r in caplog.records)


def test_online_goes_idle(caplog):
    conv = DshStateConverger()
    with caplog.at_level("INFO"):
        out = conv.set_online(True)
    assert conv.current_state is DshState.IDLE
    # DSH 一开始就在线：首个状态直接是 idle（from 为空，不是 offline -> idle）
    assert _states(out) == ["idle"]
    assert any("[DSH STATE] idle" in r.getMessage() for r in caplog.records)


def test_offline_then_online_idle(caplog):
    """先 offline，DSH 上线后切 idle：日志体现 offline -> idle。"""
    conv = DshStateConverger()
    conv.set_online(False)
    assert conv.current_state is DshState.OFFLINE
    with caplog.at_level("INFO"):
        out = conv.set_online(True)
    assert conv.current_state is DshState.IDLE
    assert _states(out) == ["idle"]
    assert any("[DSH STATE] offline -> idle" in r.getMessage() for r in caplog.records)


def test_edge_trigger_dedup():
    """同状态重复事件不重复产出。"""
    conv = DshStateConverger()
    conv.set_online(True)  # -> idle
    out = _feed(conv, *(_records_for("user/message") * 2))  # thinking ×2
    assert conv.current_state is DshState.THINKING
    assert _states(out) == ["thinking"]  # 只有一次 thinking 转换


def test_full_pipeline():
    """完整生命周期：thinking -> working -> waiting_approval -> working -> success -> idle。

    审批锁存的权威触发是 cordis/request-run（requiresApproval 严格 True）；
    解锁用 cordis/request-run-resolved（approval/decided 同款兼容路径另测）。
    """
    conv = DshStateConverger()
    conv.set_online(True)  # idle
    out = _feed(conv, *(_records_for("user/message", "tool/call")))
    out += _feed(conv, {"event": "cordis/request-run", "requestId": "r-1",
                        "payload": {"requiresApproval": True}})
    out += _feed(conv, {"event": "cordis/request-run-resolved", "requestId": "r-1"})
    out += _feed(conv, *(_records_for("turn/end", "idle")))
    assert _states(out) == [
        "thinking", "working", "waiting_approval", "working", "success", "idle",
    ]
    assert conv.current_state is DshState.IDLE


def test_approval_asked_does_not_latch():
    """H1 钉住：裸 approval/asked（普通工具调用也会被宿主打标的审计信号）
    绝不收敛为 waiting_approval——它是误报源，不是权威审批事件。"""
    conv = DshStateConverger()
    conv.set_online(True)  # idle
    out = _feed(conv, {"event": "approval/asked", "tool": "pwsh"})
    assert _states(out) == []
    assert conv.current_state is DshState.IDLE
    assert conv._pending_approval is False


def test_cordis_request_run_requires_strict_true():
    """cordis/request-run 只在 requiresApproval 严格布尔 True 时锁存审批态。"""
    conv = DshStateConverger()
    conv.set_online(True)
    # 平铺 False / 缺失 / 字符串 "true" 都不锁存
    _feed(conv, {"event": "cordis/request-run", "requestId": "r-a",
                 "payload": {"requiresApproval": False}})
    _feed(conv, {"event": "cordis/request-run", "requestId": "r-b"})
    _feed(conv, {"event": "cordis/request-run", "requestId": "r-c",
                 "payload": {"requiresApproval": "true"}})
    assert conv.current_state is DshState.IDLE
    # 嵌套 True 才锁存
    out = _feed(conv, {"event": "cordis/request-run", "requestId": "r-d",
                       "payload": {"requiresApproval": True}})
    assert _states(out) == ["waiting_approval"]
    assert conv.current_state is DshState.WAITING_APPROVAL


def test_approval_decided_releases_latch_for_compat():
    """approval/decided 保留为解锁兼容路径（旧桥/自定义通道的 approval 对）。"""
    conv = DshStateConverger()
    conv.set_online(True)
    _feed(conv, {"event": "approval/request", "approvalId": "ap-1"})  # 旧式审批事件
    assert conv.current_state is DshState.WAITING_APPROVAL
    out = _feed(conv, {"event": "approval/decided", "approvalId": "ap-1"})
    assert _states(out) == ["working"]
    assert conv.current_state is DshState.WORKING


def test_approval_latch_ignores_working():
    """审批锁存期间 working 事件被忽略，直到 cordis/request-run-resolved。"""
    conv = DshStateConverger()
    conv.set_online(True)
    # waiting_approval 后，即便又来 working（agent 仍在跑），也不被顶掉
    _feed(conv, {"event": "cordis/request-run", "requestId": "r-1",
                 "payload": {"requiresApproval": True}})
    _feed(conv, *(_records_for("tool/call", "working")))
    assert conv.current_state is DshState.WAITING_APPROVAL

    _feed(conv, {"event": "cordis/request-run-resolved", "requestId": "r-1"})
    assert conv.current_state is DshState.WORKING


def test_offline_force_overrides_work():
    """DSH 被强制关闭时切 offline，不崩。"""
    conv = DshStateConverger()
    conv.set_online(True)
    _feed(conv, *(_records_for("working")))
    assert conv.current_state is DshState.WORKING

    conv.set_online(False)
    assert conv.current_state is DshState.OFFLINE


def test_question_latch_ignores_working():
    """问题锁存期间 working 事件被忽略，直到 question/resolved。"""
    conv = DshStateConverger()
    conv.set_online(True)
    _feed(conv, {"event": "question/requested", "questions": [
        {"id": "q1", "question": "要执行哪个方案？",
         "options": [{"label": "方案 A"}, {"label": "方案 B"}]}]})
    _feed(conv, *(_records_for("tool/call", "working")))
    assert conv.current_state is DshState.WAITING_QUESTION

    _feed(conv, {"event": "question/resolved"})
    assert conv.current_state is DshState.WORKING


def test_question_pipeline():
    """完整生命周期：thinking -> working -> waiting_question -> working -> success -> idle。"""
    conv = DshStateConverger()
    conv.set_online(True)  # idle
    out = []
    out.extend(_feed(conv, *(_records_for("user/message", "tool/call"))))
    out.extend(_feed(conv, {"event": "question/requested", "questions": [
        {"id": "q1", "question": "选 A 还是 B？", "options": [{"label": "A"}, {"label": "B"}]}]}))
    out.extend(_feed(conv, {"event": "question/resolved"}))
    out.extend(_feed(conv, *(_records_for("turn/end", "idle"))))
    assert _states(out) == [
        "thinking", "working", "waiting_question", "working", "success", "idle",
    ]
    assert conv.current_state is DshState.IDLE


def test_offline_releases_question_latch():
    """DSH 离线时问题锁存一并清除，且离线后不再被残留 resolved 顶成 working。"""
    conv = DshStateConverger()
    conv.set_online(True)
    _feed(conv, {"event": "question/requested", "questions": [{"id": "q", "question": "?"}]})
    assert conv.current_state is DshState.WAITING_QUESTION

    out = conv.set_online(False)
    assert conv.current_state is DshState.OFFLINE
    assert _states(out) == ["offline"]

    # 残留 resolved 不再把 offline 顶成 working（map 得 working，但读方在离线时
    # 不喂记录；即便防御性喂入，resolved 也只是解除一个已清的锁存）
    out = _feed(conv, {"event": "question/resolved"})
    assert conv.current_state is DshState.OFFLINE


def test_recovery_after_restart():
    """DSH 重启后自动回 idle 并继续消费事件。"""
    conv = DshStateConverger()
    conv.set_online(True)
    conv.set_online(False)
    assert conv.current_state is DshState.OFFLINE

    conv.set_online(True)
    assert conv.current_state is DshState.IDLE

    _feed(conv, *(_records_for("turn/start")))
    assert conv.current_state is DshState.THINKING


def test_user_message_plugin_source_ignored():
    """agent.inject() 注入上下文（sourceKind=plugin）不触发对话开始、不进状态机。

    每轮 DSH 会注入 4-5 条 system-reminder/技能目录等 user/message,必须与真人
    消息区分,否则「对话开始」被注入文案污染。
    """
    conv = DshStateConverger()
    conv.set_online(True)  # idle
    out = _feed(conv, {"event": "user/message", "sourceKind": "plugin",
                       "text": "<system-reminder> 技能目录……", "sessionId": "s1"})
    assert [o for o in out if o[0] == "user_message"] == []
    assert conv.current_state is DshState.IDLE


def test_user_message_real_emits_output():
    """真人消息（sourceKind=user）产出 user_message(session, text) 并收敛 thinking。"""
    conv = DshStateConverger()
    conv.set_online(True)  # idle
    out = _feed(conv, {"event": "user/message", "sourceKind": "user",
                       "text": "看看还有没有这个事件", "sessionId": "s1"})
    assert [o for o in out if o[0] == "user_message"] == [("user_message", "s1", "看看还有没有这个事件")]
    assert conv.current_state is DshState.THINKING


def test_user_message_legacy_record_keeps_output():
    """旧版桥接记录无 sourceKind：按真人消息兼容处理，绝不静默丢事件。"""
    conv = DshStateConverger()
    conv.set_online(True)  # idle
    out = _feed(conv, {"event": "user/message", "text": "hi", "sessionId": "s2"})
    assert [o for o in out if o[0] == "user_message"] == [("user_message", "s2", "hi")]
    assert conv.current_state is DshState.THINKING


def test_unknown_event_ignored():
    conv = DshStateConverger()
    conv.set_online(True)
    _feed(conv, {"event": "some/unknown", "foo": 1})
    assert conv.current_state is DshState.IDLE


def test_llm_error_record_enters_error_state():
    """桥接真实写的是 llm_error（index.js），状态机必须认它——否则 ERROR 态不可达。

    桥接在 bad_response_status_code（API 级错误）分支写 ``event: "llm_error"``；
    旧键名 "llm/error" 与它只差一个分隔符，导致 API 错误永远进不了 ERROR。
    """
    conv = DshStateConverger()
    conv.set_online(True)  # idle
    out = _feed(conv, {"event": "tool/call"},  # working
                {
                    "event": "llm_error", "errorCode": "bad_response_status_code",
                    "errorMessage": "404", "errorKind": "api",
                })
    assert conv.current_state is DshState.ERROR
    assert _states(out) == ["working", "error"]


def test_dead_event_keys_removed_from_state_map():
    """状态表不得保留桥接从不写的事件键。

    index.js 明确不转发流式 assistant/chunk，plan/mode 也只在 DSH 内部词汇里
    出现——留着这两条只会让状态表看起来覆盖了并不存在的事件。
    """
    from pet.dsh_state import _EVENT_TO_STATE

    assert "llm_error" in _EVENT_TO_STATE
    assert "llm/error" not in _EVENT_TO_STATE, "桥接实际写 llm_error，旧键名匹配不到"
    assert "assistant/chunk" not in _EVENT_TO_STATE
    assert "plan/mode" not in _EVENT_TO_STATE


def test_approval_latch_timeout_releases_to_working():
    """审批锁存超时兜底：DSH 漏发 approval/decided 时 tick() 强制回 working。"""
    clock = [1000.0]
    conv = DshStateConverger(clock=lambda: clock[0])
    conv.set_online(True)
    _feed(conv, {"event": "tool/call"})
    _feed(conv, {"event": "cordis/request-run", "requestId": "r-1",
                 "payload": {"requiresApproval": True}})
    assert conv.current_state is DshState.WAITING_APPROVAL

    clock[0] += APPROVAL_LATCH_TIMEOUT_S - 1
    assert conv.tick() == [], "未到超时点不得解除锁存"
    assert conv.current_state is DshState.WAITING_APPROVAL

    clock[0] += 2.0
    out = conv.tick()
    assert _states(out) == ["working"]
    assert conv.current_state is DshState.WORKING


def test_candidate_ports_include_desktop_host():
    """端口候选必须含 desktop 桌面端硬编码端口 19387（web 3080 / 避让 38080 之外）。"""
    ports = candidate_ports()
    assert 3080 in ports
    assert 38080 in ports
    assert 19387 in ports, "desktop 桌面端 host 在 127.0.0.1:19387，漏探会把桌面端误判 offline"
