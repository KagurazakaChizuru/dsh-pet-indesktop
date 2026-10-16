# -*- coding: utf-8 -*-
"""「快速识屏」本地 OCR 契约（offscreen 可跑）。

切片 5 起一次识别 = 一个识别子进程（``pet/screen_capture/ocr_worker.py``；源码态
``python -m pet.screen_capture.ocr_worker``，冻结态 ``<exe> --ocr-worker``）：像素从
stdin 管道进、结果从 stdout 一行 JSON 出、日志走 stderr，认完即退出。**进程退出是
"内存用完真归零"的唯一实现**——进程内 ``unload()`` 实测只回吐约 30 MB / 108 MB。

这一层要钉死五件事：

1. **协议**：帧的编解码、短读、坏魔数、超长长度头；
2. **像素**：``QImage`` → PNG 的通道数与色彩序（工作端拿到的必须是 3 通道 BGR）；
3. **退出码语义**：0 = 有文字、3 = 没文字（**不是故障**）、≥4 = 各类故障，而
   Windows 强杀落下的 1/2 永远不许被当成成功——那是"取消/超时看起来像空结果"的坑；
4. **子进程的一生**：超时杀进程并报人话、释放中止在跑的进程、跑完不留孤儿；
5. **真实端到端**：真工作端认出程序画出来的已知文字（含中文），空图返回空串，
   且每次调用都是一个**新的**进程（用完就丢）。

工作端的替身一律是**真的子进程**（``sys.executable -c ...``）：协议、管道、kill、
回收全部走真实系统调用。把 ``Popen`` 换成假对象等于把这一片最该验的东西验掉了。

字体说明（真机实测）：``QT_QPA_PLATFORM=offscreen`` 下 Qt 的字体库**是空的**
（Windows 上 ``QFontDatabase.families()`` 返回 0 个家族），直接画字只会得到一
串豆腐块。所以测试图必须先用 ``addApplicationFont`` 显式注册一个真实字体
文件；注册不到就跳过（那是环境缺字体，不是被测代码的问题）。
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pet.screen_capture import ocr, ocr_worker  # noqa: E402
from pet.screen_capture.ocr import (  # noqa: E402
    OcrEngine,
    OcrError,
    OcrLoadError,
    OcrModelMissingError,
    OcrRecognitionError,
    OcrUnavailableError,
    TextBlock,
    reading_order,
)

REPO = Path(__file__).resolve().parents[1]

#: 拉丁字体候选（三端常见路径）。取第一个能注册成功的。
_LATIN_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)

#: 中文字体候选。CI 的 Linux runner 装了 fonts-noto-cjk，Windows 有微软雅黑。
_CJK_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
)

_LATIN_LINES = ("hello world 12345", "quick brown fox", "deepseek pet 2026")


@pytest.fixture(scope="module", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


def _register_font(candidates) -> str | None:
    """注册第一个存在的字体文件，返回家族名；一个都没有返回 None。"""
    for path in candidates:
        if not Path(path).is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id == -1:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            return families[0]
    return None


@pytest.fixture(scope="module")
def latin_family():
    family = _register_font(_LATIN_FONT_CANDIDATES)
    if family is None:
        pytest.skip("本机没有可注册的拉丁字体文件，画不出测试图")
    return family


@pytest.fixture(scope="module")
def cjk_family():
    family = _register_font(_CJK_FONT_CANDIDATES)
    if family is None:
        pytest.skip("本机没有可注册的中文字体文件，画不出中文测试图")
    return family


def _screenshot(family: str | None, lines=_LATIN_LINES, *, width=800, height=400,
                pixel_size=30) -> QImage:
    """按像素画一张"像截图"的白底黑字图（行距固定，方便断言阅读顺序）。"""
    image = QImage(width, height, QImage.Format.Format_RGB888)
    image.fill(QColor(255, 255, 255))
    painter = QPainter(image)
    painter.setPen(QColor(0, 0, 0))
    font = QFont(family) if family else QFont()
    font.setPixelSize(pixel_size)
    painter.setFont(font)
    for index, line in enumerate(lines):
        painter.drawText(30, 60 + index * 80, line)
    painter.end()
    return image


def _blank(width=64, height=32) -> QImage:
    image = QImage(width, height, QImage.Format.Format_RGB888)
    image.fill(QColor(255, 255, 255))
    return image


# ------------------------------------------------------- 假工作端（真子进程）


def _fake(body: str) -> list[str]:
    """把一段 Python 源码当成假工作端的命令行（``python -c``）。"""
    return [sys.executable, "-c", body]


_FAKE_HEAD = "import json, os, sys\nsys.stdin.buffer.read()\n"


def _record(record: dict) -> str:
    """在工作端 stderr 上写一条本进程自己的结构化记录（宿主按前缀认）。"""
    line = ocr_worker.STDERR_PREFIX + json.dumps(record, ensure_ascii=False)
    return f"os.write(2, ({line!r} + chr(10)).encode('utf-8'))\n"


def _results(*blocks: dict) -> str:
    payload = json.dumps({"blocks": list(blocks)})
    return f"os.write(1, ({payload!r} + chr(10)).encode('utf-8'))\n"


_BLOCK = {"text": "hello world", "score": 0.9, "box": [[1, 2], [30, 2], [30, 12], [1, 12]]}

FAKE_TEXT = _FAKE_HEAD + _results(_BLOCK) + "sys.exit(0)\n"
FAKE_NO_TEXT = _FAKE_HEAD + _results() + f"sys.exit({ocr_worker.EXIT_NO_TEXT})\n"
FAKE_LIES = _FAKE_HEAD + _results(_BLOCK) + f"sys.exit({ocr_worker.EXIT_NO_TEXT})\n"
FAKE_GARBAGE = _FAKE_HEAD + "os.write(1, b'not json at all' + chr(10).encode())\nsys.exit(0)\n"
FAKE_SILENT_OK = _FAKE_HEAD + "sys.exit(0)\n"
FAKE_MODEL_MISSING = (
    _FAKE_HEAD
    + 'os.write(2, b"noise from a native library\\n")\n'
    + _record({"error": "缺少本地 OCR 模型文件 x.onnx（找过的目录：/tmp）"})
    + f"sys.exit({ocr_worker.EXIT_MODEL_MISSING})\n"
)
FAKE_UNAVAILABLE = _FAKE_HEAD + f"sys.exit({ocr_worker.EXIT_UNAVAILABLE})\n"
FAKE_LOAD_FAILED = _FAKE_HEAD + f"sys.exit({ocr_worker.EXIT_LOAD_FAILED})\n"
FAKE_REC_FAILED = _FAKE_HEAD + f"sys.exit({ocr_worker.EXIT_RECOGNIZE_FAILED})\n"
#: 模拟崩溃统一用 42：一个三端都原样存活的"不属于任何语义"的异常码。
#: 不能用访问违例码 3221225477（0xC0000005）——POSIX 只留低 8 位（0x05，正好撞
#: EXIT_UNAVAILABLE 的语义），Windows  runner 上还有符号/截断差异；这些平台特性
#: 的格式化由 interpret 的参数化用例（3221225477 / -1073741819）在纯函数层钉死，
#: 子进程层只验"未知异常码会被点名+按 stage 归类"这件事本身。
#: 崩溃前一条 stage 记录都没有：宿主只能说"启动或读图那一段"。
FAKE_CRASH_NO_STAGE = _FAKE_HEAD + "sys.exit(42)\n"
#: 已经读过帧（stage=frame-read），说明崩在模型加载那一段。
FAKE_CRASH_LOADING = _FAKE_HEAD + _record({"stage": "frame-read"}) + "sys.exit(42)\n"
#: 崩溃前已经写过 stage=loaded：引擎起来了，崩在识别里。
FAKE_CRASH_LATE = _FAKE_HEAD + _record({"stage": "loaded"}) + "sys.exit(42)\n"
#: Windows 上 TerminateProcess 的落码就是 1：绝不能被当成"图里没有文字"。
FAKE_KILLED = _FAKE_HEAD + "sys.exit(1)\n"
FAKE_HANG = _FAKE_HEAD + "import time\ntime.sleep(120)\n"
#: 把收到的帧解析一遍、把结论当成识别结果报回来（用来断言**管道里只有一个帧**）。
FAKE_FRAME_CHECK = (
    "import json, os, struct, sys\n"
    "data = sys.stdin.buffer.read()\n"
    "magic = data[:7] == b'DSHOCR1'\n"
    "size = struct.unpack('>I', data[7:11])[0] if len(data) >= 11 else -1\n"
    "text = ('magic=%s size=%d payload=%d' % (magic, size, len(data) - 11))\n"
    "block = {'text': text, 'score': 1.0, 'box': [[0, 0], [1, 0], [1, 1], [0, 1]]}\n"
    "os.write(1, (json.dumps({'blocks': [block]}) + chr(10)).encode('utf-8'))\n"
    "sys.exit(0)\n"
)


class _SpawnLog:
    """记录 ``OcrEngine`` 起过的每个子进程（超时/孤儿断言要看它）。"""

    def __init__(self) -> None:
        self.processes: list = []

    def __call__(self, argv):
        process = ocr.spawn_worker(argv)
        self.processes.append(process)
        return process


def _engine(body: str, *, timeout=ocr.DEFAULT_RECOGNIZE_TIMEOUT) -> tuple[OcrEngine, _SpawnLog]:
    log = _SpawnLog()
    return OcrEngine(command=lambda: _fake(body), spawn=log, timeout=timeout), log


def _pid_alive(pid: int) -> bool:
    """进程是否还活着（**跨进程**判据，不看我们手里的 Popen 句柄）。"""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, wintypes.DWORD(pid))  # QUERY_LIMITED
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_for(predicate, timeout=10.0, interval=0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ------------------------------------------------------------------ 模型路径


def test_bundled_model_dir_points_at_repo_resources():
    directory = ocr.bundled_model_dir()

    assert directory.name == "rapidocr_models"
    assert directory.parent.name == "resources"


def test_bundled_model_dir_honours_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(ocr.OCR_MODEL_DIR_ENV, str(tmp_path))

    assert ocr.bundled_model_dir() == tmp_path


def test_model_problem_names_the_missing_file(tmp_path):
    problem = ocr.model_problem(tmp_path)

    assert problem, "空目录必须判定为模型缺失"
    assert str(tmp_path) in problem, "人话原因里要带上找过的路径，用户才知道去哪补"


def test_model_problem_is_empty_when_all_files_present(tmp_path):
    for name in ocr.MODEL_FILES.values():
        (tmp_path / name).write_bytes(b"")

    assert ocr.model_problem(tmp_path) == ""


def test_resolve_model_dir_finds_a_usable_directory():
    directory = ocr.resolve_model_dir()

    assert ocr.model_problem(directory) == "", (
        f"既没找到随包模型（{ocr.bundled_model_dir()}）也没找到已装 wheel 自带的模型"
    )


def test_resolve_model_dir_prefers_an_explicit_directory(tmp_path):
    assert ocr.resolve_model_dir(tmp_path) == tmp_path


def test_explicit_model_dir_never_falls_back_to_the_wheel(monkeypatch, tmp_path):
    """显式指定（含环境变量）就是用户要的那一份，不许静默回退到另一批模型。

    回退只是给"干净 clone 里随包模型还没落盘"这种开发场景的；一个用户明确换过的
    目录要是悄悄被换回 wheel 里那批，识别结果会变而用户以为是同一批模型——
    "同名不同内容"正是构建期 sha256 门专门防的那件事。
    """
    monkeypatch.setenv(ocr.OCR_MODEL_DIR_ENV, str(tmp_path))

    assert ocr.resolve_model_dir() == tmp_path
    assert ocr.model_problem(ocr.resolve_model_dir()), "空目录就该判定为缺失，而不是换个目录继续"


# ------------------------------------------------------------------ 管道协议


def test_frame_bytes_prefixes_magic_and_big_endian_length():
    frame = ocr.frame_bytes(b"\x89PNG-fake")

    assert frame[:len(ocr_worker.MAGIC)] == ocr_worker.MAGIC
    assert frame[len(ocr_worker.MAGIC):len(ocr_worker.MAGIC) + 4] == b"\x00\x00\x00\x09"
    assert frame.endswith(b"\x89PNG-fake")


def test_read_frame_round_trips_a_frame():
    payload = b"\x89PNG" + bytes(range(256))

    assert ocr_worker.read_frame(io.BytesIO(ocr.frame_bytes(payload))) == payload


def test_read_exact_survives_short_reads():
    """``read(n)`` 在管道上可能短读；把短读当读完，后面全错位。"""

    class _Drip(io.BytesIO):
        def read(self, size=-1):
            return super().read(1 if size != 4 else 4)

    assert ocr_worker.read_exact(_Drip(b"abcdefgh"), 8) == b"abcdefgh"


def test_read_frame_rejects_a_bad_magic():
    with pytest.raises(ocr_worker.WorkerError) as excinfo:
        ocr_worker.read_frame(io.BytesIO(b"NOTOURS!" + b"\x00\x00\x00\x01x"))

    assert excinfo.value.code == ocr_worker.EXIT_PROTOCOL
    assert "帧头" in str(excinfo.value)


def test_read_frame_rejects_a_truncated_payload():
    frame = ocr_worker.MAGIC + b"\x00\x00\x00\x10" + b"short"

    with pytest.raises(ocr_worker.WorkerError) as excinfo:
        ocr_worker.read_frame(io.BytesIO(frame))

    assert excinfo.value.code == ocr_worker.EXIT_PROTOCOL
    assert "不完整" in str(excinfo.value)


def test_read_frame_rejects_an_oversize_length_header():
    """长度头被写坏时不许照它去分配内存（64 MiB 上限，超了立刻判协议错）。"""
    frame = ocr_worker.MAGIC + (ocr_worker.MAX_FRAME_BYTES + 1).to_bytes(4, "big")

    with pytest.raises(ocr_worker.WorkerError) as excinfo:
        ocr_worker.read_frame(io.BytesIO(frame))

    assert excinfo.value.code == ocr_worker.EXIT_PROTOCOL
    assert "上限" in str(excinfo.value)


def test_read_frame_rejects_an_empty_frame():
    with pytest.raises(ocr_worker.WorkerError) as excinfo:
        ocr_worker.read_frame(io.BytesIO(ocr_worker.MAGIC + b"\x00\x00\x00\x00"))

    assert excinfo.value.code == ocr_worker.EXIT_PROTOCOL


def test_worker_stderr_records_are_parsed_and_noise_is_ignored():
    stderr = (
        b"onoise: onnxruntime says hi\n"
        + (ocr_worker.STDERR_PREFIX + '{"stage": "loaded"}\n').encode()
        + b"more noise\n"
        + (ocr_worker.STDERR_PREFIX + '{"error": "模型没了"}\n').encode()
    )

    assert ocr.parse_stderr(stderr) == ("loaded", "模型没了")
    assert ocr.parse_stderr(b"only noise\n") == ("", "")


# ---------------------------------------------------------------- 像素 → PNG


def _png_colour_type(png: bytes) -> int:
    """PNG IHDR 的色彩类型字节（2 = truecolor RGB，6 = RGBA）。"""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert png[12:16] == b"IHDR"
    return png[25]


def test_encode_png_is_a_three_channel_png():
    png = ocr.encode_png(_blank(13, 7))

    assert _png_colour_type(png) == 2, "必须是不带 alpha 的 3 通道 PNG（解码端只要 BGR）"
    assert int.from_bytes(png[16:20], "big") == 13
    assert int.from_bytes(png[20:24], "big") == 7


def test_encode_png_strips_alpha_from_non_rgb888_input():
    image = QImage(9, 5, QImage.Format.Format_ARGB32)
    image.fill(QColor(10, 20, 30, 128))

    assert _png_colour_type(ocr.encode_png(image)) == 2


def test_encode_png_keeps_pixels_lossless_and_in_order():
    """PNG 是无损的；顺带把色彩序钉死：源是 RGB，解码方看到的就是 BGR。"""
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    image = QImage(4, 2, QImage.Format.Format_RGB888)
    image.fill(QColor(255, 0, 0))

    decoded = cv2.imdecode(np.frombuffer(ocr.encode_png(image), dtype=np.uint8), cv2.IMREAD_COLOR)

    assert decoded.shape == (2, 4, 3)
    assert tuple(int(v) for v in decoded[0, 0]) == (0, 0, 255), "rapidocr 要的是 BGR"


def test_encode_png_refuses_a_null_image():
    with pytest.raises(OcrRecognitionError):
        ocr.encode_png(QImage())


def test_empty_image_is_rejected_before_starting_a_process():
    engine, log = _engine(FAKE_TEXT)

    with pytest.raises(ValueError):
        engine.recognize(QImage())

    assert log.processes == [], "空图不该起一个要付几百毫秒启动成本的子进程"


def test_non_qimage_input_is_a_type_error():
    engine, log = _engine(FAKE_TEXT)

    with pytest.raises(TypeError):
        engine.recognize("not an image")

    assert log.processes == []


# ------------------------------------------------------------ 退出码 → 人话


def test_success_exit_returns_the_blocks_in_reading_order():
    engine, _ = _engine(FAKE_TEXT)

    blocks = engine.recognize(_blank())

    assert [block.text for block in blocks] == ["hello world"]
    assert blocks[0].score == pytest.approx(0.9)
    assert blocks[0].bounds == (1.0, 2.0, 29.0, 10.0)


def test_no_text_exit_is_an_empty_result_not_an_error():
    """「没识别到文字」是**成功**的一种：它必须一路传到 UI 的"没有识别到文字"，
    而不是变成一句错误提示。"""
    engine, _ = _engine(FAKE_NO_TEXT)

    assert engine.recognize(_blank(800, 400)) == []


def test_the_pipe_carries_exactly_one_frame():
    """管道里只能有**一个**帧：魔数 + 长度 + 正好那么长的 PNG，其后没有多余字节。

    套两层帧的写法（拼一次、传的时候又拼一次）在工作端那侧表现为"图像解不开"——
    报错指向图像格式，真正的原因却在传输层。这条把协议形状钉在管道上，而不是只钉
    在 ``frame_bytes`` 这个函数上。
    """
    image = _blank(64, 32)
    expected = len(ocr.encode_png(image))
    engine, _ = _engine(FAKE_FRAME_CHECK)

    blocks = engine.recognize(image)

    assert [b.text for b in blocks] == [f"magic=True size={expected} payload={expected}"]


def test_no_text_exit_that_carries_blocks_is_a_protocol_failure():
    """退出码与载荷是一对冗余信号；不一致时宁可报故障，也不显示一个可能错的结果。"""
    engine, _ = _engine(FAKE_LIES)

    with pytest.raises(OcrRecognitionError) as excinfo:
        engine.recognize(_blank())

    assert "自相矛盾" in str(excinfo.value)


def test_model_missing_exit_uses_the_workers_own_message():
    engine, _ = _engine(FAKE_MODEL_MISSING)

    with pytest.raises(OcrModelMissingError) as excinfo:
        engine.recognize(_blank())

    message = str(excinfo.value)
    assert "缺少本地 OCR 模型文件" in message and "/tmp" in message
    assert "noise from a native library" not in message, "没有前缀的噪声不许进人话"


def test_missing_dependency_exit_falls_back_to_a_plain_language_message():
    engine, _ = _engine(FAKE_UNAVAILABLE)

    with pytest.raises(OcrUnavailableError) as excinfo:
        engine.recognize(_blank())

    assert "依赖" in str(excinfo.value) and "重新安装" in str(excinfo.value)


def test_load_failure_exit_is_a_load_error():
    engine, _ = _engine(FAKE_LOAD_FAILED)

    with pytest.raises(OcrLoadError) as excinfo:
        engine.recognize(_blank())

    assert "加载" in str(excinfo.value)


def test_recognition_failure_exit_is_a_recognition_error():
    engine, _ = _engine(FAKE_REC_FAILED)

    with pytest.raises(OcrRecognitionError) as excinfo:
        engine.recognize(_blank())

    assert "识别" in str(excinfo.value)


@pytest.mark.parametrize("code", [1, 2, 3221225477, -1073741819])
def test_abnormal_exit_codes_are_never_read_as_success(code):
    """**只有工作端自己会产生的两个码**算成功（0=有文字、3=没文字）。

    其余一律是故障：1/2 是 Windows ``TerminateProcess`` 的常见落码（``Popen.kill``
    走的就是它），3221225477 / -1073741819 是访问违例。谁把 1 划给"没有文字"，
    取消与超时就会变成一句平静的「没有识别到文字」——用户以为机器没认出来，
    其实是他自己的操作被中止了。
    """
    assert ocr_worker.EXIT_TEXT not in (1, 2)
    assert ocr_worker.EXIT_NO_TEXT not in (1, 2)
    assert ocr_worker.EXIT_NO_TEXT != ocr_worker.EXIT_TEXT

    with pytest.raises(OcrError):
        ocr.interpret(code, b'{"blocks": []}', b"")


def test_a_crash_without_any_stage_record_still_names_the_exit_code():
    engine, _ = _engine(FAKE_CRASH_NO_STAGE)

    with pytest.raises(OcrLoadError) as excinfo:
        engine.recognize(_blank())

    message = str(excinfo.value)
    assert "42" in message, "退出码必须带出来，否则没人能定位"
    assert "启动或读取图像" in message


def test_a_crash_while_the_engine_loads_is_reported_as_a_load_error():
    engine, _ = _engine(FAKE_CRASH_LOADING)

    with pytest.raises(OcrLoadError) as excinfo:
        engine.recognize(_blank())

    assert "加载识别模型" in str(excinfo.value)


def test_a_crash_after_the_engine_loaded_is_reported_as_a_recognition_error():
    engine, _ = _engine(FAKE_CRASH_LATE)

    with pytest.raises(OcrRecognitionError) as excinfo:
        engine.recognize(_blank())

    assert "识别" in str(excinfo.value)


def test_a_killed_worker_is_never_mistaken_for_an_empty_result():
    """Windows 的 ``TerminateProcess`` 落码 1；协议里 1/2 刻意不分配给任何语义。

    这条是本片最容易出的静默错：取消/超时被杀的子进程要是被判成"图里没有文字"，
    用户会看到一句平静的「没有识别到文字」，而真相是他的这次操作被中止了。
    """
    engine, _ = _engine(FAKE_KILLED)

    with pytest.raises(OcrError) as excinfo:
        engine.recognize(_blank())

    message = str(excinfo.value)
    assert "没有识别到文字" not in message
    assert "异常退出" in message and "退出码 1" in message


@pytest.mark.parametrize("body", [FAKE_GARBAGE, FAKE_SILENT_OK])
def test_unusable_stdout_with_a_success_code_is_a_protocol_failure(body):
    engine, _ = _engine(body)

    with pytest.raises(OcrRecognitionError) as excinfo:
        engine.recognize(_blank())

    assert "工作进程" in str(excinfo.value)


def test_malformed_blocks_are_a_protocol_failure_not_a_crash():
    engine, _ = _engine(_FAKE_HEAD + _results({"text": "x", "score": "not a number", "box": []}) + "sys.exit(0)\n")

    with pytest.raises(OcrRecognitionError) as excinfo:
        engine.recognize(_blank())

    assert "坐标/置信度" in str(excinfo.value)


# ------------------------------------------------------- 超时 / 不留孤儿


def test_a_missing_worker_executable_reads_as_unavailable():
    engine = OcrEngine(command=lambda: [str(Path(__file__).parent / "no-such-worker.exe")])

    with pytest.raises(OcrUnavailableError) as excinfo:
        engine.recognize(_blank())

    assert "工作进程" in str(excinfo.value)


def test_timeout_kills_the_worker_and_reports_plain_language():
    engine, log = _engine(FAKE_HANG, timeout=1.0)

    started = time.monotonic()
    with pytest.raises(OcrRecognitionError) as excinfo:
        engine.recognize(_blank())
    elapsed = time.monotonic() - started

    assert elapsed < 20, "超时必须真的生效，不能把调用方挂住"
    assert "超时" in str(excinfo.value) and "等待 1 秒" in str(excinfo.value)

    process = log.processes[0]
    assert process.poll() is not None, "超时后进程必须已经被收走"
    assert _wait_for(lambda: not _pid_alive(process.pid)), "超时的识别子进程成了孤儿"


def test_release_engine_aborts_a_running_worker_and_says_so():
    engine, log = _engine(FAKE_HANG)
    errors: list = []

    thread = threading.Thread(target=lambda: _capture(engine, errors))
    thread.start()
    assert _wait_for(lambda: len(ocr._LIVE_WORKERS) > 0), "识别子进程没能在预算内起来"

    assert ocr.release_engine() is True, "在跑的识别子进程就该被中止"

    thread.join(timeout=30)
    assert not thread.is_alive(), "被中止的识别没能收尾"
    assert errors and "中止" in str(errors[0]), errors

    process = log.processes[0]
    assert process.poll() is not None
    assert _wait_for(lambda: not _pid_alive(process.pid)), "被中止的识别子进程成了孤儿"
    assert ocr._LIVE_WORKERS == set(), "收尾后不该还挂着进程"


def _capture(engine: OcrEngine, errors: list) -> None:
    try:
        engine.recognize(_blank())
    except Exception as exc:  # noqa: BLE001 - 测试要看清到底炸在哪
        errors.append(exc)


def test_release_engine_is_a_cheap_noop_when_nothing_runs():
    """每次截图收口都会调它：没有识别在跑就必须是零成本 no-op。"""
    assert ocr._LIVE_WORKERS == set()

    assert ocr.release_engine() is False


def test_a_successful_recognition_leaves_no_process_behind():
    engine, log = _engine(FAKE_TEXT)

    engine.recognize(_blank())

    process = log.processes[-1]
    assert process.poll() is not None, "认完就该退出（用完就丢）"
    assert ocr._LIVE_WORKERS == set()
    assert _wait_for(lambda: not _pid_alive(process.pid)), "跑完的识别子进程成了孤儿"


# ------------------------------------------------------------ 命令行（两态）


def test_worker_command_uses_the_module_in_source_mode(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert ocr.worker_command() == [sys.executable, "-m", ocr.WORKER_MODULE]


def test_worker_command_uses_the_internal_flag_when_frozen(monkeypatch):
    """冻结包里没有可用的 python：exe 自己就是解释器，走 --ocr-worker 子命令。"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "C:/fake/dsh-pet-standalone.exe")

    assert ocr.worker_command() == ["C:/fake/dsh-pet-standalone.exe", ocr.OCR_WORKER_FLAG]


