"""
多渠道消息分流路由 - Batch 14 交付

典型场景: "技术话题推到 #tech 飞书群, 财经话题推到 #finance 群, 安全漏洞推到 #security 群"

DSL: config/notification_routes.yaml
    routes:
      - name: tech
        webhooks:
          - name: feishu-tech
            channel: feishu
            webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/tech-xxx"
        keywords: ["AI", "GPU", "Nvidia", "LLM", "Kubernetes"]
        topics: ["tech"]

      - name: finance
        webhooks:
          - channel: feishu
            webhook_url: "https://..."
        keywords: ["股票", "加息", "降息", "GDP", "财报"]

      - name: security
        webhooks:
          - channel: feishu
            webhook_url: "https://..."
          - channel: bark
            webhook_url: "https://api.day.app/xxx"
        keywords: ["CVE", "漏洞", "RCE", "零日", "ransomware"]

工具:
    route_add(name, keywords, webhooks)
    route_list()
    route_remove(name)
    route_test(text)                # 返回匹配到的路由, 不真发
    route_dispatch(text, title)     # 实际按路由分发
"""

from __future__ import annotations

import re
import base64
import hashlib
import hmac
import time as _time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


def _feishu_sign(secret: str, timestamp: int) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    mac = hmac.new(string_to_sign.encode("utf-8"),
                   digestmod=hashlib.sha256).digest()
    return base64.b64encode(mac).decode("utf-8")


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "ROUTE_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,48}$")


def _yaml():
    from ruamel.yaml import YAML
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 200
    return y


