# -*- coding: utf-8 -*-
"""HDR 抓帧通道（``pet/screen_capture/hdr_capture.py``）的离屏测试。

这里**跑不了真 DXGI**（offscreen 环境 + CI 无 HDR 屏），所以分三层测：

1. **换算数学**（``fp16_scrgb_to_srgb8``）——纯函数，直接喂合成数组。它是"色彩
   口径对不对"的唯一机器可判定部分：0 → 0、SDR 白点 → 255、超白点削平、
   单调、sRGB 曲线形状（线性 0.5 → 188，不是截断的 128）；
2. **判定逻辑**（``hdr_state`` / 会话缓存 / 退避）——把 Windows 侧那几个只读
   查询函数换成替身，验的是"读不到/没开/白点为 0 一律按未启用"，
   以及"失败之后不再反复付建设备的钱"；
3. **接线**（``pixels.grab_screen_image``）——HDR 关、通道返回 ``None``、通道抛
   异常、逃生门环境变量：四条路都必须落到原来的 ``grabWindow`` 路径且行为不变。

真机路径（DXGI + D3D11 + 真实显示器）由 ``.scratch/screen-capture/
probe_hdr_capture_ab.py`` 负责，不在这里假装。
"""

from __future__ import annotations

import ctypes
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pet.screen_capture import hdr_capture, pixels  # noqa: E402
from pet.screen_capture.hdr_capture import (  # noqa: E402
    DISABLE_ENV,
    fp16_scrgb_to_srgb8,
    grab_hdr_sdr,
    hdr_capture_disabled,
    hdr_state,
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _clean_caches():
    """会话缓存与退避表是模块级的：每条用例前后都清，避免互相串味。"""
    hdr_capture._SESSIONS.clear()
    hdr_capture._FAILED_UNTIL.clear()
    yield
    hdr_capture._SESSIONS.clear()
    hdr_capture._FAILED_UNTIL.clear()


# ------------------------------------------------------------------ 测试替身


def _fake_screen(name="H27T22S", *, geometry=(0, 0, 2560, 1440), dpr=1.0, grabbed=None):
    """QScreen 的最小替身：``grabWindow`` 计数 + 定位用的名字/几何。"""

    class _Screen:
        def __init__(self) -> None:
            self.calls = 0
            self._grabbed = grabbed

        def name(self):
            return name

        def geometry(self):
            return SimpleNamespace(x=lambda: geometry[0], y=lambda: geometry[1],
                                   width=lambda: geometry[2], height=lambda: geometry[3])

        def devicePixelRatio(self):  # noqa: N802 - 对齐 Qt 命名
            return dpr

        def grabWindow(self, window=0, *args):  # noqa: N802
            self.calls += 1
            return self._grabbed if self._grabbed is not None else QPixmap(8, 8)

    return _Screen()


def _patch_platform(monkeypatch):
    monkeypatch.setattr(hdr_capture, "_platform_ok", lambda: True)


def _fp16(*pixels_rgba) -> bytes:
    """若干 RGBA float16 像素 → 紧凑的行字节（``8 × 像素数`` 字节）。"""
    values = np.array(pixels_rgba, dtype=np.float16).reshape(len(pixels_rgba), 4)
    return np.ascontiguousarray(values).tobytes()


def _rgb8(*pixels_rgba, row_pitch=None) -> bytes:
    """按行距排布的一行 FP16 数据；``row_pitch`` 大于行长时行尾填 0xFF（垃圾）。"""
    row = _fp16(*pixels_rgba)
    if row_pitch is None:
        return row
    assert row_pitch >= len(row)
    return row + b"\xff" * (row_pitch - len(row))


# --------------------------------------------------------------- 换算数学


def test_fp16_scrgb_maps_zero_and_sdr_white_to_the_ends():
    """本机系数 3.5（3500/1000）：0 → 0，SDR 白点 3.5 → 255。"""
    out = fp16_scrgb_to_srgb8(_fp16((0.0, 0.0, 0.0, 1.0)), 1, 1, 8, 3.5)
    assert out.tolist() == [[[0, 0, 0]]]

    out = fp16_scrgb_to_srgb8(_fp16((3.5, 3.5, 3.5, 1.0)), 1, 1, 8, 3.5)
    assert out.tolist() == [[[255, 255, 255]]]


def test_fp16_scrgb_above_sdr_white_is_clipped():
    """比 SDR 白更亮的（HDR 高光）在 8-bit SDR 图里没有对应值：削到 255。"""
    for value in (3.6, 5.0, 20.0, float("inf")):
        out = fp16_scrgb_to_srgb8(_fp16((value, value, value, 1.0)), 1, 1, 8, 3.5)
        assert out.tolist() == [[[255, 255, 255]]], value


def test_fp16_scrgb_domain_errors_become_zero():
    """scRGB 里的域外值：负值与 NaN 归 0（参考实现同口径）。"""
    for value in (-1.0, -0.001, float("nan")):
        out = fp16_scrgb_to_srgb8(_fp16((value, value, value, 1.0)), 1, 1, 8, 3.5)
        assert out.tolist() == [[[0, 0, 0]]], value


def test_fp16_scrgb_applies_the_srgb_transfer_not_a_truncation():
    """线性 0.5 在 sRGB 下是 188；只换位深（截断）会得到 128——正是 HDR 屏
    "截出来发灰"的成因，也是这条通道存在的理由。"""
    out = fp16_scrgb_to_srgb8(_fp16((0.5, 0.5, 0.5, 1.0)), 1, 1, 8, 1.0)

    assert out[0, 0, 0] == 188
    assert out[0, 0, 0] != 128


def test_fp16_scrgb_curve_is_continuous_at_the_linear_knee():
    """0.0031308 是 sRGB 的分段点：两侧都得 10（不跳变）。"""
    below = fp16_scrgb_to_srgb8(_fp16((0.003, 0.0, 0.0, 1.0)), 1, 1, 8, 1.0)[0, 0, 0]
    at = fp16_scrgb_to_srgb8(_fp16((0.0031308, 0.0, 0.0, 1.0)), 1, 1, 8, 1.0)[0, 0, 0]
    above = fp16_scrgb_to_srgb8(_fp16((0.0032, 0.0, 0.0, 1.0)), 1, 1, 8, 1.0)[0, 0, 0]

    assert below == 10
    assert at == 10
    assert above == 11


def test_fp16_scrgb_is_monotonic():
    values = [0.0, 0.001, 0.003, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5,
              0.6, 0.7, 0.8, 0.9, 1.0, 1.5, 2.0, 3.5, 5.0]
    out = [int(fp16_scrgb_to_srgb8(_fp16((v, 0.0, 0.0, 1.0)), 1, 1, 8, 1.0)[0, 0, 0])
           for v in values]

    assert out == sorted(out)
    assert out[0] == 0 and out[-1] == 255


def test_fp16_scrgb_keeps_channel_order_rgb():
    out = fp16_scrgb_to_srgb8(_fp16((1.0, 0.5, 0.0, 1.0)), 1, 1, 8, 1.0)

    assert out[0, 0].tolist() == [255, 188, 0]


def test_fp16_scrgb_respects_row_pitch_padding():
    """行距大于行长（本机 2560×1440 的 RowPitch 就带填充）时按行距切，
    行尾的垃圾字节不许影响任何像素。"""
    row_pitch = 32
    buffer = _rgb8((1.0, 0.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0),
                   row_pitch=row_pitch)
    buffer = buffer * 2      # 两行一样的数据

    out = fp16_scrgb_to_srgb8(buffer, 3, 2, row_pitch, 1.0)

    assert out.shape == (2, 3, 3)
    assert out[0].tolist() == [[255, 0, 0], [0, 255, 0], [0, 0, 255]]
    assert out[1].tolist() == out[0].tolist()


def test_fp16_scrgb_rejects_bad_arguments():
    with pytest.raises(ValueError):
        fp16_scrgb_to_srgb8(b"\x00" * 16, 0, 1, 8, 1.0)
    with pytest.raises(ValueError):
        fp16_scrgb_to_srgb8(b"\x00" * 16, 1, 1, 4, 1.0)      # 行距装不下一个像素
    with pytest.raises(ValueError):
        fp16_scrgb_to_srgb8(b"\x00" * 16, 1, 1, 8, 0.0)      # 白点系数必须为正
    with pytest.raises(ValueError):
        fp16_scrgb_to_srgb8(b"\x00" * 16, 1, 1, 8, float("nan"))


def _scalar_reference(value: float, white: float) -> int:
    """单个 FP16 值的参考换算（标量写法，与实现里的向量写法各自独立表达）。

    NaN / ±inf / 负值按口径归到 0 或 255；其余走 sRGB 分段函数后四舍五入到 8 位。
    """
    import math

    if math.isnan(value):
        return 0
    linear = value / white
    if linear <= 0.0:
        return 0
    if math.isinf(linear) or linear >= 1.0:
        return 255
    encoded = 12.92 * linear if linear <= 0.0031308 else 1.055 * linear ** (1.0 / 2.4) - 0.055
    return min(255, max(0, int(encoded * 255.0 + 0.5)))


@pytest.mark.parametrize("white", [1.0, 3.5])
def test_fp16_scrgb_bit_pattern_table_matches_a_scalar_reference(white):
    """实现是按 **FP16 位模式** 查表的（快 7.7 倍），所以这一层的正确性必须查到位
    模式级别：表索引错一格、字节序反了、denormal 处理不对，都会让整张截图偏色，
    而普通的行为断言（0/白点/越界）看不出来。这里逐位模式对一遍标量参考实现。
    """
    patterns = list(range(0, 65536, 511))
    patterns += [0x0000, 0x0001, 0x03FF, 0x0400,             # 零 / denormal / 最小正规格化
                 0x3555, 0x3600,                             # 白点附近（3.33 / 3.5）
                 0x3800, 0x3C00, 0x4000, 0x4200,             # 0.5 / 1.0 / 2.0 / 3.0
                 0x7BFF, 0x7C00, 0x7C01, 0x7E00, 0x7FFF,     # 最大有限 / inf / sNaN / qNaN / NaN
                 0x8000, 0xFC00, 0xFFFF]                     # -0 / -inf / 负 NaN
    buffer = np.repeat(np.array(patterns, dtype=np.uint16), 4).tobytes()   # RGBA 各一

    out = fp16_scrgb_to_srgb8(buffer, len(patterns), 1, len(patterns) * 8, white)

    expected = [_scalar_reference(float(np.uint16(p).view(np.float16)), white)
                for p in patterns]
    assert out[0, :, 0].tolist() == expected


def test_fp16_scrgb_output_is_monotonic_over_all_bit_patterns():
    """单调性是"没有把通道顺序搞反 / 没有把符号位当数值"的廉价兜底。"""
    positives = np.arange(0x0000, 0x7C00, dtype=np.uint16)      # 0 → 最大有限正数
    buffer = np.repeat(positives, 4).tobytes()                  # RGBA 各一

    out = fp16_scrgb_to_srgb8(buffer, len(positives), 1, len(positives) * 8, 3.5)

    values = out[0, :, 0].tolist()
    assert values == sorted(values)
    assert values[0] == 0 and values[-1] == 255


# ----------------------------------------------------- ABI：结构体与槽位


def test_win32_struct_sizes_match_the_sdk_layout():
    """结构体尺寸是硬契约：对不上就静默读错字段（甚至越界）。

    逐条按本机 SDK 头文件（10.0.26100.0）的字段推导：
    ``DISPLAYCONFIG_MODE_INFO`` = 16 字节头 + 48 字节联合体 = 64；
    ``DISPLAYCONFIG_PATH_INFO`` = 20 + 48 + 4 = 72；
    ``MONITORINFOEXW`` = 4 + 16 + 16 + 4 + 32×2 = 104；
    ``D3D11_TEXTURE2D_DESC`` = 11 × UINT = 44；
    ``DXGI_OUTDUPL_FRAME_INFO`` = 8 + 8 + 4 + 4 + 4 + 12 + 4 + 4 = 48（8 对齐）。
    """
    assert ctypes.sizeof(hdr_capture._MODE_INFO) == 64
    assert ctypes.sizeof(hdr_capture._PATH_INFO) == 72
    assert ctypes.sizeof(hdr_capture._MONITORINFOEXW) == 104
    assert ctypes.sizeof(hdr_capture._TEXTURE2D_DESC) == 44
    assert ctypes.sizeof(hdr_capture._MAPPED_SUBRESOURCE) == 16
    assert ctypes.sizeof(hdr_capture._OUTDUPL_FRAME_INFO) == 48
    assert ctypes.sizeof(hdr_capture._DXGI_OUTPUT_DESC1) == 152
    assert ctypes.sizeof(hdr_capture._SOURCE_DEVICE_NAME) == 84


def test_wstr_decodes_utf16_units_up_to_nul():
    """WCHAR 字段是固定宽度码位数组（不用 c_wchar，它在非 Windows 是 4 字节），
    读出统一过 _wstr：ASCII、中文、NUL 截断、全零空串。"""
    def buf(text, size=8):
        arr = (hdr_capture._WCHAR * size)(*[ord(c) for c in text])
        return arr

    assert hdr_capture._wstr(buf("A1")) == "A1"
    assert hdr_capture._wstr(buf("显示器")) == "显示器"
    assert hdr_capture._wstr((hdr_capture._WCHAR * 4)()) == ""
    arr = (hdr_capture._WCHAR * 6)(*[ord(c) for c in "AB"], 0, ord("C"))
    assert hdr_capture._wstr(arr) == "AB"


def test_com_pointer_normalisation_accepts_int_and_c_void_p():
    assert hdr_capture._ptr_value(None) == 0
    assert hdr_capture._ptr_value(0) == 0
    assert hdr_capture._ptr_value(1234) == 1234
    assert hdr_capture._ptr_value(ctypes.c_void_p(1234)) == 1234
    assert hdr_capture._ptr_value(ctypes.c_void_p(None)) == 0


def test_null_com_pointer_is_a_named_failure_not_a_ctypes_crash():
    """空指针要抛能读懂的错误：ctypes 自己那句 "NULL pointer access" 看不出所以然。"""
    with pytest.raises(hdr_capture._Unavailable):
        hdr_capture._com_call(0, 8, ctypes.c_long, [])


# ------------------------------------------------------------- hdr_state


def _patch_display_config(monkeypatch, *, advanced_value=0x3, white=3500, paths=("path",)):
    _patch_platform(monkeypatch)
    monkeypatch.setattr(hdr_capture, "_active_paths", lambda: list(paths))
    monkeypatch.setattr(hdr_capture, "_resolve_gdi_name", lambda screen, p: "\\\\.\\DISPLAY1")
    monkeypatch.setattr(hdr_capture, "_path_for_gdi_name",
                        lambda name, p: p[0] if p else None)
    monkeypatch.setattr(hdr_capture, "_advanced_color",
                        lambda path: None if advanced_value is None else SimpleNamespace(value=advanced_value))
    monkeypatch.setattr(hdr_capture, "_sdr_white_raw", lambda path: white)


def test_hdr_state_reports_enabled_and_the_sdr_white_scale(monkeypatch):
    """本机实测值：高级颜色开、SDRWhiteLevel=3500 ⇒ 系数 3.5（= 280 nits）。"""
    _patch_display_config(monkeypatch, advanced_value=0x3, white=3500)

    assert hdr_state("H27T22S") == (True, 3.5)


def test_hdr_state_accepts_a_qscreen(monkeypatch):
    _patch_display_config(monkeypatch)

    assert hdr_state(_fake_screen()) == (True, 3.5)


def test_hdr_state_is_off_when_advanced_color_is_not_enabled(monkeypatch):
    """``value`` 第 0 位是"支持"、第 1 位是"已启用"：只支持不算开。"""
    _patch_display_config(monkeypatch, advanced_value=0x1)

    assert hdr_state("H27T22S") == (False, 1.0)


def test_hdr_state_is_off_on_a_zero_white_level(monkeypatch):
    """白点为 0 会导致除零，按"没开 HDR"处理——不是拿 0 当系数。"""
    _patch_display_config(monkeypatch, white=0)

    assert hdr_state("H27T22S") == (False, 1.0)


def test_hdr_state_is_off_when_the_monitor_cannot_be_resolved(monkeypatch):
    _patch_display_config(monkeypatch, paths=())
    monkeypatch.setattr(hdr_capture, "_resolve_gdi_name", lambda screen, p: "")

    assert hdr_state("不存在的屏") == (False, 1.0)


def test_hdr_state_is_off_when_the_query_fails(monkeypatch):
    """DisplayConfig 抛异常也不许冒泡：按未启用处理，抓帧照走 GDI。"""
    _patch_platform(monkeypatch)

    def _boom():
        raise OSError("QueryDisplayConfig rc=87")

    monkeypatch.setattr(hdr_capture, "_active_paths", _boom)

    assert hdr_state(None) == (False, 1.0)


def test_hdr_state_is_off_on_a_non_windows_platform(monkeypatch):
    monkeypatch.setattr(hdr_capture, "_platform_ok", lambda: False)

    def _must_not_run():
        raise AssertionError("非 Windows 上不该碰 DisplayConfig")

    monkeypatch.setattr(hdr_capture, "_active_paths", _must_not_run)

    assert hdr_state(None) == (False, 1.0)


# ---------------------------------------------------------- grab_hdr_sdr


class _FakeSession:
    """替身会话：只认"给我一个 sRGB 数组/一次失败"这一件事。"""

    key = "\\\\.\\DISPLAY1"

    def __init__(self, rgb=None, error: Exception | None = None) -> None:
        self.rgb = rgb
        self.error = error
        self.scales: list[float] = []

    def grab_srgb8(self, sdr_white_scale: float):
        self.scales.append(sdr_white_scale)
        if self.error is not None:
            raise self.error
        return self.rgb


def _patch_pipeline(monkeypatch, session):
    _patch_platform(monkeypatch)
    monkeypatch.setattr(hdr_capture, "_active_paths", lambda: ["path"])
    monkeypatch.setattr(hdr_capture, "_read_hdr_state", lambda screen, paths: (True, 3.5))
    monkeypatch.setattr(hdr_capture, "_session_for", lambda screen, paths: session)
    return session


def test_grab_hdr_sdr_builds_a_raw_device_pixel_srgb_image(monkeypatch):
    """缓冲 → 换算 → QImage 的组装：格式 RGB888、dpr=1.0、标 sRGB、dpr 口径确定。"""
    source = fp16_scrgb_to_srgb8(
        _rgb8((0.0, 0.0, 0.0, 1.0), (3.5, 3.5, 3.5, 1.0), (1.0, 1.0, 1.0, 1.0)),
        3, 1, 24, 3.5)
    session = _patch_pipeline(monkeypatch, _FakeSession(source))

    image = grab_hdr_sdr("H27T22S")

    assert isinstance(image, QImage) and not image.isNull()
    assert (image.width(), image.height()) == (3, 1)
    assert image.format() == QImage.Format.Format_RGB888
    assert image.devicePixelRatio() == 1.0
    assert image.colorSpace().isValid()
    assert [image.pixelColor(x, 0).getRgb()[:3] for x in range(3)] == [
        (0, 0, 0), (255, 255, 255), (146, 146, 146)]
    assert session.scales == [3.5]        # 换算用的是读出来的白点系数


def test_grab_hdr_sdr_image_does_not_alias_the_source_buffer(monkeypatch):
    """结果图必须是自己的内存：源数组之后被改写也不许影响它（QImage 不接管
    外部缓冲，直接拿临时缓冲建图会指向野内存）。"""
    source = np.full((2, 2, 3), 200, dtype=np.uint8)
    _patch_pipeline(monkeypatch, _FakeSession(source))

    image = grab_hdr_sdr("H27T22S")
    source[:] = 0

    assert image.pixelColor(0, 0).getRgb()[0] == 200


def test_grab_hdr_sdr_returns_none_when_hdr_is_off(monkeypatch):
    _patch_platform(monkeypatch)
    monkeypatch.setattr(hdr_capture, "_active_paths", lambda: ["path"])
    monkeypatch.setattr(hdr_capture, "_read_hdr_state", lambda screen, paths: (False, 1.0))
    monkeypatch.setattr(hdr_capture, "_session_for",
                        lambda screen, paths: pytest.fail("没开 HDR 不该建会话"))

    assert grab_hdr_sdr("H27T22S") is None


def test_grab_hdr_sdr_returns_none_when_the_session_is_unavailable(monkeypatch):
    _patch_pipeline(monkeypatch, None)

    assert grab_hdr_sdr("H27T22S") is None


def test_grab_hdr_sdr_returns_none_and_backs_off_when_no_frame_arrives(monkeypatch):
    session = _patch_pipeline(monkeypatch, _FakeSession(None))

    assert grab_hdr_sdr("H27T22S") is None
    assert hdr_capture._FAILED_UNTIL[session.key] > 0
    assert session.key not in hdr_capture._SESSIONS


def test_grab_hdr_sdr_swallows_internal_errors(monkeypatch):
    """通道内部抛的任何异常都不许到调用方：返回 None、丢掉缓存会话、退避。"""
    session = _patch_pipeline(monkeypatch, _FakeSession(error=RuntimeError("设备被拔了")))

    assert grab_hdr_sdr("H27T22S") is None
    assert session.key in hdr_capture._FAILED_UNTIL


@pytest.mark.parametrize("negotiated, expected_ttl", [
    (True, hdr_capture._FORMAT_VERDICT_TTL_S),
    (False, hdr_capture._NEGATIVE_TTL_S),
], ids=["已协商→判定级退避", "未协商→按抖动退避"])
def test_format_mismatch_backoff_follows_whether_the_format_was_negotiated(
        monkeypatch, negotiated, expected_ttl):
    """帧不是 FP16 的退避分两档：

    协商过（``DuplicateOutput1`` 成功）还拿到 BGRA8 = "这个桌面模式给不出 HDR 面"，
    短期重试不会变，退避长；没协商上只是"协商通道这次不给用"——本机实测它反复
    无常，按抖动退避，别让一次 OS 抽风把用户关在 GDI 里十几分钟。
    """
    session = _patch_pipeline(
        monkeypatch,
        _FakeSession(error=hdr_capture._FormatMismatch("format=87", negotiated=negotiated)))

    before = hdr_capture.time.monotonic()
    assert grab_hdr_sdr("H27T22S") is None

    window = hdr_capture._FAILED_UNTIL[session.key] - before
    assert window >= expected_ttl - 1
    assert hdr_capture._FORMAT_VERDICT_TTL_S > hdr_capture._NEGATIVE_TTL_S


def test_backoff_skips_a_new_session_attempt(monkeypatch):
    """退避期内不再建设备：调用方拿到的还是 None，但一次查询都不做。"""
    _patch_platform(monkeypatch)
    monkeypatch.setattr(hdr_capture, "_active_paths", lambda: ["path"])
    monkeypatch.setattr(hdr_capture, "_resolve_gdi_name", lambda screen, p: "\\\\.\\DISPLAY1")
    monkeypatch.setattr(hdr_capture, "_create_session",
                        lambda gdi: pytest.fail("退避期内不该尝试建会话"))
    hdr_capture._FAILED_UNTIL["\\\\.\\DISPLAY1"] = hdr_capture.time.monotonic() + 60

    assert hdr_capture._session_for("H27T22S", ["path"]) is None


def test_session_cache_is_reused_while_still_valid(monkeypatch):
    """连续两次截图复用同一个会话（建设备是贵的那一步），元数据变了才重建。"""
    _patch_platform(monkeypatch)
    monkeypatch.setattr(hdr_capture, "_active_paths", lambda: ["path"])
    monkeypatch.setattr(hdr_capture, "_resolve_gdi_name", lambda screen, p: "\\\\.\\DISPLAY1")
    created = []

    class _CachedSession:
        key = "\\\\.\\DISPLAY1"

        def __init__(self, reusable=True):
            self.reusable = reusable

        def is_reusable(self):
            return self.reusable

        def release(self):
            pass

    def _create(gdi):
        created.append(1)
        return _CachedSession()

    monkeypatch.setattr(hdr_capture, "_create_session", _create)

    first = hdr_capture._session_for("H27T22S", ["path"])
    second = hdr_capture._session_for("H27T22S", ["path"])

    assert first is second
    assert len(created) == 1

    first.reusable = False           # 设备丢了/HDR 被关：旧会话作废，重建一次
    third = hdr_capture._session_for("H27T22S", ["path"])
    assert third is not first
    assert len(created) == 2


def test_release_cached_sessions_returns_the_gpu_resources():
    """显式放掉缓存会话：会话本身被 release，退避表也清空（"这片屏不抓了"的出口）。"""
    released = []

    class _Session:
        key = "\\\\.\\DISPLAY1"

        def release(self):
            released.append(self.key)

    hdr_capture._SESSIONS["\\\\.\\DISPLAY1"] = _Session()
    hdr_capture._FAILED_UNTIL["\\\\.\\DISPLAY1"] = 12345.0

    hdr_capture.release_cached_sessions()

    assert released == ["\\\\.\\DISPLAY1"]
    assert hdr_capture._SESSIONS == {}
    assert hdr_capture._FAILED_UNTIL == {}


def test_dxgi_reason_names_the_two_actionable_failures():
    """"别的应用占满复制会话"与"会话失效"要能和别的码区分开——处置完全不同。"""
    assert "占满" in hdr_capture._dxgi_reason(hdr_capture.DXGI_ERROR_NOT_CURRENTLY_AVAILABLE)
    assert "失效" in hdr_capture._dxgi_reason(hdr_capture.DXGI_ERROR_ACCESS_LOST)
    assert hdr_capture._dxgi_reason(0x887A0004) == "hr=0x887a0004"


def test_grab_hdr_sdr_is_disabled_by_the_escape_hatch(monkeypatch):
    monkeypatch.setenv(DISABLE_ENV, "1")
    monkeypatch.setattr(hdr_capture, "_platform_ok", lambda: True)
    monkeypatch.setattr(hdr_capture, "_active_paths",
                        lambda: pytest.fail("逃生门开着时不该读任何显示状态"))

    assert grab_hdr_sdr("H27T22S") is None


@pytest.mark.parametrize("value, expected", [
    ("", False), ("0", False), ("false", False), ("no", False), ("off", False),
    ("1", True), ("true", True), ("yes", True), ("ON", True), (" 1 ", True),
])
def test_escape_hatch_value_semantics(monkeypatch, value, expected):
    monkeypatch.setenv(DISABLE_ENV, value)

    assert hdr_capture_disabled() is expected


def test_grab_hdr_sdr_returns_none_on_a_non_windows_platform(monkeypatch):
    monkeypatch.setattr(hdr_capture, "_platform_ok", lambda: False)

    assert grab_hdr_sdr(None) is None


# ------------------------------------------------- 会话内部：全零首帧


class _RiggedSession(hdr_capture._Session):
    """把"抓一帧"换成从列表里取，专门验全零首帧的重试策略。"""

    def __init__(self, frames) -> None:
        super().__init__(key="k", output=0, device=0, context=0)
        self._frames = list(frames)
        self.calls: list[tuple[int, int]] = []

    def _grab_rgb8(self, timeout_ms, poll_ms, sdr_white_scale):
        self.calls.append((timeout_ms, poll_ms))
        return self._frames.pop(0) if self._frames else None

    def _restart_duplication(self):
        return True


def test_all_zero_frame_is_retried_because_the_fresh_surface_is_uninitialised():
    """刚开的复制会话会先给一张未初始化的全零 FP16 面（本机实测）：再等一帧。"""
    black = np.zeros((2, 2, 3), dtype=np.uint8)
    real = np.full((2, 2, 3), 255, dtype=np.uint8)
    session = _RiggedSession([black, real])

    out = session.grab_srgb8(3.5)

    assert out is real
    assert len(session.calls) == 2


def test_all_zero_frames_twice_fall_back_instead_of_returning_a_black_shot():
    """连续全零就当这条通道这次拿不到图——绝不能把黑屏当截图交出去。"""
    black = np.zeros((2, 2, 3), dtype=np.uint8)
    session = _RiggedSession([black, black, np.full((2, 2, 3), 255, dtype=np.uint8)])

    assert session.grab_srgb8(3.5) is None
    assert len(session.calls) == 2


def test_a_black_frame_only_after_a_valid_first_frame_is_still_retried():
    """顺序反过来也一样：全零就是不可信，与它是第几帧无关。"""
    real = np.full((2, 2, 3), 7, dtype=np.uint8)
    session = _RiggedSession([real])

    assert session.grab_srgb8(3.5) is real
    assert len(session.calls) == 1


# ----------------------------------------------- pixels.grab_screen_image 接线


def _patch_pixels_hdr(monkeypatch, *, state=(True, 3.5), hdr_result=None, hdr_error=None,
                      state_error=None):
    calls = {"hdr": 0, "state": 0}

    def _state(screen):
        calls["state"] += 1
        if state_error is not None:
            raise state_error
        return state

    def _grab(screen):
        calls["hdr"] += 1
        if hdr_error is not None:
            raise hdr_error
        return hdr_result

    monkeypatch.setattr(pixels, "hdr_state", _state)
    monkeypatch.setattr(pixels, "grab_hdr_sdr", _grab)
    return calls


def test_grab_screen_image_uses_the_gdi_path_when_hdr_is_off(monkeypatch):
    calls = _patch_pixels_hdr(monkeypatch, state=(False, 1.0))
    screen = _fake_screen()
    screen.calls = 0

    image = pixels.grab_screen_image(screen)

    assert calls["state"] == 1 and calls["hdr"] == 0
    assert screen.calls == 1
    assert image.devicePixelRatio() == 1.0


def test_grab_screen_image_prefers_the_hdr_capture(monkeypatch):
    hdr_image = QImage(4, 3, QImage.Format.Format_RGB888)
    hdr_image.fill(0)
    hdr_image.setDevicePixelRatio(1.0)
    calls = _patch_pixels_hdr(monkeypatch, hdr_result=hdr_image)
    screen = _fake_screen()
    screen.calls = 0

    image = pixels.grab_screen_image(screen)

    assert calls["hdr"] == 1
    assert screen.calls == 0                      # 拿到 HDR 图就不再抓 GDI
    assert (image.width(), image.height()) == (4, 3)


def test_grab_screen_image_falls_back_when_the_hdr_channel_returns_none(monkeypatch):
    calls = _patch_pixels_hdr(monkeypatch, hdr_result=None)
    screen = _fake_screen()
    screen.calls = 0

    image = pixels.grab_screen_image(screen)

    assert calls["hdr"] == 1
    assert screen.calls == 1
    assert not image.isNull()


def test_grab_screen_image_survives_an_hdr_channel_exception(monkeypatch):
    _patch_pixels_hdr(monkeypatch, hdr_error=OSError("DXGI 炸了"))
    screen = _fake_screen()
    screen.calls = 0

    image = pixels.grab_screen_image(screen)

    assert screen.calls == 1
    assert not image.isNull()


def test_grab_screen_image_survives_a_broken_hdr_state_query(monkeypatch):
    _patch_pixels_hdr(monkeypatch, state_error=RuntimeError("DisplayConfig 挂了"))
    screen = _fake_screen()
    screen.calls = 0

    image = pixels.grab_screen_image(screen)

    assert screen.calls == 1
    assert not image.isNull()


def test_grab_screen_image_escape_hatch_skips_the_hdr_channel_entirely(monkeypatch):
    monkeypatch.setenv(DISABLE_ENV, "1")
    calls = _patch_pixels_hdr(monkeypatch, hdr_result=QImage(2, 2, QImage.Format.Format_RGB888))
    screen = _fake_screen()
    screen.calls = 0

    pixels.grab_screen_image(screen)

    assert calls["state"] == 0 and calls["hdr"] == 0
    assert screen.calls == 1


def test_grab_screen_image_fake_screen_without_geometry_still_works(monkeypatch):
    """没有 geometry/name 的替身（老测试就是这种）不能被 HDR 通道搞崩。"""
    monkeypatch.setattr(hdr_capture, "_platform_ok", lambda: True)
    monkeypatch.setattr(hdr_capture, "_active_paths", lambda: [])
    screen = _fake_screen(grabbed=QPixmap(8, 8))

    assert not pixels.grab_screen_image(screen).isNull()


def test_cached_sessions_are_released_after_idle(qapp, monkeypatch):
    """最后一次抓帧 30s 后，缓存的 D3D11 设备/会话整组还回系统（闲置回收器）。"""
    import time as _time
    import pet.screen_capture.hdr_capture as hdr

    released = []

    class _FakeSession:
        def release(self):
            released.append(True)

    monkeypatch.setattr(hdr, "_IDLE_RELEASE_S", 0.05)   # 测试预算内的短窗
    hdr._SESSIONS["TEST\DISPLAY"] = _FakeSession()
    hdr._arm_idle_release()

    deadline = _time.monotonic() + 5.0
    while not released and _time.monotonic() < deadline:
        _time.sleep(0.02)
    assert released, "闲置回收器没有在窗口期放掉缓存会话"
    assert hdr._SESSIONS == {}
    hdr._FAILED_UNTIL.clear()