def test_the_package_entry_serves_the_worker_flag():
    """源码态路由：``python -m pet --ocr-worker`` 必须真的进工作端（冻结入口同形）。"""
    process = subprocess.run(
        [sys.executable, "-m", "pet", ocr.OCR_WORKER_FLAG],
        input=b"not-a-frame", capture_output=True, cwd=REPO, timeout=120,
    )

    assert process.returncode == ocr_worker.EXIT_PROTOCOL
    assert ocr_worker.STDERR_PREFIX.encode() in process.stderr
    assert process.stdout == b"", "stdout 是协议通道：失败时不许往里写任何东西"


def test_the_worker_module_never_imports_pyside():
    """工作端只该付 rapidocr/numpy/onnxruntime 的启动开销。

    Qt 实测要多付约 0.2 s，而每次识屏都要付一遍——这正是子进程模型最想省的那一段。
    用一个真的子进程把 ``PySide6`` 从 import 系统里挡住：真有人往工作端链上加了
    Qt 依赖，这里立刻红（而不是等用户觉得"识屏怎么有点慢"）。
    """
    script = (
        "import sys\n"
        "class Blocker:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
        "            raise ImportError('PySide6 must not be imported by the OCR worker')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Blocker())\n"
        "import pet.screen_capture.ocr_worker\n"
        "leaked = [m for m in sys.modules if m == 'PySide6' or m.startswith('PySide6.')]\n"
        "print('LEAK' if leaked else 'CLEAN')\n"
    )
    process = subprocess.run([sys.executable, "-c", script], capture_output=True,
                             cwd=REPO, timeout=120)

    assert process.returncode == 0, process.stderr.decode("utf-8", "replace")
    assert process.stdout.strip() == b"CLEAN"


