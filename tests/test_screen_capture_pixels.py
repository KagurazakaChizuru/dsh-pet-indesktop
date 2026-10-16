# -*- coding: utf-8 -*-
"""「快速识屏」P0 像素链路：冻结帧抓取 / 选区裁剪 / sRGB 8-bit 统一（offscreen）。

验收门槛是**"截图与肉眼色彩一致"**，所以这里的断言不只看格式：

- 裁剪必须用**设备像素**换算（分数 DPR 下逻辑坐标 × DPR），产出图统一
  ``devicePixelRatio == 1.0``——后续 OCR 吃的是真实像素，不留缩放歧义；
- ``to_srgb8`` 真的**跑色彩变换**（线性 0.5 → sRGB 188，而非直接截断的
  128）；只换格式不换色彩空间，正是 HDR 屏上"截出来发灰/发闷"的成因。
"""

from __future__ import annotations

import struct

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QColorSpace, QImage, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pet.screen_capture.pixels import (  # noqa: E402
    SRGB8_FORMAT,
    crop_selection,
    grab_screen_image,
    to_srgb8,
)
from pet.screen_capture.session import SelectionRect, normalize_drag  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _frame(width: int, height: int, *, dpr: float = 1.0) -> QImage:
    """造一张带方位标记的底图：左上红、右上绿、左下蓝、右下白。"""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(0, 0, 0))
    half_w, half_h = width // 2, height // 2
    painter = QPainter(image)
    painter.fillRect(0, 0, half_w, half_h, QColor(255, 0, 0))
    painter.fillRect(half_w, 0, width - half_w, half_h, QColor(0, 255, 0))
    painter.fillRect(0, half_h, half_w, height - half_h, QColor(0, 0, 255))
    painter.fillRect(half_w, half_h, width - half_w, height - half_h, QColor(255, 255, 255))
    painter.end()
    image.setDevicePixelRatio(dpr)
    return image


class _FakeScreen:
    """``QScreen.grabWindow`` 真机返回 **QPixmap**（探针实测），替身照抄这个事实。"""

    def __init__(self, grabbed) -> None:
        self._grabbed = grabbed
        self.calls = 0

    def grabWindow(self, window=0, *args):  # noqa: N802 - 对齐 Qt 命名
        self.calls += 1
        return self._grabbed


# ---------------------------------------------------------------- 冻结帧抓取


def test_grab_screen_image_returns_device_pixels_with_dpr_one():
    """Qt 的高 DPI 约定是"设备像素 + dpr 标记"；本模块统一成 dpr=1.0 的裸像素。"""
    screen = _FakeScreen(QPixmap.fromImage(_frame(40, 40, dpr=2.0)))

    image = grab_screen_image(screen)

    assert screen.calls == 1
    assert isinstance(image, QImage)
    assert image.width() == 40 and image.height() == 40
    assert image.devicePixelRatio() == 1.0


def test_grab_screen_image_accepts_qimage_returns():
    """替身 / 其它平台可能直接给 QImage，两种返回都要能用。"""
    screen = _FakeScreen(_frame(40, 40, dpr=1.5))

    image = grab_screen_image(screen)

    assert isinstance(image, QImage)
    assert image.devicePixelRatio() == 1.0


def test_grab_screen_image_tolerates_screen_without_grabwindow():
    class _NullScreen:
        pass

    assert grab_screen_image(_NullScreen()).isNull()


def test_grab_screen_image_rejects_non_image_result():
    class _WeirdScreen:
        def grabWindow(self, window=0, *args):  # noqa: N802
            return "not an image"

    assert grab_screen_image(_WeirdScreen()).isNull()


def test_grab_screen_image_tolerates_null_pixmap():
    assert grab_screen_image(_FakeScreen(QPixmap())).isNull()


# ------------------------------------------------------------------ 选区裁剪


def test_crop_selection_uses_logical_coordinates_at_dpr_one():
    frame = _frame(40, 40)

    crop = crop_selection(frame, SelectionRect(2, 3, 5, 6), 1.0)

    assert (crop.width(), crop.height()) == (5, 6)
    assert crop.pixelColor(0, 0).getRgb() == (255, 0, 0, 255)   # 左上象限 ⇒ 红


def test_crop_selection_scales_with_integer_dpr():
    frame = _frame(40, 40, dpr=2.0)  # 逻辑屏幕 20×20

    crop = crop_selection(frame, SelectionRect(5, 5, 10, 10), 2.0)

    assert (crop.width(), crop.height()) == (20, 20)


