# -*- coding: utf-8 -*-
"""截图问答浮窗（``ask_dialog.ScreenAskDialog``）与多轮会话（``VisionConversation``）。

浮窗是本片 2026-10-14 重做后的问答面，它**同时是隐私确认面**：框选完只把图摆在
输入栏上方，发不发、发什么，都由用户点「发送」那一刻决定。所以这里钉死五件事：

1. **打开窗口一个字节都不出网**（唯一的网络出口是「发送」，且真会话也这么走）；
2. **一轮一条**：发送中的第二次点按被拒收（不会叠出两条请求）；
3. **结果回 GUI 线程**：阻塞的网络调用跑在后台线程，答复/失败经信号回落到气泡与状态行；
4. **开新会话**：换图即清空旧消息与旧上下文（旧历史配新图是语义错乱）；
5. **Esc 可关**，输入框聚焦时留给输入框自己（与结果面板同一条"不抢主人按键"的口径）。

``VisionConversation`` 的组包契约在同一份文件里（首轮带图、后续轮纯文本、历史自持）。

纪律：offscreen，能直调的直调；涉及真线程的用例走事件同步 + 宽预算（不用固定
sleep 猜时序）。
"""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QKeyEvent, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from pet.chat.models import ProviderConfig  # noqa: E402
from pet.screen_capture.ask_dialog import ScreenAskDialog, _Bubble  # noqa: E402
from pet.screen_capture.session import SelectionRect  # noqa: E402
from pet.screen_capture.vision_bridge import VisionConversation  # noqa: E402

#: 等待预算（秒）：后台线程 + CI 慢 runner 给足，靠事件同步醒，不靠 sleep 猜。
_BUDGET = 10.0


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _image(width: int = 40, height: int = 30) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(200, 40, 40))
    return image


def _escape() -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)


def _settle() -> None:
    """把挂起的事件（含 ``deleteLater`` 的墓碑）推完，再看控件树。"""
    app = QApplication.instance()
    assert app is not None
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _until(predicate, what: str) -> None:
    deadline = time.monotonic() + _BUDGET
    while not predicate() and time.monotonic() < deadline:
        _settle()
        time.sleep(0.005)
    assert predicate(), f"预算内没等到：{what}"


def _bubbles(dialog) -> list[tuple[str, str]]:
    """消息列表里的气泡（role, 文本）——按渲染出来的控件读，不数布局项。"""
    return [(bubble.objectName(), bubble.text())
            for bubble in dialog._messages_host.findChildren(_Bubble)]


def _texts(dialog) -> list[str]:
    return [text for _role, text in _bubbles(dialog)]


class _VisionConfig:
    """``resolve_chat_context`` 要的两个口（真 ``VisionConversation`` 用）。

    浮窗自己只把 config 存着、不读；真会话在 ``__init__`` 里把它解析成
    ``(provider, system_prompt)``，所以这两个方法必须给得出东西。
    """

    def chat_settings(self):
        return SimpleNamespace(
            active_config=ProviderConfig.from_dict(
                "t", {"model": "deepseek-v4-flash", "api_key": "sk-x"}),
            default_system_prompt="sys",
        )

    def resolve_api_key(self, _provider) -> str:
        return "sk-x"


class _FakeConversation:
    """会话替身：记录 ``start`` 收到的图/上下文与 ``ask`` 收到的每一轮问题。"""

    def __init__(self, config, *, reply: str = "我看这是一段代码。") -> None:
        self.config = config
        self.reply = reply
        self.started: list = []
        self.contexts: list[str] = []
        self.questions: list[str] = []

    def start(self, image, context_text: str = "") -> None:
        self.started.append(image)
        self.contexts.append(str(context_text))

    def ask(self, text: str) -> str:
        self.questions.append(str(text))
        return self.reply


class _Factory:
    """``conversation_factory`` 替身：每个会话都记在案（浮窗每次开新会话造一个）。"""

    def __init__(self, cls=_FakeConversation, **kwargs) -> None:
        self.cls = cls
        self.kwargs = kwargs
        self.made: list = []

    def __call__(self, config):
        conversation = self.cls(config, **self.kwargs)
        self.made.append(conversation)
        return conversation

    @property
    def latest(self):
        assert self.made, "浮窗没有建会话"
        return self.made[-1]