# -------------------------------------------------------------------- 只读视图


def test_shared_engine_is_a_single_instance():
    assert ocr.shared_engine() is ocr.shared_engine()


def test_module_level_recognize_joins_blocks_in_reading_order():
    """切片 3 的 seam 契约：``ocr.recognize(QImage) -> str``（同步、纯本地、不联网）。"""
    body = _FAKE_HEAD + _results(
        {"text": "第二行", "score": 0.9, "box": [[10, 60], [70, 60], [70, 90], [10, 90]]},
        {"text": "右", "score": 0.9, "box": [[120, 10], [180, 10], [180, 40], [120, 40]]},
        {"text": "左", "score": 0.9, "box": [[10, 14], [70, 14], [70, 44], [10, 44]]},
    ) + "sys.exit(0)\n"
    engine, _ = _engine(body)
    original = ocr.shared_engine
    ocr.shared_engine = lambda: engine
    try:
        assert ocr.recognize(_blank()) == "左\n右\n第二行"
    finally:
        ocr.shared_engine = original


# ---------------------------------------------------------------- 阅读顺序


def _box(left: float, top: float, width: float, height: float):
    return ((left, top), (left + width, top), (left + width, top + height), (left, top + height))


def test_reading_order_sorts_lines_top_to_bottom_and_left_to_right():
    """同行的两块上沿差 2 px、不同行差 90 px——纯按上沿排会把同行两块排反。"""
    blocks = [
        TextBlock("右下", 0.9, _box(300, 100, 60, 30)),
        TextBlock("左上", 0.9, _box(10, 12, 60, 30)),
        TextBlock("左下", 0.9, _box(10, 100, 60, 30)),
        TextBlock("右上", 0.9, _box(300, 10, 60, 30)),
    ]

    assert [b.text for b in reading_order(blocks)] == ["左上", "右上", "左下", "右下"]


