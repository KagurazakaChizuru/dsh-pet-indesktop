# -*- coding: utf-8 -*-
"""Phase 4.1a overlay 产品壳 offscreen 单测（QT_QPA_PLATFORM=offscreen 可跑）。

覆盖：is_overlay_topology env 契约；OverlayShell 构建期 dpr/bounds/默认右下
角落位；tick 顺序协议（行为→碰撞→物理，装桩记录调用序）；start/stop 幂等；
音效预热接线（首次可见前预热一次、开关关闭零调用）；geometryChanged 的 rx/ry
比例迁移；屏拔除的 overlay 重建与拖拽收尾；会话结束与退出收口；app.py 拓扑
分支（默认路径不构造 OverlayShell）。
纪律：同步直调 handler / _on_tick(dt=...)，不 sleep 赌时序（AGENTS.md 时序
测试纪律）；sprite/库/屏用纯假实现，不碰 webm 素材与 ffmpeg。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Signal
from PySide6.QtWidgets import QApplication

import pet.app as app_mod
import pet.overlay_shell as overlay_shell_mod
from pet import click_sound
from pet.app import AppShell
from pet.config import Config
from pet.overlay_shell import OverlayShell, is_overlay_topology

app = QApplication.instance() or QApplication([])


# ---------------------------------------------------------------- 假屏 / 假 sprite / 假实例
class FakeScreen(QObject):
    """鸭式 QScreen：几何/可用区/DPR 可变，带 Qt 信号验证真实接线。"""

    geometryChanged = Signal(QRect)
    availableGeometryChanged = Signal(QRect)

    def __init__(self, geo, avail, *, dpr=1.0, refresh=60.0, name="fake-screen"):
        super().__init__()
        self._geo = QRect(*geo)
        self._avail = QRect(*avail)
        self._dpr = float(dpr)
        self._refresh = float(refresh)
        self._name = name

    def set_rects(self, geo, avail, *, dpr=None):
        self._geo = QRect(*geo)
        self._avail = QRect(*avail)
        if dpr is not None:
            self._dpr = float(dpr)

    def geometry(self):
        return QRect(self._geo)

    def availableGeometry(self):
        return QRect(self._avail)

    def devicePixelRatio(self):
        return self._dpr

    def refreshRate(self):
        return self._refresh

    def name(self):
        return self._name


class FakeSprite:
    """记录 set_dpr/set_bounds/set_pos 调用的假 sprite（对接 4.1a 接口契约）。"""

    SIZE = (120, 80)

    def __init__(self, lib, pos, scale):
        self.lib = lib
        self.pos = QPointF(pos)
        self.scale = scale
        self.home_screen = None
        self.dpr_calls: list[float] = []
        self.bounds_calls: list[QRect] = []
        self.pos_calls: list[QPointF] = []
        self.releases: list[QPointF] = []
        self.dragging = False
        self.interaction_state = "normal"

    def rect(self):
        return QRect(int(self.pos.x()), int(self.pos.y()), *self.SIZE)

    def set_dpr(self, dpr):
        self.dpr_calls.append(float(dpr))

    def set_bounds(self, bounds):
        self.bounds_calls.append(QRect(bounds))

    def set_pos(self, pos):
        self.pos = QPointF(pos)
        self.pos_calls.append(QPointF(pos))

    def advance(self, dt):
        return None

    def paint(self, painter):
        pass

    def alpha_at(self, local):
        return 0

    def on_release(self, pos):
        self.releases.append(QPointF(pos))
        self.dragging = False


class FakeLibrary:
    def __init__(self):
        self.manifest = {}
        self.folder_map = {}
        self.folder_files = {}
        self.stopped_all = 0
        self.paused = 0
        self.provision_cancels = 0

    def names(self):
        return []

    def stop_all_clips(self):
        self.stopped_all += 1

    def cancel_frameseq_provision(self):
        self.provision_cancels += 1

    def pause_warm(self):
        self.paused += 1


class FakeConfig:
    def __init__(self, values=None):
        self._values = dict(values or {})

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value


class FakeInstance:
    def __init__(self, config=None):
        self.config = config or FakeConfig()
        self.created_character_ids: list[str] = []

    def _create_library(self, character_id):
        self.created_character_ids.append(character_id)
        return FakeLibrary()


def _make_shell(screen=None, instance=None):
    screen = screen or FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040))
    instance = instance or FakeInstance()
    shell = OverlayShell(
        app, instance, screen=screen,
        sprite_factory=lambda lib, pos, scale: FakeSprite(lib, pos, scale))
    return shell, screen, instance


# ---------------------------------------------------------------- env flag 契约
def test_is_overlay_topology_env_contract(monkeypatch):
    # T5 默认化：默认 overlay；PET_RENDER_TOPOLOGY=legacy 是唯一逃生门
    monkeypatch.delenv("PET_RENDER_TOPOLOGY", raising=False)
    assert is_overlay_topology() is True
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", "overlay")
    assert is_overlay_topology() is True
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", "legacy")
    assert is_overlay_topology() is False
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", "")
    assert is_overlay_topology() is True


# ---------------------------------------------------------------- 构建期：dpr/bounds/右下角
def test_shell_wires_dpr_bounds_and_default_corner():
    screen = FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040), dpr=1.5)
    shell, _, instance = _make_shell(screen=screen)

    sprite = shell.sprite
    assert sprite is not None
    assert sprite in shell.overlay.sprites
    assert sprite.home_screen is screen
    assert sprite.dpr_calls == [1.5]                       # 构建即喂主屏 DPR
    assert sprite.bounds_calls[0] == QRect(0, 0, 1920, 1040)  # 可用区转 overlay 局部
    # 控制器进程级一组；行为/物理边界 = overlay 局部可用区
    assert shell.behavior.bounds == QRect(0, 0, 1920, 1040)
    assert shell.physics.bounds == QRectF(0, 0, 1920, 1040)
    assert shell.overlay.behavior is shell.behavior        # contextMenuEvent 查表点
    # 默认右下角（go_default_corner 旧算式：右缘留 CORNER_MARGIN、底贴可用区底）
    expected = QPointF(1920 - 1 - FakeSprite.SIZE[0] - 24, 1040 - 1 - FakeSprite.SIZE[1])
    assert sprite.pos_calls[-1] == expected
    assert sprite.pos == expected
    # per-pet 库：经实例 _create_library 按配置角色创建（T3）
    assert instance.created_character_ids == ["shenshen"]


def test_shell_library_character_fallback():
    class MissingLibInstance(FakeInstance):
        def _create_library(self, character_id):
            self.created_character_ids.append(character_id)
            if character_id != "shenshen":
                raise FileNotFoundError(character_id)
            return FakeLibrary()

    instance = MissingLibInstance(FakeConfig({"character": "dlc-gone"}))
    shell, _, _ = _make_shell(instance=instance)
    assert instance.created_character_ids == ["dlc-gone", "shenshen"]
    assert instance.config.get("character") == "shenshen"
    assert shell.lib is not None


# ---------------------------------------------------------------- tick 装配与顺序协议（M-2）
def test_shell_assembles_process_level_tick_driver():
    """M-2/T2：驱动器独立持有三控制器，overlay 只被驱动（不再挂 tick 钩子）。"""
    shell, _, _ = _make_shell()
    driver = shell.driver
    assert driver is not None
    assert shell.overlay.tick_driver is driver          # 同一驱动器驱动本 overlay
    assert driver.overlays == [shell.overlay]
    assert driver.behavior is shell.behavior
    assert driver.collision is shell.collision
    assert driver.physics is shell.physics
    # 产品 overlay 不再覆写兼容钩子（仿真段唯一入口 = 驱动器 tick_sim）
    assert "before_sprites_advance" not in type(shell.overlay).__dict__


def test_tick_order_behavior_collision_physics():
    shell, _, _ = _make_shell()
    calls = []

    class Recorder:
        def __init__(self, name):
            self.name = name

        def tick(self, sprites, dt):
            calls.append((self.name, list(sprites), dt))

    # M-2 后控制器由驱动器持有：替换点从 shell 属性面移到驱动器装配点
    shell.driver.set_controllers(Recorder("behavior"), Recorder("collision"),
                                 Recorder("physics"))
    shell.overlay._on_tick(dt=0.016)  # 同步直调，不跑真 QTimer

    assert [c[0] for c in calls] == ["behavior", "collision", "physics"]
    for _, sprites, dt in calls:
        assert sprites == [shell.sprite]
        assert dt == 0.016


# ---------------------------------------------------------------- 生命周期
def test_start_stop_idempotent():
    shell, _, _ = _make_shell()
    calls = []

    class Nop:
        def tick(self, sprites, dt):
            calls.append(1)

    shell.behavior = shell.collision = shell.physics = Nop()

    assert not shell.overlay._timer.isActive()
    shell.start()
    assert shell.overlay._timer.isActive()
    shell.start()  # 幂等：重复 start 不重建
    assert shell.overlay._timer.isActive()
    shell.stop()
    assert not shell.overlay._timer.isActive()
    shell.stop()   # 幂等：重复 stop 是 no-op
    assert not shell.overlay._timer.isActive()


# ---------------------------------------------------------------- 音效预热接线（P1 音频冷启动）
class _BodySprite(FakeSprite):
    """FakeSprite + body_rect（spawn 落位需要主宠身体矩形）。"""

    def body_rect(self):
        return self.rect()


def _warm_spy(monkeypatch, calls, shell=None):
    """替换音效预热入口（模块级 OS 音频边界），记录参数与调用时的可见性。

    替换的是 ``pet.click_sound.warm_click_sound_effects``（产品侧以模块属性
    调用），与 ``tests/test_requested_regressions.py`` 替换设置页同名入口同风格——
    不碰 winmm/DLL/声卡。
    """
    def spy(pack, data_dir=None, limit=8):
        visible = shell.overlay.isVisible() if shell is not None else None
        calls.append((pack, data_dir, visible))
    monkeypatch.setattr(click_sound, "warm_click_sound_effects", spy)


def test_start_warms_sound_before_overlay_visible(tmp_path, monkeypatch):
    """overlay 首次可见前必须预热音效后端（口径 = legacy app.py:535-539）。

    缺这段接线时 overlay 拓扑一次都不预热，本进程第一次发声要付 winmm
    ``waveOutOpen`` 冷启动（实测 159.6ms，落在 GUI 事件循环里：
    .scratch/arch-ab/CTL-COLL-SOUND-NEW-10-REPORT.md）。参数必须与 legacy
    同一入口同一来源：真 Config 的 click_sound_pack + config.dir。
    """
    pack = {"kind": "builtin", "id": "duck"}
    config = Config(tmp_path)
    config.set("click_sound_enabled", True)
    config.set("click_sound_pack", pack)
    shell, _, _ = _make_shell(instance=FakeInstance(config))
    calls = []
    _warm_spy(monkeypatch, calls, shell)

    shell.start()

    assert calls == [(config.get("click_sound_pack"), config.dir, False)]
    assert shell.overlay.isVisible()             # 反证：prewarm 时确实还没可见


def test_start_skips_sound_warm_when_both_switches_off(monkeypatch):
    """两开关都关：绝不预热（同 legacy 的 OR 闸门），不无谓拉起音频后端。"""
    config = FakeConfig(
        {"click_sound_enabled": False, "collision_sound_enabled": False})
    shell, _, _ = _make_shell(instance=FakeInstance(config))
    calls = []
    _warm_spy(monkeypatch, calls)

    shell.start()

    assert calls == []


def test_three_in_process_pets_warm_sound_once(monkeypatch):
    """三宠同进程（overlay 多宠 = spawn 进同一壳）：预热只发生一次。"""
    instance = FakeInstance(FakeConfig({"click_sound_enabled": True}))
    shell = OverlayShell(
        app, instance,
        screen=FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040)),
        sprite_factory=lambda lib, pos, scale: _BodySprite(lib, pos, scale))
    shell._create_main_library = FakeLibrary
    calls = []
    _warm_spy(monkeypatch, calls)

    shell.start()
    shell.spawn_pet()
    shell.spawn_pet()

    assert len(shell._spawned) == 2  # 前提：三宠确实同进程存在
    assert len(calls) == 1


def test_stop_start_does_not_repeat_sound_warm(monkeypatch):
    """stop→start（重 show）不重复预热：池是进程级，重复预热纯浪费。

    配置顺带走「只开碰撞音效」分支（OR 闸门的另一半）：点击音效关时也必须
    预热，否则碰碰车场景的碰撞音效仍在首次发声付冷启动。
    """
    shell, _, _ = _make_shell(instance=FakeInstance(
        FakeConfig({"click_sound_enabled": False,
                    "collision_sound_enabled": True})))
    calls = []
    _warm_spy(monkeypatch, calls)

    shell.start()
    shell.stop()
    shell.start()

    assert len(calls) == 1


# ---------------------------------------------------------------- 屏事件：geometryChanged 比例迁移
def test_geometry_change_migrates_sprite_proportionally():
    screen = FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040), dpr=1.0)
    shell, _, _ = _make_shell(screen=screen)
    sprite = shell.sprite
    # 摆到可用区正中：中心 (960, 520) → rx=ry=0.5
    sprite.pos_calls.clear()
    sprite.set_pos(QPointF(960 - 60, 520 - 40))
    sprite.pos_calls.clear()

    screen.set_rects((0, 0, 1280, 720), (0, 0, 1280, 680), dpr=2.0)
    screen.geometryChanged.emit(screen.geometry())   # 走真信号接线，不直调 handler

    assert shell.overlay.geometry() == QRect(0, 0, 1280, 720)
    assert shell.behavior.bounds == QRect(0, 0, 1280, 680)
    assert shell.physics.bounds == QRectF(0, 0, 1280, 680)
    assert sprite.bounds_calls[-1] == QRect(0, 0, 1280, 680)
    assert sprite.dpr_calls[-1] == 2.0               # 几何变化重喂 DPR
    # rx/ry 不变：新中心 = (640, 340) → pos = (580, 300)
    assert sprite.pos == QPointF(640 - 60, 340 - 40)


def test_geometry_change_with_offset_origin():
    # 屏原点非 (0,0)（副屏场景）：可用区换算 overlay 局部坐标
    screen = FakeScreen((1920, 0, 1920, 1080), (1920, 40, 1920, 1040))
    shell, _, _ = _make_shell(screen=screen)
    sprite = shell.sprite
    assert sprite.bounds_calls[0] == QRect(0, 40, 1920, 1040)

    sprite.set_pos(QPointF(960 - 60, 40 + 520 - 40))  # 中心 (960, 560)：rx=0.5, ry=0.5
    screen.set_rects((1920, 0, 1280, 720), (1920, 40, 1280, 680))
    shell.handle_geometry_changed()                   # 直调 handler 路径

    assert sprite.bounds_calls[-1] == QRect(0, 40, 1280, 680)
    assert sprite.pos == QPointF(640 - 60, 40 + 340 - 40)


# ---------------------------------------------------------------- 屏事件：拔除 → 重建
def test_screen_removed_rebuilds_overlay_on_primary():
    fake = FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040))
    shell, _, _ = _make_shell(screen=fake)
    sprite = shell.sprite
    old_overlay = shell.overlay
    primary = app.primaryScreen()

    # 拖拽中拔屏：先收尾拖拽再迁移（v1.1 §10）
    sprite.dragging = True
    old_overlay._mouse_grab = sprite
    old_overlay._press_global = QPointF(10, 10).toPoint()

    shell.handle_screen_removed(fake)

    assert shell._screen is primary
    assert shell.overlay is not old_overlay            # overlay 重建
    assert sprite not in old_overlay.sprites
    assert sprite in shell.overlay.sprites
    assert sprite.home_screen is primary
    assert len(sprite.releases) == 1                   # 拖拽被收尾
    assert old_overlay._mouse_grab is None
    assert not old_overlay._timer.isActive()
    assert sprite.dpr_calls[-1] == float(primary.devicePixelRatio())
    primary_bounds = OverlayShell._local_bounds(primary)
    assert shell.behavior.bounds == primary_bounds


def test_screen_removed_other_screen_keeps_overlay():
    fake = FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040))
    shell, _, _ = _make_shell(screen=fake)
    other = FakeScreen((1920, 0, 1920, 1080), (1920, 0, 1920, 1040), name="other")
    old_overlay = shell.overlay
    shell.handle_screen_removed(other)
    assert shell.overlay is old_overlay                # 非当前屏：不重建
    assert shell._screen is fake


# ---------------------------------------------------------------- 会话结束 / 退出收口
def test_session_end_stops_all_clips_and_tick_idempotent():
    shell, _, _ = _make_shell()
    shell.overlay._timer.start()                       # 制造"tick 运转中"状态
    shell._on_session_end()
    assert shell.lib.stopped_all == 1
    assert not shell.overlay._timer.isActive()
    shell._on_session_end()                            # 幂等
    assert shell.lib.stopped_all == 1
    shell.overlay._timer.stop()


def test_about_to_quit_pauses_warm_and_stops_tick():
    shell, _, _ = _make_shell()
    shell.overlay._timer.start()
    shell._on_about_to_quit()
    assert shell.lib.paused == 1
    assert not shell.overlay._timer.isActive()


def test_about_to_quit_cancels_frameseq_provision():
    """退出收口必须取消在飞的帧序列供给线程（B1）。

    供给线程**不是**预热线程：``pause_warm`` 管不到它，而它自己派生转换 ffmpeg
    ——退出/关机窗口里最不该有的派生（issue #111）；库随本壳销毁时活线程还会被
    一起析构（Qt fatal）。原来的退出收口只 pause_warm，这条改用例会红。
    """
    shell, _, _ = _make_shell()
    shell._on_about_to_quit()
    assert shell.lib.paused == 1
    assert shell.lib.provision_cancels == 1


def test_about_to_quit_cancels_provision_for_spawned_libraries(monkeypatch):
    """子肥鱼各持独立库（M8）：逐库取消，不只主库。"""
    instance = FakeInstance(FakeConfig({"click_sound_enabled": False}))
    shell = OverlayShell(
        app, instance,
        screen=FakeScreen((0, 0, 1920, 1080), (0, 0, 1920, 1040)),
        sprite_factory=lambda lib, pos, scale: _BodySprite(lib, pos, scale))
    shell._create_main_library = FakeLibrary
    calls = []
    _warm_spy(monkeypatch, calls)
    shell.start()
    shell.spawn_pet()
    spawned = list(shell._spawned_libs.values())
    assert spawned                                     # 前提：确实有子库

    shell._on_about_to_quit()

    assert shell.lib.provision_cancels == 1
    assert [lib.provision_cancels for lib in spawned] == [1] * len(spawned)


# ---------------------------------------------------------------- app.py 拓扑分支
def _stub_shell_start(shell, monkeypatch):
    """把 start() 里分支点之外的进程级副作用全部换成 no-op 记录器。"""
    monkeypatch.setattr(shell._dsh_state_tracker, "start", lambda: None)
    monkeypatch.setattr(AppShell, "_sync_dynamic_island", lambda self: None)


def test_app_start_default_path_does_not_touch_overlay_shell(tmp_path, monkeypatch):
    # legacy 逃生门路径不构造 OverlayShell（默认路径见下方 overlay 用例）
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", "legacy")
    constructed = []
    monkeypatch.setattr(overlay_shell_mod, "OverlayShell",
                        lambda *a, **kw: constructed.append((a, kw)))
    ui_calls = []
    monkeypatch.setattr(AppShell, "_create_ui_with_character_fallback",
                        lambda self, cid: ui_calls.append(cid))

    shell = AppShell(app, Config(tmp_path))
    _stub_shell_start(shell, monkeypatch)
    shell.start()

    assert constructed == []                           # 默认路径不构造 OverlayShell
    assert ui_calls == ["shenshen"]                    # 旧路径主窗创建照常
    assert getattr(shell, "_overlay_shell", None) is None


def test_app_start_overlay_topology_takes_overlay_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", "overlay")
    created = []

    class FakeOverlayShell:
        def __init__(self, qapp, instance, **kwargs):
            self.qapp = qapp
            self.instance = instance
            self.kwargs = kwargs
            self.started = 0
            created.append(self)

        def start(self):
            self.started += 1

    monkeypatch.setattr(overlay_shell_mod, "OverlayShell", FakeOverlayShell)
    ui_calls = []
    monkeypatch.setattr(AppShell, "_create_ui_with_character_fallback",
                        lambda self, cid: ui_calls.append(cid))

    shell = AppShell(app, Config(tmp_path))
    _stub_shell_start(shell, monkeypatch)
    shell.start()

    assert len(created) == 1
    assert created[0].qapp is shell.app
    assert created[0].instance is shell.instance
    assert created[0].started == 1
    assert shell._overlay_shell is created[0]
    assert ui_calls == []                              # overlay 路径不建 PetWindow
    # 4.3 后半：D0 常建的共享子系统注入 sprite 世界的壳（扇出目标）
    assert shell._shared is not None
    assert created[0].kwargs["agent_link_manager"] is shell._shared.agent_link
    assert created[0].kwargs["proactive_watcher"] is shell._shared.proactive
    # 点击自言自语的朗读走同一条音频通道（AppShell 持有，进程内唯一）：
    # overlay 拓扑没有 PetWindow 可注入，落点必须是 sprite 壳
    assert created[0].on_self_talk_speak == shell.speak_self_talk


# ---------------------------------------------------------------- D0 门控解绑（T3）
def test_hub_and_shared_subsystems_are_always_on(tmp_path, monkeypatch):
    """D0 + 4.4b：hub 常开、共享子系统常建，**不再有任何 spawn flag 门控**。

    契约来源 PHASE4_DESIGN T3/D0：多 sprite/多窗同角色若各建解码链会退化成
    N 路独立 ffmpeg；共享子系统缺位则是静默缺失。4.4b 起 spawn 开关键已删除，
    拓扑差异只剩 OverlayShell 与 PetWindow 两条渲染面。
    """
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", "overlay")
    shell = AppShell(app, Config(tmp_path))
    try:
        assert shell._decode_hub.enabled is True       # hub 常开
        assert shell._shared is not None               # 共享子系统常建
    finally:
        shell._shared.stop_all()


def test_overlay_topology_hub_respects_shared_decode_off(tmp_path, monkeypatch):
    """用户级总闸 `experimental_shared_decode` 仍然生效。"""
    monkeypatch.setenv("PET_RENDER_TOPOLOGY", "overlay")
    cfg = Config(tmp_path)
    cfg.set("experimental_shared_decode", False)
    shell = AppShell(app, cfg)
    try:
        assert shell._decode_hub.enabled is False
        assert shell._shared is not None               # 两项门控彼此独立
    finally:
        shell._shared.stop_all()


def test_legacy_topology_also_builds_shared_subsystems(tmp_path, monkeypatch):
    """4.4b 回归护栏：legacy 拓扑同样常建共享子系统（T6 常开化）。

    hub 的开关收敛为用户级 `experimental_shared_decode`（默认开）。
    """
    monkeypatch.delenv("PET_RENDER_TOPOLOGY", raising=False)
    shell = AppShell(app, Config(tmp_path))
    try:
        assert shell._decode_hub.enabled is True
        assert shell._shared is not None
    finally:
        shell._shared.stop_all()


# ---------------------------------------------------------------- 边缘探头壳层接线
def test_shell_wires_edge_probe_world():
    """edge_probe 接线：世界挂 driver extras（tick 尾段）+ overlay 事件钩子 +
    碰撞真撞击监听 + sprite 移除注销 + 几何变化 bounds 同步。"""
    shell, screen, _ = _make_shell()
    probe = shell._probe
    assert probe is not None
    assert probe in shell.driver._extras
    assert shell.overlay.edge_probe is probe
    # 碰撞监听已挂（真撞击链里有 probe 处理器）
    assert shell._on_collision_probe in shell.collision._listeners
    # 几何变化 → probe bounds 同步
    from PySide6.QtCore import QRect
    new_bounds = QRect(0, 0, 1280, 720)
    shell._apply_bounds(new_bounds)
    assert probe.bounds == new_bounds
    # sprite 移除监听已挂 probe.forget
    assert shell._probe.forget in shell.overlay._sprite_removed_listeners


def test_shell_wires_throw_egg_world():
    """throw_egg 接线：世界挂 driver extras（probe 之后）+ 碰撞真撞击 arm 链 +
    sprite 移除注销 + bounds 同步。"""
    shell, screen, _ = _make_shell()
    egg = shell._throw_egg
    assert egg is not None
    assert egg in shell.driver._extras
    # extras 顺序：probe 先（cancel 会话）、egg 后（读物理结算速度）
    assert shell.driver._extras.index(shell._probe) < shell.driver._extras.index(egg)
    assert egg.forget in shell.overlay._sprite_removed_listeners
    from PySide6.QtCore import QRect
    new_bounds = QRect(0, 0, 1280, 720)
    shell._apply_bounds(new_bounds)
    assert egg.bounds == new_bounds


def test_shell_wires_slingshot_config():
    """弹弓接线：overlay.slingshot 接 shell 的 config（slingshot_enabled 热读）。"""
    shell, _, _ = _make_shell()
    assert shell.overlay.slingshot.config is shell._config


def test_shell_attach_island_bridge():
    """岛桥接线：attach_island 幂等可重复调；桥挂进程级 collision 世界；
    None 摘桥；stop() 收口。"""
    from tests.test_island_bridge import StubIsland
    shell, _, _ = _make_shell()
    island = StubIsland()
    shell.attach_island(island)
    bridge = shell.island_bridge
    assert bridge is not None and bridge.attached
    shell.attach_island(island)  # 重复调：旧桥收口换新桥，不叠加
    assert shell.island_bridge is not bridge
    shell.attach_island(None)
    assert shell.island_bridge is None
    shell.attach_island(island)
    shell._on_about_to_quit()  # 退出收口（stop 只服务已 start 的壳）
    assert shell.island_bridge is None
