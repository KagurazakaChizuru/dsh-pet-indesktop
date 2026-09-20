# -*- coding: utf-8 -*-
"""检查更新（GitHub Releases）。

右键/托盘菜单「检查更新」：查询 GitHub 最新 release 与本地版本比较；
有新版本时「打开下载页」跳转 Release 页面。

仅使用标准库（urllib），与聊天 HTTP 层一致，不引入 requests。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import __version__

# 与 pet/__init__.py 保持单一来源：发布时只改一处
APP_VERSION = __version__
REPO = 'MerZlin/dsh-pet-indesktop'
RELEASE_API = f'https://api.github.com/repos/{REPO}/releases/latest'
REPO_URL = f'https://github.com/{REPO}'
# 夸克网盘备用下载地址（Windows 安装包镜像；菜单「夸克网盘下载」入口）
QUARK_PAN_URL = 'https://pan.quark.cn/s/68fc681ae486'
# 仓库内 update.json 的 CDN 镜像源：GitHub API 不可达（被墙/网络抖动）时回退，
# jsDelivr 在国内一般稳定可达（实测 cdn/fastly 均通）。
_UPDATE_JSON_URLS = (
    f'https://cdn.jsdelivr.net/gh/{REPO}@main/update.json',
    f'https://fastly.jsdelivr.net/gh/{REPO}@main/update.json',
    f'https://gcore.jsdelivr.net/gh/{REPO}@main/update.json',
)
_USER_AGENT = 'dsh-pet-standalone-updater'


def _fetch_json(url: str, timeout: float):
    """GET JSON；任何失败返回 None。"""
    try:
        req = urllib.request.Request(
            url,
            headers={'Accept': 'application/json', 'User-Agent': _USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def latest_release(timeout: float = 5.0) -> dict | None:
    """多源查询最新版本信息（统一结构）。

    1) GitHub Releases API（完整 Release 说明与资产）；
    2) 仓库内 update.json 的 jsDelivr CDN 镜像（API 不可达时兜底）。

    返回统一 dict：
    {'version': '3.0.0', 'html_url': ..., 'notes': ..., 'assets': {name: url}}
    全部失败返回 None。
    """
    release = _fetch_json(RELEASE_API, timeout)
    if release is not None and release.get('tag_name'):
        return {
            'version': str(release['tag_name']).lstrip('vV'),
            'html_url': str(release.get('html_url', REPO_URL)),
            'notes': str(release.get('body') or ''),
            'assets': {
                str(a['name']): str(a['browser_download_url'])
                for a in release.get('assets', [])
                if a.get('name') and a.get('browser_download_url')
            },
        }
    for url in _UPDATE_JSON_URLS:
        data = _fetch_json(url, timeout)
        if data is not None and data.get('version'):
            assets = {}
            for name, link in (data.get('assets') or {}).items():
                if isinstance(link, str):
                    assets[str(name)] = link
            return {
                'version': str(data['version']).lstrip('vV'),
                'html_url': str(data.get('html_url', REPO_URL)),
                'notes': str(data.get('notes') or ''),
                'assets': assets,
            }
    return None


def version_parts(tag: str) -> list[int]:
    """'v3.0.1' / '3.0.0' → [3, 0, 1]（忽略每段前导非数字字符）。"""
    out: list[int] = []
    for seg in str(tag).lstrip('vV').split('.'):
        digits = ''
        for ch in seg:
            if ch.isdigit():
                digits += ch
            else:
                break
        out.append(int(digits) if digits else 0)
    return out


def is_newer(latest_tag: str, current: str = APP_VERSION) -> bool:
    """latest_tag 是否比 current 新（'v3.0.1' > '3.0.0'）。"""
    return version_parts(latest_tag) > version_parts(current)