def test_reading_order_keeps_baseline_shifted_boxes_on_one_line():
    """同一行里右边那块比左边高 4 px（字号/基线不同），不能因此把顺序颠倒。"""
    blocks = [
        TextBlock("右", 0.9, _box(120, 10, 60, 30)),
        TextBlock("左", 0.9, _box(10, 14, 60, 30)),
        TextBlock("下一行", 0.9, _box(10, 60, 60, 30)),
    ]

    assert [b.text for b in reading_order(blocks)] == ["左", "右", "下一行"]


def test_reading_order_accepts_empty_input():
    assert reading_order([]) == []


def test_text_block_bounds_and_center():
    block = TextBlock("x", 0.5, _box(10, 20, 30, 40))

    assert block.bounds == (10.0, 20.0, 30.0, 40.0)
    assert block.center == (25.0, 40.0)


# --------------------------------------------------------- 真实工作端（端到端）


class _RealWorker:
    """真工作端 + 起过的进程记录（pid 与存活状态是"用完就丢"的证据）。"""

    def __init__(self) -> None:
        self.processes: list = []
        self.engine = OcrEngine(spawn=self._spawn)

    def _spawn(self, argv):
        process = ocr.spawn_worker(argv)
        self.processes.append(process)
        return process


@pytest.fixture(scope="module")
def real_worker():
    pytest.importorskip("rapidocr", reason="未安装本地 OCR 依赖（rapidocr）")
    directory = ocr.resolve_model_dir()
    problem = ocr.model_problem(directory)
    assert not problem, (
        f"本地 OCR 模型不可用：{problem}\n"
        f"模型随包放在 {ocr.bundled_model_dir()}；"
        "重新取出的命令见 pet/screen_capture/ocr_models.py 的模块说明"
    )
    return _RealWorker()


