"""AI 回复的 Markdown 渲染（pet/chat/markdown_view.py + MessageBubble）。"""
from __future__ import annotations

from PySide6.QtWidgets import QApplication

from pet.chat.markdown_view import markdown_to_html, preserve_line_breaks


def _app():
    return QApplication.instance() or QApplication([])



def test_single_newlines_become_hard_breaks_outside_code_fences():
    src = "第一行\n第二行\n\n```\ncode a\ncode b\n```\n末行"
    out = preserve_line_breaks(src).split("\n")
    assert out[0] == "第一行  "
    assert out[1] == "第二行"  # 段落末行（下一行空）不加
    assert out[4] == "code a"  # 代码块内原样
    assert out[5] == "code b"


def test_table_right_after_text_line_still_renders_as_table():
    _app()
    html = markdown_to_html("对比如下：\n| 项目 | 数值 |\n|---|---|\n| 内存 | 220MB |")
    assert "<table" in html
    assert "对比如下：" in html


def test_markdown_renders_formatting_and_escapes_raw_html():
    _app()
    html = markdown_to_html("**加粗** `code`\n| a | b |\n|---|---|\n| 1 | 2 |\n\n<b>raw</b> [链接](https://example.com)")
    assert "font-weight:700" in html
    assert "Consolas" in html
    assert "<table" in html
    assert "&lt;b&gt;raw&lt;/b&gt;" in html  # 原始 HTML 只按字面显示
    assert 'href="https://example.com"' in html
    assert "font-size:9pt" not in html  # 不覆盖气泡自身字体


def test_assistant_bubble_renders_markdown_but_keeps_raw_text_for_copy():
    from pet.chat.widgets import MessageBubble

    app = _app()
    src = "**重点**\n- 一\n- 二"
    bubble = MessageBubble("assistant", src)
    assert bubble.content == src
    assert "font-weight:700" in bubble.body.text()
    bubble.copy_button.click()
    assert app.clipboard().text() == src
    user = MessageBubble("user", "**不渲染**")
    assert user.body.text() == "**不渲染**"
    bubble.set_content("请求失败：<x> **原样**", markdown=False)
    assert bubble.body.text() == "请求失败：<x> **原样**"


def test_slow_markdown_render_is_throttled_while_streaming_and_flushed_on_finish():
    from pet.chat.widgets import MessageBubble

    _app()
    bubble = MessageBubble("assistant", "")
    bubble.set_state("streaming")
    bubble._render_cost_ms = 30.0  # 模拟长回答：单次渲染+排版 30ms
    bubble.set_content("**第一版**")
    assert bubble._render_timer.isActive()  # 合并到定时器，不在这一拍同步重排
    assert "第一版" not in bubble.body.text()
    bubble.set_content("**最终版**")
    bubble.set_state("normal")  # 结束流式：立刻渲染最终内容
    assert not bubble._render_timer.isActive()
    assert "最终版" in bubble.body.text() and "font-weight:700" in bubble.body.text()


def test_legacy_bubble_renders_markdown_for_assistant():
    """经典聊天窗口（chat_ui_style=classic）的助手气泡同样走 Markdown；
    用户气泡保持纯文本（模型输出才可能含 markdown 标记）。"""
    _app()
    from pet.chat.legacy_widgets import MessageBubble

    assistant = MessageBubble("assistant", "重点**加粗**收尾")
    assert 'font-weight:700' in assistant.body.text() and "加粗" in assistant.body.text()  # Qt 写 span 而非 <strong>
    user = MessageBubble("user", "原样**不渲染**")
    assert "<strong>" not in user.body.text()
    assistant.deleteLater()
    user.deleteLater()
