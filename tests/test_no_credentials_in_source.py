# -*- coding: utf-8 -*-
"""面向公众发包的凭据守卫：仓库源码里**永远不许出现真实凭据**。

背景（她 2026-10-13 的关切）：「面向公众发包的话，这些引擎接入需要他们自己来做，
不能走我的API啊」——所以：① 仓库默认值一律留空；② 真实凭据只存**用户自己的**
系统钥匙串（`pet/tts_secrets.py`）；③ 这道守卫把"不许写进源码"钉死。

误报教训（第一版抓到的）：`sk` 前缀不能裸配（`skip_tick_count` 会被当密钥），
必须**带分隔符**且**看起来有熵**（大小写+数字混合，或长十六进制），否则测试里的
合成假值（`sk-legacy-token-1` 这种全小写）也会被算成凭据。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("pet", "docs", "tests", "packaging", "scripts")
SUFFIXES = {".py", ".md", ".json", ".txt", ".yml", ".yaml", ".ps1", ".iss"}

#: 用片段拼出来，避免守卫自身成为命中样本
_UUID = re.compile(r"\b[0-9a-fA-F]{8}" + "-[0-9a-fA-F]{4}" + "-[0-9a-fA-F]{4}"
                   + "-[0-9a-fA-F]{4}" + "-[0-9a-fA-F]{12}\b")
_LONG_HEX = re.compile(r"\b[0-9a-f]{32}\b")
_SECRET_PREFIX = re.compile(r"\b(?:sk|AKLT|AKID|LTAI)[-_][A-Za-z0-9_-]{12,}\b")
_KEY_LITERAL = re.compile(
    r"""(?:api[_-]?key|secret[_-]?key|access[_-]?token|app[_-]?secret|api[_-]?secret)"""
    r"""\s*[=:]\s*["']([^"'\s]{12,})["']""",
    re.IGNORECASE,
)

ALLOWED_VALUES = {
    "00000000-0000-0000-0000-000000000000",
    "12345678-1234-1234-1234-123456789012",
}
SYNTHETIC_WORDS = ("test", "fake", "dummy", "sample", "example", "placeholder", "stub",
                   "mock", "legacy", "provider", "local", "chain", "your", "xxx")


def _looks_like_secret(value: str) -> bool:
    """有熵才算：真实密钥基本是"大小写+数字"混合或长十六进制；合成假值多为全小写词。"""
    if len(value) < 20:
        return False
    if any(word in value.lower() for word in SYNTHETIC_WORDS):
        return False
    if re.fullmatch(r"[0-9a-f]+", value):
        return len(value) >= 32
    has_digit = any(ch.isdigit() for ch in value)
    has_upper = any(ch.isupper() for ch in value)
    has_lower = any(ch.islower() for ch in value)
    return has_digit and has_upper and has_lower


def _hits(path: Path) -> list[str]:
    found: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return found
    if path.name == "test_no_credentials_in_source.py":
        return found
    for match in _UUID.finditer(text):
        value = match.group(0)
        if value.lower() not in {a.lower() for a in ALLOWED_VALUES}:
            found.append(f"UUID 形态串: {value[:8]}…")
    for match in _LONG_HEX.finditer(text):
        found.append(f"长十六进制串: {match.group(0)[:8]}…")
    for match in _SECRET_PREFIX.finditer(text):
        if _looks_like_secret(match.group(0)):
            found.append(f"密钥前缀形态: {match.group(0)[:6]}…")
    for match in _KEY_LITERAL.finditer(text):
        if _looks_like_secret(match.group(1)):
            found.append(f"非空凭据字面量: {match.group(1)[:4]}…")
    return found


def _scanned_files() -> list[Path]:
    try:
        listed = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.splitlines()
    except Exception:  # noqa: BLE001 —— 没有 git 就退化成遍历
        listed = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()]
    out = []
    for rel in listed:
        if not rel.startswith(SCAN_DIRS) or rel.startswith(".scratch"):
            continue
        if Path(rel).suffix.lower() not in SUFFIXES:
            continue
        path = ROOT / rel
        if path.is_file():
            out.append(path)
    return out


def test_no_credentials_in_source() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _scanned_files():
        hits = _hits(path)
        if hits:
            offenders[str(path.relative_to(ROOT))] = hits
    assert not offenders, (
        "仓库源码里出现了疑似真实凭据——真实凭据只许存在**用户自己的**系统钥匙串里"
        "（见 pet/tts_secrets.py），仓库默认值一律留空：\n"
        + "\n".join(f"  {name}: {hits}" for name, hits in offenders.items())
    )


def test_guard_scan_covers_the_tts_providers() -> None:
    """守卫必须真的在扫——不然它绿得毫无意义。"""
    names = {str(p.relative_to(ROOT)).replace("\\", "/") for p in _scanned_files()}
    assert "pet/tts/doubao.py" in names
    assert "pet/tts/__init__.py" in names


if __name__ == "__main__":
    test_no_credentials_in_source()
    print("凭据守卫通过：仓库源码里没有凭据")
    sys.exit(0)