def test_real_worker_reads_known_latin_lines_in_reading_order(real_worker, latin_family):
    image = _screenshot(latin_family)

    blocks = real_worker.engine.recognize(image)

    joined = " ".join(block.text for block in blocks).lower()
    assert "12345" in joined, f"没读出行 1 的关键词，实际识别：{joined!r}"
    assert "fox" in joined, f"没读出行 2 的关键词，实际识别：{joined!r}"
    assert "2026" in joined, f"没读出行 3 的关键词，实际识别：{joined!r}"

    keywords = ("12345", "fox", "2026")
    positions = [next(i for i, b in enumerate(blocks) if key in b.text.lower()) for key in keywords]
    assert positions == sorted(positions), f"三行的块序不是自上而下：{[(b.text, b.bounds) for b in blocks]}"

    for block in blocks:
        left, top, width, height = block.bounds
        assert 0 < block.score <= 1.0
        assert left >= -1 and top >= -1
        assert left + width <= image.width() + 1
        assert top + height <= image.height() + 1


def test_real_worker_reads_chinese_lines(real_worker, cjk_family):
    image = _screenshot(cjk_family, ("本地离线识别", "快速识屏提取文字"))

    blocks = real_worker.engine.recognize(image)

    joined = "".join(block.text for block in blocks)
    assert "离线" in joined, f"中文识别没对上，实际识别：{joined!r}"
    assert "文字" in joined, f"中文识别没对上，实际识别：{joined!r}"


