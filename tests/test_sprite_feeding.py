# -*- coding: utf-8 -*-
"""SpriteFeedingController offscreen 单测（4.1c 投喂）。

覆盖：命中 sprite 才 accept（未命中/无 URL ignore）、统计文件同格式落盘、
吃动画经 play_once 一次性播放、气泡接缝静默、dragMove 同判定。
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication

import tests.test_sprite_menu_facade as fac
from pet.sprite_feeding import SpriteFeedingController

app = QApplication.instance() or QApplication([])


def _drop_event(pos: QPointF, paths: list[str]):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    event = QDropEvent(pos, Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    event._mime_ref = mime  # QDropEvent 不持有 mime 所有权：Python 侧保活
    return event


def _drag_enter(pos: QPointF, paths: list[str]):
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
    event = QDragEnterEvent(pos.toPoint(), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    event._mime_ref = mime
    return event


def _make(tmp_path, config_values=None):
    shell, lib = fac._make_shell(tmp_path, config_values)
    # 生产里首帧上屏后命中图才存在；测试同步重建一帧（等同首个 paint）
    shell.sprite.bind_clip("idle1")
    shell.sprite._rebuild_pixmap()
    ctrl = SpriteFeedingController(shell.overlay, shell.sprite,
                                   shell._config, shell.behavior)
    return shell, lib, ctrl


def test_accept_only_over_sprite(tmp_path):
    shell, _lib, ctrl = _make(tmp_path)
    try:
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        over = QPointF(shell.sprite.rect().center())
        away = QPointF(10, 10)  # sprite 在右下角，(10,10) 必空
        e1 = _drag_enter(over, [str(tmp_path / "a.txt")])
        ctrl.handle_drag_enter(e1)
        assert e1.isAccepted()
        e2 = _drag_enter(away, [str(tmp_path / "a.txt")])
        ctrl.handle_drag_enter(e2)
        assert not e2.isAccepted()
        e3 = _drag_enter(over, [])          # 无 URL
        ctrl.handle_drag_enter(e3)
        assert not e3.isAccepted()
    finally:
        shell._delete_runtime_marker()


def test_drop_records_stats_and_plays_eat_anim(tmp_path):
    shell, lib, ctrl = _make(tmp_path)
    try:
        f1 = tmp_path / "snack.txt"
        f1.write_text("yummy", encoding="utf-8")
        bubbles = []
        ctrl._bubble_cb = lambda files, folders, b, stats: bubbles.append((files, folders, b))
        event = _drop_event(QPointF(shell.sprite.rect().center()), [str(f1)])
        result = ctrl.handle_drop(event)
        assert event.isAccepted()
        assert result["files"] == 1 and result["bytes"] == 5
        # 统计文件同格式落盘
        stats = json.loads((tmp_path / "file_eaten_stats.json").read_text(encoding="utf-8"))
        assert stats["feed_count"] == 1
        assert stats["file_count"] == 1
        assert stats["total_bytes"] == 5
        # 吃动画一次性播放（acts 池的 act1 被选中）
        assert shell.sprite._clip_name == "act1"
        assert lib._clips["act1"].started is True
        assert bubbles == [(1, 0, 5)]
    finally:
        shell._delete_runtime_marker()


def test_drop_ignored_away_from_sprite(tmp_path):
    shell, _lib, ctrl = _make(tmp_path)
    try:
        f1 = tmp_path / "snack.txt"
        f1.write_text("yummy", encoding="utf-8")
        event = _drop_event(QPointF(10, 10), [str(f1)])
        assert ctrl.handle_drop(event) is None
        assert not event.isAccepted()
        assert not (tmp_path / "file_eaten_stats.json").exists()
    finally:
        shell._delete_runtime_marker()


def test_feeding_bubble_text_format(tmp_path):
    """投喂气泡文案（file_eater._show_feedback 同格式）经 shell 回调落到 follower。"""
    shell, _lib, _ctrl = _make(tmp_path)
    try:
        said = []
        shell._bubble_follower.say = lambda text, **kw: said.append((text, kw)) or True
        f1 = tmp_path / "snack.txt"
        f1.write_text("yummy", encoding="utf-8")
        ctrl = shell._feeding
        event = _drop_event(QPointF(shell.sprite.rect().center()), [str(f1)])
        ctrl.handle_drop(event)
        assert len(said) == 1
        text, kw = said[0]
        assert "啊呜～吃掉 1 个文件" in text
        assert "累计吃掉 1 个文件" in text
        assert kw["subtitle"] == "放心，只是做个样子，文件没有删除或移动哦"
    finally:
        shell._delete_runtime_marker()


# ---------------------------------------------------------------- 解读询问接缝
def test_eat_paths_calls_interpret_offer(tmp_path):
    """吃完后必须询问解读（旧 ``file_eater.eat_paths:183-186`` 的接缝）。"""
    shell, _lib, ctrl = _make(tmp_path)
    try:
        offered: list = []
        ctrl.interpret_offer = offered.append
        f1 = tmp_path / "a.txt"
        f1.write_text("x", encoding="utf-8")
        event = _drop_event(QPointF(shell.sprite.rect().center()), [str(f1)])
        ctrl.handle_drop(event)
        assert len(offered) == 1, "投喂后必须把原始路径交给解读控制器"
        assert [Path(p) for p in offered[0]] == [f1]
    finally:
        shell._delete_runtime_marker()


def test_eat_paths_without_offer_is_silent(tmp_path):
    """未注入解读控制器（无聊天变体/未接线）：投喂照旧，不抛。"""
    shell, _lib, ctrl = _make(tmp_path)
    try:
        assert ctrl.interpret_offer is None
        f1 = tmp_path / "a.txt"
        f1.write_text("x", encoding="utf-8")
        event = _drop_event(QPointF(shell.sprite.rect().center()), [str(f1)])
        assert ctrl.handle_drop(event) is not None
    finally:
        shell._delete_runtime_marker()


def test_shell_file_interpret_offer_seam_survives_rebind(tmp_path):
    """壳侧注入接缝：``set_file_interpret_offer`` 落到控制器，重挂不丢。

    壳在「主宠提升 / 屏迁移」时都会 ``_bind_feeding()`` 重建控制器——接缝必须
    由壳持有并在重挂时回填，否则拖文件解读在那些路径之后静默失效。
    """
    shell, _lib, _ctrl = _make(tmp_path)
    try:
        offered: list = []
        shell.set_file_interpret_offer(offered.append)
        assert shell._feeding.interpret_offer is not None

        shell._bind_feeding()          # 主宠提升/屏迁移的重挂路径
        assert shell._feeding.interpret_offer is not None, "重挂后接缝必须还在"

        f1 = tmp_path / "a.txt"
        f1.write_text("x", encoding="utf-8")
        event = _drop_event(QPointF(shell.sprite.rect().center()), [str(f1)])
        shell._feeding.handle_drop(event)
        assert len(offered) == 1
        assert [Path(p) for p in offered[0]] == [f1]
    finally:
        shell._delete_runtime_marker()