class RouterTools:
    """多账号/多群飞书等通知分流"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self.routes_path = self.project_root / "config" / "notification_routes.yaml"
        self.routes_path.parent.mkdir(parents=True, exist_ok=True)

    # ────────────── 配置 ──────────────

    def _load(self) -> List[Dict]:
        if not self.routes_path.exists():
            return []
        try:
            y = _yaml()
            with self.routes_path.open("r", encoding="utf-8") as f:
                data = y.load(f) or {}
            routes = data.get("routes") or []
            return [dict(r) for r in routes if isinstance(r, dict)]
        except Exception:
            return []

    def _save(self, routes: List[Dict]) -> None:
        y = _yaml()
        with self.routes_path.open("w", encoding="utf-8") as f:
            y.dump({"routes": routes}, f)

    # ────────────── CRUD ──────────────

    def add(
        self,
        name: str,
        webhooks: List[Dict],
        keywords: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
        match_mode: str = "any",
        enabled: bool = True,
        description: str = "",
    ) -> Dict:
        if not _NAME_RE.match(name or ""):
            return _err("name 必须以字母开头, 2-49 位字母数字下划线横线", code="INVALID_NAME")
        if not webhooks or not isinstance(webhooks, list):
            return _err("webhooks 必须是非空数组", code="INVALID_PARAM")
        for wh in webhooks:
            if not isinstance(wh, dict) or not wh.get("webhook_url") or not wh.get("channel"):
                return _err("每个 webhook 需要 {channel, webhook_url}", code="INVALID_PARAM")
        if match_mode not in ("any", "all"):
            return _err("match_mode 必须是 any / all", code="INVALID_PARAM")
        if not keywords and not topics:
            return _err("keywords 或 topics 至少需要一个", code="INVALID_PARAM")

        routes = self._load()
        if any(r.get("name") == name for r in routes):
            return _err(f"路由 {name} 已存在", code="DUPLICATE")

        routes.append({
            "name": name,
            "description": description,
            "enabled": enabled,
            "match_mode": match_mode,
            "keywords": list(keywords or []),
            "topics": list(topics or []),
            "webhooks": webhooks,
        })
        self._save(routes)
        return _ok({"name": name, "total": len(routes)})

    def list_routes(self, include_urls: bool = False) -> Dict:
        routes = self._load()
        out = []
        for r in routes:
            webhooks = r.get("webhooks") or []
            wh_view = [
                {
                    "name": w.get("name"),
                    "channel": w.get("channel"),
                    "webhook_url": (w.get("webhook_url") if include_urls
                                    else (w.get("webhook_url", "")[:30] + "...")),
                }
                for w in webhooks
            ]
            out.append({
                "name": r.get("name"),
                "description": r.get("description", ""),
                "enabled": r.get("enabled", True),
                "match_mode": r.get("match_mode", "any"),
                "keywords": r.get("keywords") or [],
                "topics": r.get("topics") or [],
                "webhooks": wh_view,
            })
        return _ok({"routes": out}, count=len(out))

    def remove(self, name: str) -> Dict:
        routes = self._load()
        new = [r for r in routes if r.get("name") != name]
        if len(new) == len(routes):
            return _err(f"未找到路由 {name}", code="NOT_FOUND")
        self._save(new)
        return _ok({"removed": name, "remaining": len(new)})

    # ────────────── 匹配 + 分发 ──────────────

    def _match(self, route: Dict, text: str, topics: Optional[List[str]] = None) -> bool:
        """一条消息是否命中该路由"""
        if not route.get("enabled", True):
            return False
        kws = [k.lower() for k in route.get("keywords") or []]
        rtopics = set(route.get("topics") or [])
        text_lower = (text or "").lower()
        mode = route.get("match_mode", "any")

        kw_hits = [k for k in kws if k in text_lower]
        topic_hits = list(rtopics.intersection(set(topics or [])))

        if mode == "all":
            if kws and len(kw_hits) < len(kws):
                return False
            if rtopics and len(topic_hits) < len(rtopics):
                return False
            return bool(kw_hits or topic_hits)
        # any 模式
        return bool(kw_hits or topic_hits)

    def test(self, text: str, topics: Optional[List[str]] = None) -> Dict:
        """干跑: 看命中哪些路由"""
        routes = self._load()
        matched = []
        for r in routes:
            if self._match(r, text, topics):
                matched.append({
                    "name": r.get("name"),
                    "webhooks_count": len(r.get("webhooks") or []),
                })
        return _ok({"matched": matched, "text": text[:100]}, count=len(matched))

    def dispatch(
        self,
        text: str,
        title: str = "Argus 通知",
        topics: Optional[List[str]] = None,
    ) -> Dict:
        """按所有匹配的路由分发消息"""
        routes = self._load()
        dispatched: List[Dict] = []
        errors: List[Dict] = []

        for r in routes:
            if not self._match(r, text, topics):
                continue
            for wh in r.get("webhooks") or []:
                ch = wh.get("channel")
                url = wh.get("webhook_url")
                sec = wh.get("secret")
                try:
                    sent = self._send_direct(ch, url, title, text, secret=sec)
                    dispatched.append({
                        "route": r.get("name"),
                        "webhook_name": wh.get("name") or "(anon)",
                        "channel": ch,
                        "ok": sent.get("ok"),
                        "status_code": sent.get("status_code"),
                    })
                    if not sent.get("ok"):
                        errors.append({
                            "route": r.get("name"),
                            "channel": ch,
                            "error": sent.get("error"),
                        })
                except Exception as ex:
                    errors.append({
                        "route": r.get("name"),
                        "channel": ch,
                        "error": f"{type(ex).__name__}: {ex}",
                    })

        return _ok(
            {
                "dispatched": dispatched,
                "errors": errors,
            },
            matched_routes=len({d['route'] for d in dispatched}),
            total_sends=len(dispatched),
            error_count=len(errors),
        )

    # ────────────── 直连 webhook (不走 Argus notification) ──────────────

    @staticmethod
    def _send_direct(channel: str, webhook_url: str, title: str, content: str,
                     secret: Optional[str] = None) -> Dict:
        """直接对 webhook 发 HTTP POST. 支持 feishu/dingtalk/wework/slack/generic"""
        try:
            if channel == "feishu":
                payload = {
                    "msg_type": "interactive",
                    "card": {
                        "config": {"wide_screen_mode": True},
                        "header": {
                            "title": {"tag": "plain_text", "content": title},
                            "template": "blue",
                        },
                        "elements": [
                            {"tag": "markdown", "content": content}
                        ],
                    },
                }
                if secret:
                    ts = int(_time.time())
                    payload["timestamp"] = str(ts)
                    payload["sign"] = _feishu_sign(secret, ts)
            elif channel == "dingtalk":
                payload = {
                    "msgtype": "markdown",
                    "markdown": {"title": title, "text": f"# {title}\n\n{content}"},
                }
            elif channel == "wework":
                payload = {
                    "msgtype": "markdown",
                    "markdown": {"content": f"# {title}\n\n{content}"},
                }
            elif channel == "slack":
                payload = {"text": f"*{title}*\n{content}"}
            elif channel == "bark":
                import urllib.parse as _up
                # bark 是 GET /{key}/{title}/{body}
                url = webhook_url.rstrip("/") + "/" + _up.quote(title) + "/" + _up.quote(content[:1500])
                r = requests.get(url, timeout=10)
                return {"ok": r.ok, "status_code": r.status_code}
            elif channel in ("ntfy", "generic"):
                payload = {"title": title, "message": content}
            else:
                return {"ok": False, "error": f"未支持 channel {channel}"}

            r = requests.post(webhook_url, json=payload, timeout=15)
            return {
                "ok": r.ok and (r.status_code < 300),
                "status_code": r.status_code,
                "body_preview": r.text[:200],
            }
        except Exception as ex:
            return {"ok": False, "error": f"{type(ex).__name__}: {ex}"}