def test_real_worker_returns_empty_list_for_blank_image(real_worker):
    assert real_worker.engine.recognize(_blank(800, 400)) == []


def test_real_worker_exits_after_every_recognition(real_worker, latin_family):
    """「用完就丢」的进程级证据：每次识别都是一个**新的**、认完就死的进程。

    这正是切片 5 存在的理由：进程退出时操作系统把所有 native 堆收走，RSS 回到
    触发前的水位（实测数字见 ``.scratch/screen-capture/probe_ocr_subprocess.txt``）。
    进程内 ``unload()`` 做不到这件事（只回吐约 30 MB / 108 MB）。
    """
    before = len(real_worker.processes)

    real_worker.engine.recognize(_blank(320, 120))
    real_worker.engine.recognize(_blank(320, 120))

    started = real_worker.processes[before:]
    assert len(started) == 2, "每次 recognize 都该起一个新进程（不许复用常驻进程）"
    assert started[0].pid != started[1].pid
    for process in started:
        assert process.poll() is not None, "认完就退：进程还在就是「内存没真归零」"
        assert _wait_for(lambda p=process: not _pid_alive(p.pid))


def test_real_worker_reports_missing_models_in_plain_language(monkeypatch, tmp_path):
    """真工作端子进程 + 显式模型目录：报出来的那句话必须能直接给用户看。"""
    monkeypatch.setenv(ocr.OCR_MODEL_DIR_ENV, str(tmp_path))
    engine = OcrEngine()

    with pytest.raises(OcrModelMissingError) as excinfo:
        engine.recognize(_blank(320, 120))

    message = str(excinfo.value)
    assert "模型" in message and str(tmp_path) in message