def _dialog(**kwargs) -> ScreenAskDialog:
    kwargs.setdefault("conversation_factory", _Factory())
    return ScreenAskDialog(_VisionConfig(), style="light", **kwargs)


def _render(widget, background: QColor | None = None) -> QImage:
    from PySide6.QtCore import QPoint

    canvas = QImage(widget.size(), QImage.Format.Format_ARGB32)
    canvas.fill(background if background is not None else QColor(0, 0, 0, 0))
    painter = QPainter(canvas)
    widget.render(painter, QPoint(0, 0))
    painter.end()
    return canvas


# ------------------------------------------------------------------ 开新会话


def test_start_with_image_opens_a_session_with_the_thumbnail_and_input_focus(qapp):
    factory = _Factory()
    dialog = _dialog(conversation_factory=factory)
    image = _image()

    dialog.start_with_image(image)

    assert factory.latest.started == [image], "会话拿到的必须是刚框到的那张图"
    # 缩略图是输入栏上方那一小条 chip 里的 40×40 方块（round 2：大图横幅把对话区挤没了）
    assert dialog._thumb_chip.objectName() == "screen-ask-chip"
    assert (dialog._thumb.width(), dialog._thumb.height()) == (40, 40)
    thumb = dialog._thumb.pixmap()
    assert thumb.isNull() is False
    assert thumb.width() <= 40 and thumb.height() <= 40, "缩略图溢出了 chip"
    assert dialog.isVisible() is True
    _settle()   # 焦点要事件循环推一把才生效（Qt 的 setFocus 是排队的）
    assert dialog._input.hasFocus() is True, "开窗就聚焦输入框：用户下一秒要打字"
    dialog.close()


def test_opening_the_dialog_puts_nothing_on_the_wire(qapp, monkeypatch):
    """隐私红线：打开浮窗只准备图，唯一的网络出口是用户点「发送」。

    （这条接替了旧契约里的"发送前必须显式确认"：确认面从系统 Yes/No 对话框
    换成了浮窗本身——图就摆在输入栏上方，发不发由用户自己点。所以"确认"不再是
    一句断言，而是"没点发送就一个字节都不出去"这条可测的事实。）
    """
    from pet import vision as vision_mod

    sent: list = []
    monkeypatch.setattr(vision_mod, "post_vision_messages",
                        lambda *args, **kwargs: sent.append(args) or "不该发生")
    dialog = ScreenAskDialog(_VisionConfig())   # 真会话（不是替身）

    dialog.start_with_image(_image())

    assert sent == [], "打开浮窗就把图发出去了"
    assert dialog._conversation is not None
    assert dialog._conversation.ready is True
    dialog.close()


