"""
微信公众号 RSS 集成 - Batch 7 交付

路径 A: 本地 WeRSS (Node 原生, 用户用 scripts/install-werss.sh 安装并启动)
路径 B: 手动把任意微信公众号 RSS 源 (werss / feeddd / rsshub /wechat/ce) 接入 Argus

MCP 工具:
    wechat_rss_status(port?)          — 探测本地 werss 是否在运行
    wechat_add_feed(url, name, id?)   — 把一个微信 RSS URL 加到 config.yaml
    wechat_list_feeds()               — 列出 config.yaml 中已集成的微信相关 feed
    wechat_remove_feed(id)            — 从 config.yaml 移除一个 wechat 源

只改 Argus config.yaml, 不依赖 werss 自身 API (werss 是 web 应用, 订阅动作靠 web UI)。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "WECHAT_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,48}$")


class WechatRSSTools:
    """微信公众号 RSS 集成"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self.config_path = self.project_root / "config" / "config.yaml"

    # ────────────── 工具: werss 状态 ──────────────

    def werss_status(self, port: int = 8080, host: str = "127.0.0.1") -> Dict:
        url = f"http://{host}:{port}/"
        try:
            r = requests.get(url, timeout=5)
            return _ok(
                {
                    "running": True,
                    "url": url,
                    "status_code": r.status_code,
                    "title_hint": self._extract_title(r.text),
                },
                port=port,
            )
        except requests.exceptions.ConnectionError:
            return _ok(
                {
                    "running": False,
                    "url": url,
                    "hint": "werss 未运行. 执行 scripts/install-werss.sh 安装, 然后 werss/start.sh bg",
                },
                port=port,
            )
        except Exception as ex:
            return _err(f"探测失败: {ex}", code="NETWORK_ERROR")

    @staticmethod
    def _extract_title(html: str) -> str:
        m = re.search(r"<title>([^<]+)</title>", html or "", re.IGNORECASE)
        return (m.group(1).strip() if m else "")[:100]

    # ────────────── config.yaml 读写 ──────────────

    def _yaml(self):
        """ruamel.yaml 实例 (保留注释 + 格式)"""
        from ruamel.yaml import YAML
        y = YAML()
        y.preserve_quotes = True
        y.indent(mapping=2, sequence=4, offset=2)
        y.width = 200
        return y

    def _load_yaml(self):
        try:
            y = self._yaml()
        except ImportError:
            return None, "ruamel.yaml 未安装, pip install ruamel.yaml"
        if not self.config_path.exists():
            return None, f"config.yaml 不存在: {self.config_path}"
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                return y.load(f), None
        except Exception as ex:
            return None, f"config.yaml 解析失败: {ex}"

    def _write_yaml(self, data) -> Optional[str]:
        try:
            y = self._yaml()
        except ImportError:
            return "ruamel.yaml 未安装"
        try:
            # 备份
            bak = self.config_path.with_suffix(".yaml.bak")
            if self.config_path.exists():
                bak.write_text(self.config_path.read_text(encoding="utf-8"), encoding="utf-8")
            with self.config_path.open("w", encoding="utf-8") as f:
                y.dump(data, f)
            return None
        except Exception as ex:
            return f"写入失败: {ex}"

    @staticmethod
    def _get_feed_list(data: Dict) -> List[Dict]:
        rss = data.get("rss") or {}
        feeds = rss.get("feeds")
        if not isinstance(feeds, list):
            return []
        return feeds

    @staticmethod
    def _set_feed_list(data: Dict, feeds: List[Dict]) -> None:
        data.setdefault("rss", {})["feeds"] = feeds

    # ────────────── 公开工具 ──────────────

    def add_feed(
        self,
        url: str,
        name: str,
        feed_id: Optional[str] = None,
        enabled: bool = True,
        max_age_days: Optional[int] = None,
    ) -> Dict:
        """把一个微信公众号 RSS URL 加到 Argus config.yaml"""
        if not url or not urlparse(url).scheme:
            return _err("url 必须是合法 URL", code="INVALID_PARAM")
        if not name or not name.strip():
            return _err("name 不能为空", code="INVALID_PARAM")

        # 生成 id
        if not feed_id:
            # 尝试从 URL 末段生成
            tail = urlparse(url).path.rstrip("/").split("/")[-1] or "feed"
            slug = re.sub(r"[^a-zA-Z0-9_-]", "-", tail).strip("-")[:40] or "feed"
            feed_id = f"wechat-{slug}"
        if not _ID_RE.match(feed_id):
            return _err(f"feed_id '{feed_id}' 非法 (字母数字下划线横线, <=49 位)",
                        code="INVALID_PARAM")

        data, err = self._load_yaml()
        if err:
            return _err(err, code="CONFIG_ERROR")

        feeds = self._get_feed_list(data)
        if any((f.get("id") == feed_id) or (f.get("url") == url) for f in feeds):
            return _err(
                f"feed 已存在 (id={feed_id} 或 url 重复)", code="DUPLICATE",
                existing_ids=[f.get("id") for f in feeds if f.get("url") == url or f.get("id") == feed_id],
            )

        entry: Dict[str, Any] = {
            "id": feed_id,
            "name": name,
            "url": url,
        }
        if not enabled:
            entry["enabled"] = False
        if max_age_days is not None:
            entry["max_age_days"] = int(max_age_days)

        feeds.append(entry)
        self._set_feed_list(data, feeds)
        err = self._write_yaml(data)
        if err:
            return _err(err, code="WRITE_ERROR")
        return _ok(
            {"id": feed_id, "name": name, "url": url, "config": str(self.config_path)},
            total_feeds=len(feeds),
        )

    def list_feeds(self, only_wechat: bool = True) -> Dict:
        """列出 config.yaml 中的 feed (默认只列微信相关)"""
        data, err = self._load_yaml()
        if err:
            return _err(err, code="CONFIG_ERROR")
        feeds = self._get_feed_list(data)
        if only_wechat:
            def is_wechat(f: Dict) -> bool:
                fid = (f.get("id") or "").lower()
                name = (f.get("name") or "").lower()
                url = (f.get("url") or "").lower()
                return (
                    fid.startswith("wechat")
                    or "wechat" in url
                    or "werss" in url
                    or "公众号" in f.get("name", "")
                    or "mp.weixin.qq.com" in url
                )
            feeds = [f for f in feeds if is_wechat(f)]
        out = [
            {"id": f.get("id"), "name": f.get("name"), "url": f.get("url"),
             "enabled": f.get("enabled", True)}
            for f in feeds
        ]
        return _ok({"feeds": out}, count=len(out), only_wechat=only_wechat)

    def remove_feed(self, feed_id: str) -> Dict:
        data, err = self._load_yaml()
        if err:
            return _err(err, code="CONFIG_ERROR")
        feeds = self._get_feed_list(data)
        new_feeds = [f for f in feeds if f.get("id") != feed_id]
        if len(new_feeds) == len(feeds):
            return _err(f"未找到 feed_id={feed_id}", code="NOT_FOUND")
        self._set_feed_list(data, new_feeds)
        err = self._write_yaml(data)
        if err:
            return _err(err, code="WRITE_ERROR")
        return _ok(
            {"removed": feed_id, "remaining": len(new_feeds)}
        )