def test_self_built_sessions_are_injected_into_the_engine_cfg():
    """「断网可用」的承重结构：三份 session 必须真的被写回引擎配置。

    rapidocr 自建 session 时会去读 ``Det/Rec/Cls.model_path``，那个字段为空时它
    **会去网上下**（``DownloadFile.run``）。从外面把 session 塞进去，那条分支就短路
    了——所以"断网可用"是结构保证，不是"但愿随包文件都在"。
    """
    from omegaconf import OmegaConf

    class _FakeEngine:
        cfg = {"Det": OmegaConf.create({"model_path": ""}), "Cls": OmegaConf.create({}),
               "Rec": OmegaConf.create({})}

    sessions = {"Det": object(), "Cls": object(), "Rec": object()}

    ocr_worker._attach_sessions(_FakeEngine, sessions)

    for section, session in sessions.items():
        assert _FakeEngine.cfg[section].session is session


def test_the_real_worker_recognizes_with_the_network_blocked():
    """断网可用是硬要求：把 ``socket.socket`` 换成会抛异常的桩之后，真工作端照样认字。

    模型必须随包，加载期任何 HTTP 请求都算违规——而"加载期"现在发生在**另一个
    进程**里，所以在进程内打桩 ``requests`` 已经管不到它（切片 2 那条做法到此失效）。
    这里改成在真子进程里把 socket 层堵死：堵住了还认出字，才说明走的是随包模型。
    """
    pytest.importorskip("rapidocr", reason="未安装本地 OCR 依赖（rapidocr）")
    script = (
        "import socket, sys\n"
        "def _forbidden(*args, **kwargs):\n"
        "    raise AssertionError('识别子进程在加载/识别期发起了网络连接')\n"
        "socket.getaddrinfo = _forbidden\n"
        "socket.create_connection = _forbidden\n"
        "socket.socket.connect = _forbidden\n"
        "socket.socket.connect_ex = _forbidden\n"
        "import runpy\n"
        "runpy.run_module('pet.screen_capture.ocr_worker', run_name='__main__')\n"
    )
    image = _blank(320, 120)
    process = subprocess.run(
        [sys.executable, "-c", script], input=ocr.frame_bytes(ocr.encode_png(image)),
        capture_output=True, cwd=REPO, timeout=180,
    )

    assert process.returncode == ocr_worker.EXIT_NO_TEXT, process.stderr.decode("utf-8", "replace")
    assert b'"blocks"' in process.stdout