def test_the_dialog_lands_below_the_selection(qapp):
    """定位契约（round 2 实机反馈）：窗口落在框选的那块**下方**，不再甩到屏幕角落。"""
    dialog = _dialog()
    rect = SelectionRect(200, 200, 300, 100)

    dialog.start_with_image(_image(), below=rect)

    geo = dialog.geometry()
    assert geo.top() >= rect.y + rect.height, "窗口压在选区上了"
    assert abs(geo.center().x() - (rect.x + rect.width // 2)) <= 2, "没有对齐选区中线"
    dialog.close()


def test_the_dialog_follows_a_new_selection_on_the_next_open(qapp):
    """下一次开窗（上一次已关）跟的是**这次**的选区，不是上一张图的那块。

    选区贴屏幕下缘时窗口按既定规则翻到选区上方（离屏屏高 800，窗口高 360，
    下缘 600 之后放不下），所以这里按"贴着这块选区"断言，而不是硬要求落在下方。
    """
    dialog = _dialog()
    dialog.start_with_image(_image(), below=SelectionRect(200, 200, 300, 100))
    dialog.close()

    rect = SelectionRect(100, 500, 200, 100)
    dialog.start_with_image(_image(), below=rect)

    geo = dialog.geometry()
    assert abs(geo.center().x() - (rect.x + rect.width // 2)) <= 2, "没有对齐新选区的中线"
    assert geo.top() >= rect.y + rect.height or geo.bottom() <= rect.y, "没有贴着新选区"
    dialog.close()


def test_a_position_the_user_dragged_wins_over_the_selection(qapp):
    """用户拖过的位置是他要的：再开一次也不许被"选区下方"抢走。"""
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    dialog = _dialog()
    dialog.start_with_image(_image())
    _settle()

    def _mouse(kind, local, glob, button, buttons):
        return QMouseEvent(kind, QPointF(*local), QPointF(*glob), button, buttons,
                           Qt.KeyboardModifier.NoModifier)

    origin = dialog.pos()
    dialog.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, (10, 8),
                                  (origin.x() + 10, origin.y() + 8),
                                  Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
    dialog.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, (10, 8), (210, 108),
                                Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
    dialog.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, (10, 8), (210, 108),
                                   Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))
    dragged_to = dialog.pos()
    assert dragged_to != origin

    dialog.start_with_image(_image(), below=SelectionRect(100, 500, 200, 100))

    assert dialog.pos() == dragged_to
    dialog.close()


def test_start_with_image_passes_the_context_text_to_the_session(qapp):
    """「继续提问」带来的已识别文字要原样进会话（参考资料，只进首轮）。"""
    factory = _Factory()
    dialog = _dialog(conversation_factory=factory)

    dialog.start_with_image(_image(), context_text="识别到的原文")

    assert factory.latest.contexts == ["识别到的原文"]
    dialog.close()


def test_start_with_image_defaults_to_no_context(qapp):
    """不带来文字时上下文为空串（缺省不是漏传，也不会编一段出来）。"""
    factory = _Factory()
    dialog = _dialog(conversation_factory=factory)

    dialog.start_with_image(_image())

    assert factory.latest.contexts == [""]
    dialog.close()


def test_start_with_image_clears_the_previous_conversation(qapp):
    """开新会话 = 换图 + 清消息 + 重置发送态（旧历史配新图是语义错乱）。"""
    factory = _Factory()
    dialog = _dialog(conversation_factory=factory)
    dialog.start_with_image(_image())

    dialog._input.setText("第一轮的问题")
    assert dialog.send_current() is True
    _until(lambda: len(_texts(dialog)) == 2, "第一轮的答复")

    dialog.start_with_image(_image(60, 40))
    _settle()

    assert _bubbles(dialog) == [], "旧消息还挂在列表上"
    assert dialog._status.text() == "" and dialog._status.isVisible() is False
    assert dialog._sending is False
    assert dialog._input.text() == ""
    dialog.close()


def test_start_with_image_rejects_a_null_image_and_leaves_the_window_closed(qapp):
    dialog = _dialog()

    with pytest.raises(ValueError):
        dialog.start_with_image(QImage())

    assert dialog.isVisible() is False, "开不了会话就不许把空窗留在屏幕上"
    dialog.close()


def test_a_broken_channel_leaves_the_window_closed_and_raises(qapp):
    """通道建不起来（没配置/配置坏了）：如实抛出，窗口不显示。

    编排层把这条异常翻成结果浮层上的人话（见
    ``test_screen_capture_actions.py::test_ask_action_reports_it_when_the_dialog_itself_breaks``）。
    """
    class _Broken:
        def __init__(self, _config):
            raise RuntimeError("渠道没配置")

    dialog = ScreenAskDialog(_VisionConfig(), conversation_factory=_Broken)

    with pytest.raises(RuntimeError):
        dialog.start_with_image(_image())

    assert dialog.isVisible() is False
    dialog.close()


# ------------------------------------------------------------------ 发送


def test_send_current_uses_a_default_question_for_empty_input(qapp):
    factory = _Factory()
    dialog = _dialog(conversation_factory=factory)
    dialog.start_with_image(_image())

    assert dialog.send_current() is True

    question = factory.latest.questions[0]
    assert question.strip() != "", "空输入不许发一个空串出去"
    assert _texts(dialog) == [question], "发出去什么，列表上就要看得见什么"
    assert dialog._input.text() == "", "发送后输入框要清干净"
    _until(lambda: dialog._sending is False, "答复")
    dialog.close()


def test_send_current_uses_what_the_user_typed(qapp):
    factory = _Factory()
    dialog = _dialog(conversation_factory=factory)
    dialog.start_with_image(_image())
    dialog._input.setText("  这页说的是哪天截止？  ")

    assert dialog.send_current() is True

    assert factory.latest.questions == ["这页说的是哪天截止？"], "首尾空白要抹掉再发"
    assert _texts(dialog)[0] == "这页说的是哪天截止？"
    _until(lambda: dialog._sending is False, "答复")
    dialog.close()


def test_send_current_refuses_a_second_send_while_in_flight(qapp):
    """一轮一条：发送中的第二次点按不许叠出第二条请求，界面同时禁掉入口。"""
    released = threading.Event()

    class _Blocking(_FakeConversation):
        def ask(self, text: str) -> str:
            self.questions.append(str(text))
            released.wait(_BUDGET)
            return "答"

    factory = _Factory(cls=_Blocking)
    dialog = _dialog(conversation_factory=factory)
    dialog.start_with_image(_image())

    assert dialog.send_current() is True
    assert dialog.send_current() is False, "发送中的第二次点按被受理了"
    assert dialog._send_btn.isEnabled() is False
    assert dialog._input.isEnabled() is False

    released.set()
    _until(lambda: dialog._sending is False, "答复")
    assert len(factory.latest.questions) == 1, "拒收之后仍然发了第二条请求"
    assert len(_texts(dialog)) == 2   # 一条提问 + 一条答复
    dialog.close()


def test_send_current_refuses_without_a_session(qapp):
    """还没开过会话就点发送：拒收，且不消费用户已经打好的字。"""
    dialog = _dialog()
    dialog._input.setText("问点什么")

    assert dialog.send_current() is False

    assert dialog._input.text() == "问点什么"
    assert _bubbles(dialog) == []
    dialog.close()


def test_send_current_records_the_question_as_a_user_bubble(qapp):
    factory = _Factory()
    dialog = _dialog(conversation_factory=factory)
    dialog.start_with_image(_image())
    dialog._input.setText("这是什么？")

    dialog.send_current()

    assert _bubbles(dialog) == [("screen-ask-user", "这是什么？")]
    _until(lambda: dialog._sending is False, "答复")
    dialog.close()


# ------------------------------------------------------- 答复 / 失败（信号回来）


def test_the_reply_lands_as_an_assistant_bubble_and_releases_the_input(qapp):
    factory = _Factory(reply="这是一段 Python 代码。")
    dialog = _dialog(conversation_factory=factory)
    dialog.start_with_image(_image())
    dialog._input.setText("这是什么？")

    dialog.send_current()
    _until(lambda: len(_texts(dialog)) == 2, "答复回到气泡里")

    assert _texts(dialog) == ["这是什么？", "这是一段 Python 代码。"]
    assert [role for role, _text in _bubbles(dialog)] == [
        "screen-ask-user", "screen-ask-assistant"]
    assert dialog._sending is False
    assert dialog._send_btn.isEnabled() is True
    assert dialog._status.isVisible() is False
    dialog.close()


def test_a_failed_send_keeps_the_reason_on_the_status_line(qapp):
    """失败要有理由，而且要能接着再发（不许把窗口锁死在"正在看图"）。"""
    class _Broken(_FakeConversation):
        def ask(self, text: str) -> str:
            raise RuntimeError("连接超时")

    factory = _Factory(cls=_Broken)
    dialog = _dialog(conversation_factory=factory)
    dialog.start_with_image(_image())
    dialog._input.setText("问")

    dialog.send_current()
    _until(lambda: "发送失败" in dialog._status.text(), "失败理由回到状态行")

    assert "连接超时" in dialog._status.text()
    assert dialog._status.isVisible() is True
    assert dialog._sending is False
    assert dialog._send_btn.isEnabled() is True
    assert _bubbles(dialog) == [("screen-ask-user", "问")], "失败不该多出一条空气泡"
    dialog.close()


def test_the_reply_and_failure_handlers_map_to_the_ui(qapp):
    """信号槽那两个入口的界面映射（后台线程与它的时序都不掺进来）。"""
    dialog = _dialog()
    dialog.start_with_image(_image())

    dialog._on_error(dialog._gen, "网络超时")
    assert dialog._status.text() == "发送失败：网络超时"
    assert dialog._status.isVisible() is True
    assert dialog._sending is False

    dialog._on_reply(dialog._gen, "回答")
    assert dialog._status.isVisible() is False, "答复到了，状态行要让位"
    assert _texts(dialog) == ["回答"]
    dialog.close()


def test_an_empty_reply_does_not_render_an_empty_bubble(qapp):
    """模型没说话（空答复）也要有可见的一句，不许塞一个空气泡让界面看起来卡住。

    真空串与纯空白都算"没说话"（round 1 的实现在纯空白上会落一个看不见的气泡，
    round 2 已改成先 strip 再兜底——这条现在把两种输入都钉住）。
    """
    for blank in ("", "   ", "\n\t"):
        dialog = _dialog()
        dialog.start_with_image(_image())

        dialog._on_reply(dialog._gen, blank)

        texts = _texts(dialog)
        assert texts and texts[0].strip() != "", f"{blank!r} 落了空气泡"
        dialog.close()


def test_the_network_call_runs_off_the_gui_thread(qapp):
    main_thread = threading.current_thread().name
    worker_names: list[str] = []

    class _Recorder(_FakeConversation):
        def ask(self, text: str) -> str:
            worker_names.append(threading.current_thread().name)
            return "答"

    dialog = _dialog(conversation_factory=_Factory(cls=_Recorder))
    dialog.start_with_image(_image())

    dialog.send_current()
    _until(lambda: len(_texts(dialog)) == 2, "答复")

    assert worker_names and worker_names[0] != main_thread, "网络调用压在 GUI 线程上了"
    dialog.close()


# ------------------------------------------------------------------ 键盘


def test_escape_closes_the_dialog_unless_the_input_has_focus(qapp):
    dialog = _dialog()
    dialog.start_with_image(_image())

    dialog._input.setFocus()
    _settle()
    assert dialog._input.hasFocus() is True
    dialog.keyPressEvent(_escape())
    assert dialog.isVisible() is True, "输入框聚焦时 Esc 属于输入框自己"

    dialog._input.clearFocus()
    dialog.keyPressEvent(_escape())
    assert dialog.isVisible() is False
    dialog.close()


# ------------------------------------------------------------------ 外观


def test_the_dialog_card_renders_the_theme_surface(qapp):
    """透明窗 + 手画圆角卡片（同结果面板）：中间是主题底色，角上留得住底下画布。"""
    dialog = ScreenAskDialog(_VisionConfig(), style="light",
                             conversation_factory=_Factory())
    dialog.start_with_image(_image())

    canvas = _render(dialog, background=QColor(255, 0, 255))

    # 采样点取左侧排版留白（中轴会被缩略图/消息区盖住，量不到卡片本身）
    card = canvas.pixelColor(4, dialog.height() // 2).getRgb()
    assert card == (255, 255, 255, 255), f"卡片底色不是主题浅色，而是 {card}"
    assert canvas.pixelColor(0, 0).getRgb() == (255, 0, 255, 255), "角上被涂实了，圆角没成形"
    dialog.close()


# ------------------------------------------------- VisionConversation（组包契约）


def _sent_messages(monkeypatch, reply: str = "答") -> list:
    """把 `post_vision_messages` 换成记录器，返回"每一次发出去的 messages"。"""
    from pet import vision as vision_mod

    sent: list = []
    monkeypatch.setattr(vision_mod, "post_vision_messages",
                        lambda messages, _p: sent.append(messages) or reply)
    return sent


def test_first_turn_carries_the_image_and_later_turns_do_not(monkeypatch):
    sent = _sent_messages(monkeypatch)
    conversation = VisionConversation(_VisionConfig())
    conversation.start(_image(64, 48))

    conversation.ask("这是什么？")
    conversation.ask("再详细点")
    conversation.ask("第三轮")

    first, third = sent[0], sent[-1]
    assert first[0]["role"] == "system" and first[0]["content"] == "sys"
    user_first = first[1]
    assert user_first["role"] == "user"
    assert [part["type"] for part in user_first["content"]] == ["text", "image_url"]
    assert user_first["content"][0]["text"] == "这是什么？"
    assert user_first["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    # 图只出现在第一轮：整包 messages 里带图（list 形式 content）的只有那一条
    assert sum(1 for message in third if isinstance(message["content"], list)) == 1
    assert isinstance(third[-1]["content"], str) and third[-1]["content"] == "第三轮"


def test_the_conversation_holds_its_own_history(monkeypatch):
    sent = _sent_messages(monkeypatch, reply="答复")
    conversation = VisionConversation(_VisionConfig())
    conversation.start(_image())

    conversation.ask("第一问")
    conversation.ask("第二问")

    assert [message["role"] for message in sent[-1]] == [
        "system", "user", "assistant", "user"]
    assert sent[-1][2]["content"] == "答复", "模型自己说过的话也进历史"
    conversation.ask("第三问")
    assert [message["role"] for message in sent[-1]] == [
        "system", "user", "assistant", "user", "assistant", "user"]


def test_start_replaces_the_image_and_clears_the_history(monkeypatch):
    """换图清史：旧历史配新图是语义错乱（模型会拿旧图回答新图的问题）。"""
    sent = _sent_messages(monkeypatch)
    conversation = VisionConversation(_VisionConfig())
    conversation.start(_image())
    conversation.ask("第一问")

    conversation.start(_image(80, 60))
    conversation.ask("第二问")

    latest = sent[-1]
    assert len(latest) == 2, "换图之后历史必须清空（只剩 system + 这一轮）"
    assert latest[1]["content"][0]["text"] == "第二问"
    assert [part["type"] for part in latest[1]["content"]] == ["text", "image_url"]


def test_the_context_text_rides_along_with_the_first_turn_only(monkeypatch):
    """识别文字是参考资料：跟着首轮发一次，之后的轮次靠历史（不重复背一段）。"""
    sent = _sent_messages(monkeypatch, reply="答复")
    conversation = VisionConversation(_VisionConfig())
    conversation.start(_image(), context_text="识别到的原文")

    conversation.ask("这是什么？")
    conversation.ask("再详细点")

    first_turn_text = sent[0][1]["content"][0]["text"]
    assert "这是什么？" in first_turn_text
    assert "识别到的原文" in first_turn_text
    assert sent[-1][-1]["content"] == "再详细点"
    assert "识别到的原文" not in sent[-1][-1]["content"]


def test_a_new_session_does_not_carry_the_previous_context(monkeypatch):
    """换会话（不带文字）＝这一轮没有资料：上一张图的那段识别文字不许跟过来。"""
    sent = _sent_messages(monkeypatch)
    conversation = VisionConversation(_VisionConfig())
    conversation.start(_image(), context_text="上一张图的文字")
    conversation.ask("第一问")
    assert "上一张图的文字" in sent[-1][1]["content"][0]["text"]

    conversation.start(_image(80, 60))
    conversation.ask("第二问")

    assert "上一张图的文字" not in sent[-1][1]["content"][0]["text"]


def test_ask_without_start_is_refused(monkeypatch):
    _sent_messages(monkeypatch)
    conversation = VisionConversation(_VisionConfig())

    assert conversation.ready is False
    with pytest.raises(RuntimeError):
        conversation.ask("问")


# ------------------------------------------------------------------ 盲审 M2：会话代号门


def test_a_late_reply_from_a_previous_session_never_lands_in_the_new_one(qapp):
    """换图开新会话后，旧会话迟到的回复必须丢弃（不落气泡、不解新会话的发送锁）。"""
    dialog = _dialog()
    dialog.start_with_image(_image())
    first_gen = dialog._gen
    dialog._on_reply(first_gen, "当代答复")
    assert _texts(dialog) == ["当代答复"]

    dialog.start_with_image(_image())   # 新会话：代号 +1，消息清空
    # 清空气泡走 deleteLater：QEvent.DeferredDelete 不由 processEvents 派发
    # （本机实测），要用 sendPostedEvents 刷
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert _texts(dialog) == []
    dialog._on_reply(first_gen, "迟到的旧答复")   # 旧代号 → 丢弃
    assert _texts(dialog) == [], "旧会话的答复落进了新会话"
    dialog.close()


def test_a_stale_failure_does_not_unlock_the_new_sessions_send(qapp):
    """旧会话的失败回执不能把新会话正在跑的发送锁解开。"""
    dialog = _dialog()
    dialog.start_with_image(_image())
    first_gen = dialog._gen
    dialog.start_with_image(_image())     # 新会话（代号 +1）
    dialog._sending = True                # 新会话的发送进行中
    dialog._on_error(first_gen, "旧会话的网络超时")   # 旧代号 → 不动发送锁
    assert dialog._sending is True, "旧回执解开了新会话的发送锁"
    dialog.close()


# ------------------------------------------------------- 标题栏品牌标识（DS logo）


def _pin_whale(monkeypatch, *, missing: bool = False):
    """把标题栏 logo 的来源钉成 DS logo（``missing=True`` 钉成素材缺席，验回退）。"""
    import pet.screen_capture.ask_dialog as ask_mod
    from pet.screen_capture import brand_icons
    from PySide6.QtGui import QPixmap

    src = (lambda: QPixmap()) if missing else brand_icons.load_ds_whale
    monkeypatch.setattr(ask_mod, "load_ds_whale", lambda: src())
    return src()


def test_the_title_bar_shows_the_ds_logo_instead_of_the_words(qapp, monkeypatch):
    """标题栏就是品牌标识本身：原来的「截图问答」四字被固定 DS logo 直接顶掉。

    文字旁边**不许**再挂一个图标——那是两件东西各说各话。
    """
    whale = _pin_whale(monkeypatch)
    dialog = _dialog()
    dialog.start_with_image(_image())

    assert dialog._title.text() == "", "logo 没有顶掉标题文字"
    assert dialog._title_src is whale, "标题栏挂的必须是 DS logo"
    assert dialog._title_scaled is not None and dialog._title_scaled.isNull() is False
    assert dialog._title.pixmap().isNull() is False, "标题栏没有把 logo 画出来"
    assert dialog.findChildren(QLabel, "screen-ask-egg") == [], "文字旁又冒出一个图标位"
    dialog.close()


def test_the_title_bar_keeps_the_window_title_and_accessible_name(qapp, monkeypatch):
    """logo 顶掉的是画面，不是身份：窗口标题与无障碍名照旧可识别。"""
    _pin_whale(monkeypatch)
    dialog = _dialog()
    dialog.start_with_image(_image())

    assert dialog.windowTitle() == "截图问答"
    assert dialog._title.accessibleName() == "截图问答"
    dialog.close()


def test_opening_the_dialog_never_rolls_the_title(qapp, monkeypatch):
    """不随机标题：开一次问答窗一次骰子都不掷（鲸蛙只在加载动画里出场）。"""
    import random

    _pin_whale(monkeypatch)
    rolls: list[float] = []
    monkeypatch.setattr(random, "random", lambda: rolls.append(1.0) or 0.5)

    dialog = _dialog()
    dialog.start_with_image(_image())
    dialog.close()
    dialog.start_with_image(_image())

    assert rolls == [], "开窗时掷了骰子——标题会被随机换掉"
    dialog.close()


def test_the_title_logo_stays_the_same_across_opens(qapp, monkeypatch):
    """固定 logo：换图开新会话（窗口复用）也不换标识。"""
    _pin_whale(monkeypatch)
    dialog = _dialog()
    dialog.start_with_image(_image())
    first = dialog._title_src

    dialog.close()
    dialog.start_with_image(_image())

    assert dialog._title_src is first
    assert dialog._title.text() == ""
    dialog.close()


def test_the_title_bar_falls_back_to_the_words_when_the_asset_is_missing(qapp, monkeypatch):
    """素材缺席：退回那四个字（窗口照常开，标识不许变成空白洞）。"""
    _pin_whale(monkeypatch, missing=True)
    dialog = _dialog()
    dialog.start_with_image(_image())

    assert dialog._title.text() == "截图问答"
    assert dialog._title_src.isNull() is True
    assert dialog._title_scaled is None
    assert dialog.isVisible() is True
    assert dialog.windowTitle() == "截图问答"
    dialog.close()


def test_the_title_logo_follows_device_pixel_ratio(qapp, monkeypatch):
    """logo 按 DPR 出物理像素（offscreen 恒 1.0，走注入缝验证）。"""
    _pin_whale(monkeypatch)
    dialog = _dialog()
    dialog.start_with_image(_image())
    dialog._refresh_title_icon(dpr=2.0)
    pix = dialog._title_scaled
    assert pix.devicePixelRatio() == 2.0
    assert pix.width() == 48
    dialog.close()


def test_the_title_logo_is_rescaled_on_screen_change_without_changing_material(qapp, monkeypatch):
    """换屏只按新 DPR 重出同一张 logo，不换素材。"""
    _pin_whale(monkeypatch)
    dialog = _dialog()
    dialog.start_with_image(_image())
    first_src, first_scaled = dialog._title_src, dialog._title_scaled

    handle = dialog.windowHandle()
    assert handle is not None
    handle.screenChanged.emit(dialog.screen())

    assert dialog._title_scaled is not first_scaled, "换屏要按新 DPR 重出"
    assert dialog._title_src is first_src, "换屏换了素材"
    dialog.close()