def test_crop_selection_rounds_outwards_at_fractional_dpr():
    """1.5 倍：左/上 floor、右/下 ceil，设备矩形包住逻辑选区。"""
    frame = _frame(60, 60, dpr=1.5)

    crop = crop_selection(frame, SelectionRect(1, 1, 3, 1), 1.5)

    assert (crop.width(), crop.height()) == SelectionRect(1, 1, 3, 1).device_rect(1.5)[2:]


def test_crop_selection_keeps_the_right_quadrant():
    frame = _frame(40, 40)  # 设备 20 像素处为象限分界

    crop = crop_selection(frame, SelectionRect(20, 20, 20, 20), 1.0)

    assert crop.pixelColor(0, 0).getRgb() == (255, 255, 255, 255)


def test_crop_selection_resets_device_pixel_ratio():
    frame = _frame(40, 40, dpr=2.0)

    crop = crop_selection(frame, SelectionRect(0, 0, 10, 10), 2.0)

    assert crop.devicePixelRatio() == 1.0


def test_crop_selection_clamps_edge_drag_to_frame():
    """拖到屏幕边缘时 dpr 取整会溢出 1 像素：按底图边界钳制，不当成失败。

    真机场景：150% 缩放的 2560×1440 屏，Qt 报的逻辑宽是 1707，1707×1.5=2560.5
    ⇒ 右边界取整后越界 1 像素。这里用等价的 61 设备像素 / 1.5 复现。
    """
    frame = _frame(61, 61, dpr=1.5)
    selection = normalize_drag(20, 20, 41, 41, bounds=(41, 41))
    left, top, width, height = selection.device_rect(1.5)
    assert left + width > frame.width()  # 先证明取整真的越界了

    crop = crop_selection(frame, selection, 1.5)

    assert not crop.isNull()
    assert (crop.width(), crop.height()) == (frame.width() - left, frame.height() - top)


def test_crop_selection_rejects_out_of_frame_selection():
    frame = _frame(40, 40)
    with pytest.raises(ValueError):
        crop_selection(frame, SelectionRect(100, 100, 10, 10), 1.0)


def test_crop_selection_rejects_empty_selection():
    frame = _frame(40, 40)
    with pytest.raises(ValueError):
        crop_selection(frame, SelectionRect(1, 1, 0, 0), 1.0)


def test_crop_selection_rejects_null_frame():
    with pytest.raises(ValueError):
        crop_selection(QImage(), SelectionRect(0, 0, 1, 1), 1.0)


def test_crop_selection_requires_positive_dpr():
    with pytest.raises(ValueError):
        crop_selection(_frame(40, 40), SelectionRect(0, 0, 1, 1), 0.0)


# ------------------------------------------------------- sRGB 8-bit 统一


def _linear_gray(value: int, size: int = 4) -> QImage:
    # QImage(bytes, ...) 不拷贝缓冲区：必须把 bytes 挂在图对象上一起存活，
    # 否则缓冲区释放后 QImage 指向野内存（表现为之后 GC 时原生崩溃）。
    raw = struct.pack("<4H", value, value, value, 0xFFFF) * (size * size)
    image = QImage(raw, size, size, QImage.Format.Format_RGBX64)
    image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgbLinear))
    image._keep_alive = raw
    return image


def test_to_srgb8_applies_the_color_transform_not_just_the_format():
    """线性 0.5 → sRGB 188；直接截断会得到 128（HDR 下就是"发灰"）。"""
    out = to_srgb8(_linear_gray(32768))

    assert out.format() == SRGB8_FORMAT
    assert out.colorSpace() == QColorSpace(QColorSpace.NamedColorSpace.SRgb)
    assert out.pixelColor(0, 0).red() == 188


def test_to_srgb8_keeps_unmanaged_images_untouched_in_value():
    plain = QImage(2, 2, QImage.Format.Format_RGB32)
    plain.fill(QColor(10, 20, 30))

    out = to_srgb8(plain)

    assert out.format() == QImage.Format.Format_RGB888
    assert out.pixelColor(0, 0).getRgb() == (10, 20, 30, 255)


def test_to_srgb8_is_idempotent():
    once = to_srgb8(_linear_gray(32768))
    twice = to_srgb8(once)

    assert twice.pixelColor(0, 0).getRgb() == once.pixelColor(0, 0).getRgb()


def test_to_srgb8_passes_through_null_image():
    assert to_srgb8(QImage()).isNull()


def test_crop_then_to_srgb8_end_to_end():
    frame = _frame(60, 60, dpr=1.5)

    crop = to_srgb8(crop_selection(frame, SelectionRect(4, 4, 8, 8), 1.5))

    assert crop.format() == SRGB8_FORMAT
    assert crop.devicePixelRatio() == 1.0
    assert crop.pixelColor(0, 0).getRgb() == (255, 0, 0, 255)
