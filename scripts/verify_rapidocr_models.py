# -*- coding: utf-8 -*-
"""随包分发的本地 OCR 模型完整性硬门（构建管线，2026-10-13）。

**为什么需要这道门**：「截图提取文字」走的是**随包**的三个 ONNX 模型
（``resources/rapidocr_models/``），加载路径上没有任何下载分支。它们缺失或换版时
产品**不会崩**：识别要么直接报"缺少本地 OCR 模型文件…请重新安装"，要么（更坏）
静默变差——错字、漏行、整段读不出来，而用户只会觉得"这个识屏不准"。所以判据必须
在打包阶段跑，而不是等用户反馈。

**为什么 sha256 而不只是文件名**：三个文件名里带版本（``PP-OCRv6_*``），但换版时
"同名不同内容"是完全可以发生的（重新导出、换量化档、拿检测模型顶替识别模型…）。
文件名对得上、内容不是那一份，产品照旧不崩、只是不准——摘要正是为这种静默替换
存在的。运行期**不**校验（每次启动多读 31 MB 只为一件 CI 该做的事，见
``pet/screen_capture/ocr.py::MODEL_SHA256`` 的注释）。

**判据来源是单一真相源**：文件名与 sha256 都从 ``pet/screen_capture/ocr.py`` 读
（``MODEL_FILES`` / ``MODEL_SHA256`` / ``MODEL_RELATIVE_DIR``），本脚本不抄第二份
字面量——抄一份的下场是"改了产品没改门"或者反过来，而这两件事都会让门失去意义。
代价是这里会连带 import PySide6.QtGui（``ocr.py`` 顶部 import 了 ``QImage``，实测
0.18 s）：构建机上 PySide6 本来就必须装（要打包它），所以这条代价换的是"少一份
会漂移的常量"，值。

用法：
    python scripts/verify_rapidocr_models.py                    # 验仓库里的模型
    python scripts/verify_rapidocr_models.py --dir <目录>        # 验指定目录（验产物用）
    python scripts/verify_rapidocr_models.py --app-dir <产物根>  # 验 onedir 产物（模块+模型+配置）
    python scripts/verify_rapidocr_models.py --json              # 机器可读输出

退出码：0 = 三个模型都在、名字对、sha256 逐个对上（--app-dir 还要加上"引擎模块在包里"）；
1 = 缺失 / 摘要不符 / 引擎模块不在产物里（明细打到 stderr，含期望值、实际值与重新取出的命令）。

**`--app-dir` 为什么必须存在（2026-10-13 交叉审查 B1）**：模型齐全不等于冻结包能用。
截图动作的引擎走的是**动态 seam**（``pet/screen_capture/actions.py`` 用 importlib 按
字符串 ``"ocr"`` 解析 ``pet.screen_capture.ocr``），PyInstaller 的静态分析从入口出发
摸不到这个模块——只有构建脚本里那条 ``--hidden-import pet.screen_capture.ocr`` 能让它
进包。少了那条参数，模型、rapidocr 配置全都随包，冻结包里却解析不出引擎，产品不崩、
只是右键「截图 → 提取文字」永远置灰。

切片 5 之后要判的模块变成**两个**：宿主侧的 ``pet.screen_capture.ocr``，以及识别
子进程的 ``pet.screen_capture.ocr_worker``（冻结包里是 ``<exe> --ocr-worker``，模块
名只以字符串出现在命令行里）。缺后者不会崩——每次点击报一句"起不了工作进程"，同样
是"包看着完整、功能是死的"。判据见 :func:`required_bundle_modules`。

所以要判的是**四件事**（两个模块 + 模型 + 配置），而模块那两件只能从产物的模块图里读。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

#: rapidocr 自己的两份配置数据（不是"模型"，但缺了引擎连构造都失败）。
RAPIDOCR_BUNDLE_CONFIG_FILES = ("config.yaml", "default_models.yaml")

#: 模型缺失时给打出包人的补法（与 ocr.py 模块说明里的那条命令同源）。
FETCH_HINT = (
    "重新取出模型（与 rapidocr wheel 自带的模型逐字节相同）：\n"
    '    python -c "import os, rapidocr, shutil; src=os.path.join('
    "os.path.dirname(rapidocr.__file__), 'models'); "
    "[shutil.copy2(os.path.join(src, n), 'resources/rapidocr_models/') "
    "for n in os.listdir(src) if n.endswith('.onnx')]\""
)


def repo_root() -> Path:
    """仓库根（本脚本在 ``<root>/scripts/`` 下）。"""
    return Path(__file__).resolve().parents[1]


def _repo_on_path() -> None:
    """把仓库根放进 ``sys.path``（判据要从产品模块里读，不能靠调用方的 cwd）。"""
    root = repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def required_bundle_modules() -> tuple[str, ...]:
    """产物模块图里必须存在的模块（「截图提取文字」的两个动态目标）。

    判据同样来自单一真相源：``pet/screen_capture/ocr.py`` 的 :data:`BUNDLE_MODULES`
    ——宿主侧那一条是模块名（``actions`` 的 importlib seam 拼出来的
    ``pet.screen_capture.ocr``），子进程那一条也是模块名（``ocr_worker.py`` 只以
    ``<python> -m pet.screen_capture.ocr_worker`` 的形式出现在命令行字符串里）。
    两者都**没有**静态 import 指向，PyInstaller 从入口出发摸不到；只有构建脚本的
    ``--hidden-import`` 能把它们拉进包。本脚本不抄第二份字面量——抄一份的下场是
    "改了产品没改门"。代价是这里会连带 import 整条截图动作栈（实测 +0.04 s：
    QtGui 已为 ocr.py 加载过），构建机上无感。
    """
    _repo_on_path()
    from pet.screen_capture import ocr  # noqa: PLC0415 —— 路径先就位才能 import

    return tuple(ocr.BUNDLE_MODULES)


def load_expectations():
    """从 ``pet/screen_capture/ocr.py`` 取期望值：``(目录, {段名: 文件名}, {段名: sha256})``。"""
    _repo_on_path()
    from pet.screen_capture import ocr  # noqa: PLC0415 —— 路径先就位才能 import

    return (repo_root().joinpath(*ocr.MODEL_RELATIVE_DIR), dict(ocr.MODEL_FILES),
            dict(ocr.MODEL_SHA256))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect(directory: Path, expected_files: dict, expected_shas: dict) -> dict:
    """给一个候选目录出体检报告（不抛异常，结论都在返回值里）。"""
    report: dict = {
        "dir": str(directory),
        "exists": directory.is_dir(),
        "models": [],
        "problems": [],
    }
    if not report["exists"]:
        report["problems"].append(f"模型目录不存在：{directory}")
        return report

    for section, name in expected_files.items():
        path = directory / name
        entry: dict = {
            "section": section,
            "name": name,
            "path": str(path),
            "expected_sha256": expected_shas.get(section),
            "exists": path.is_file(),
            "size": None,
            "sha256": None,
            "sha256_ok": False,
        }
        if not entry["exists"]:
            entry["problem"] = "文件不存在"
        else:
            entry["size"] = path.stat().st_size
            try:
                entry["sha256"] = file_sha256(path)
            except OSError as error:  # 读不动就别假装读过
                entry["problem"] = f"读文件失败：{error}"
            else:
                entry["sha256_ok"] = entry["sha256"] == entry["expected_sha256"]
                if not entry["sha256_ok"]:
                    entry["problem"] = "sha256 不符（同名不同内容＝静默换版）"
        if entry.get("problem"):
            report["problems"].append(f"{name}：{entry['problem']}")
        report["models"].append(entry)

    extra = sorted(p.name for p in directory.glob("*.onnx")
                   if p.name not in set(expected_files.values()))
    report["unexpected_onnx"] = extra       # 只登记，不判失败
    return report


def format_human(report: dict) -> str:
    lines = [f"检查：{report['dir']}"]
    if not report["exists"]:
        lines.append("  目录不存在")
    for entry in report["models"]:
        state = "OK" if entry["sha256_ok"] else "[不符]"
        lines.append(f"  {entry['name']}（{entry['section']}）："
                     f"{entry['size'] if entry['size'] is not None else '缺失'} 字节 {state}")
        if entry["sha256"] and not entry["sha256_ok"]:
            lines.append(f"    期望 sha256：{entry['expected_sha256']}")
            lines.append(f"    实际 sha256：{entry['sha256']}")
    if report.get("unexpected_onnx"):
        lines.append(f"  （另有未登记的 onnx：{', '.join(report['unexpected_onnx'])}）")
    for problem in report["problems"]:
        lines.append(f"  问题：{problem}")
    return "\n".join(lines)


# ------------------------------------------------------- 产物侧（--app-dir）


def find_payload(app_dir: Path, relative: Path) -> Path:
    """在产物里**按存在性**找一段相对路径（不按平台猜载荷目录叫什么）。

    三端落点本来就不同：Windows/Linux 的 onedir 载荷在 ``<app>/_internal/``；
    macOS 的 ``.app`` 按 bundle 规范把**数据**放 ``Contents/Resources``、代码类放
    ``Contents/Frameworks``（PyInstaller 6，见 ``building/osx.py`` 的注释），而我们
    要判的三样里两样是数据。所以这里不写"macOS 一定在 X"，而是依次试候选、取真正
    存在的那一个——找不到时返回**第一个候选**（Windows/Linux 的常规落点），让报错
    里的路径是可读的、能直接去 ls 的那一个。
    """
    candidates = (
        app_dir / "_internal" / relative,
        app_dir / "Contents" / "Resources" / relative,
        app_dir / "Contents" / "Frameworks" / relative,
        app_dir / relative,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def iter_app_executables(app_dir: Path):
    """产物里的主程序（CArchive 的载体）。macOS .app 取 ``Contents/MacOS`` 下的可执行件。"""
    if app_dir.name.endswith(".app") or (app_dir / "Contents" / "MacOS").is_dir():
        macos_dir = app_dir / "Contents" / "MacOS"
        if macos_dir.is_dir():
            for path in sorted(macos_dir.iterdir()):
                if path.is_file():
                    yield path
            return
    for path in sorted(app_dir.iterdir()):
        if path.is_file() and (path.suffix.lower() == ".exe" or path.suffix == ""):
            yield path


def missing_bundle_modules(names, required) -> list[str]:
    """产物模块名清单里缺哪些必需模块（纯函数：判据与"读产物"分开，可单测）。"""
    present = set(names)
    return [name for name in required if name not in present]


def bundle_module_names(app_dir: Path) -> tuple[set[str], list[str]]:
    """读产物内嵌 PYZ 的模块名清单；读不出来返回空集 + 原因（**不放行**）。

    工程模块不在磁盘上——PyInstaller onedir 把它们打进主程序内嵌的 PYZ
    （``ZlibArchive``），只能用 PyInstaller 自己的 reader 解析（同
    ``scripts/check_bundle_encoding.py`` 的口径）。读不出来＝这条门没验成，
    按失败处理：一个"验不了就放过"的门比没有门更糟（它给人已经查过的错觉）。
    """
    try:
        from PyInstaller.archive.readers import CArchiveReader
        from PyInstaller.archive.readers import PKG_ITEM_PYZ
    except Exception as exc:  # 构建机上 PyInstaller 必然在；不在就是环境坏了
        return set(), [f"读不了产物模块图（PyInstaller reader 不可用：{exc}）"]

    names: set[str] = set()
    archives = 0
    for exe in iter_app_executables(app_dir):
        try:
            archive = CArchiveReader(str(exe))
        except Exception:  # 不是 CArchive（普通文件/被签名工具改过）：跳过，看下一个
            continue
        for entry_name, entry in archive.toc.items():
            if entry[4] != PKG_ITEM_PYZ:
                continue
            try:
                pyz = archive.open_embedded_archive(entry_name)
                names |= set(pyz.toc)
                archives += 1
            except Exception:
                continue
    if not archives:
        return names, [f"产物里找不到可读的模块归档（主程序呢？）：{app_dir}"]
    return names, []


def inspect_app_dir(app_dir: Path, expected_files: dict, expected_shas: dict,
                    required_modules=()) -> dict:
    """给一个 onedir 产物出体检报告：引擎模块 + 模型 + rapidocr 配置三件一起判。"""
    required = tuple(required_modules) or required_bundle_modules()
    app_dir = Path(app_dir)
    models_dir = find_payload(app_dir, Path("resources") / "rapidocr_models")
    cfg_dir = find_payload(app_dir, Path("rapidocr"))
    models = inspect(models_dir, expected_files, expected_shas)
    missing_cfg = [name for name in RAPIDOCR_BUNDLE_CONFIG_FILES
                   if not (cfg_dir / name).is_file()]
    names, module_problems = bundle_module_names(app_dir)
    missing_modules = missing_bundle_modules(names, required)
    problems = list(models["problems"]) + list(module_problems)
    problems += [f"产物里缺少 rapidocr 配置数据 {name}（路径 {cfg_dir / name}）"
                 for name in missing_cfg]
    problems += [f"产物里没有模块 {name}——动态 seam 永远解析不到它，"
                 "右键「截图 → 提取文字」会一直置灰（构建脚本的 "
                 "--hidden-import 掉了？）" for name in missing_modules]
    return {
        "app_dir": str(app_dir),
        "models": models,
        "models_dir": str(models_dir),
        "rapidocr_config_dir": str(cfg_dir),
        "missing_rapidocr_config": missing_cfg,
        "bundle_modules_checked": list(required),
        "missing_bundle_modules": missing_modules,
        "problems": problems,
    }


def format_app_dir(report: dict) -> str:
    lines = [f"检查产物：{report['app_dir']}"]
    for name in report["bundle_modules_checked"]:
        state = "[缺失]" if name in report["missing_bundle_modules"] else "OK"
        lines.append(f"  引擎模块 {name}：{state}")
    lines.append(format_human(report["models"]).replace("\n", "\n  "))
    for name in RAPIDOCR_BUNDLE_CONFIG_FILES:
        state = "[缺失]" if name in report["missing_rapidocr_config"] else "OK"
        lines.append(f"  rapidocr 配置 {name}：{state}")
    for problem in report["problems"]:
        lines.append(f"  问题：{problem}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    default_dir, expected_files, expected_shas = load_expectations()
    parser = argparse.ArgumentParser(
        description="校验随包分发的本地 OCR（模型 / 引擎模块 / rapidocr 配置）")
    parser.add_argument(
        "--dir", default=None,
        help="被检查的模型目录；省略即检查仓库资源 "
             f"({default_dir.relative_to(repo_root()).as_posix()})")
    parser.add_argument(
        "--app-dir", default=None,
        help="被检查的 onedir 产物根目录（产物侧的一站式门：引擎模块 + 模型 + "
             "rapidocr 配置）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args(argv)

    if args.app_dir:
        required = required_bundle_modules()
        report = inspect_app_dir(Path(args.app_dir).expanduser(),
                                 expected_files, expected_shas, required)
        ok = not report["problems"]
        if args.json:
            print(json.dumps({**report, "ok": ok}, ensure_ascii=False, indent=2))
        elif ok:
            print(format_app_dir(report))
            print("OK: 产物可以直接跑本地 OCR（引擎模块在模块图里、模型与配置齐全）")
        else:
            sys.stderr.write(format_app_dir(report) + "\n")
            sys.stderr.write(
                "FAIL: 这个产物无法跑「截图提取文字」——构建中止。缺模型/配置只是让识别"
                "静默变差；缺引擎模块则产品不崩、菜单永远置灰（那正是动态 seam 的坑）。\n"
                f"期望的引擎模块：{', '.join(required)}\n"
                "（构建脚本里必须有 --hidden-import pet.screen_capture.ocr）\n"
                + FETCH_HINT + "\n")
        return 0 if ok else 1

    target = Path(args.dir).expanduser() if args.dir else default_dir
    report = inspect(target, expected_files, expected_shas)
    ok = not report["problems"]

    if args.json:
        print(json.dumps({**report, "ok": ok}, ensure_ascii=False, indent=2))
    else:
        (sys.stdout if ok else sys.stderr).write(format_human(report) + "\n")
        if not ok:
            sys.stderr.write(
                "FAIL: 随包分发的本地 OCR 模型不完整——构建中止（缺件/换版不会让"
                "程序崩，只会让「截图提取文字」静默变差或直接不可用）。\n"
                f"期望目录：{default_dir}\n" + FETCH_HINT + "\n")
        else:
            print("OK: 本地 OCR 模型完整（三个文件名与 sha256 逐项一致）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
