"""
飞书机器人反向通道 - 接收群/私聊消息, 路由到 Argus MCP 工具

架构:
    飞书群/私聊 @Argus 发消息
        → 飞书云 POST 事件到 https://<cloudflare-tunnel>/feishu/event
        → Starlette 接收, 校验 token
        → 解析命令(去掉 @mention 前缀)
        → 路由到 MCP 工具
        → 用 tenant_access_token 发回复

环境变量:
    FEISHU_APP_ID             应用 App ID
    FEISHU_APP_SECRET         应用 App Secret
    FEISHU_VERIFICATION_TOKEN 校验 token (明文事件必填)
    FEISHU_ENCRYPT_KEY        加密 key (如果订阅用"加密模式"填, 否则留空)
    FEISHU_BOT_PORT           本地端口, 默认 6600
    FEISHU_BOT_HOST           监听地址, 默认 127.0.0.1

启动: scripts/start-feishu-bot.sh bg
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import requests
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route


log = logging.getLogger("argus.feishu_bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# ════════════════════════════════════════════════════════════════
# 配置
# ════════════════════════════════════════════════════════════════

APP_ID = os.environ.get("FEISHU_APP_ID", "")
APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
VERIFY_TOKEN = os.environ.get("FEISHU_VERIFICATION_TOKEN", "")
ENCRYPT_KEY = os.environ.get("FEISHU_ENCRYPT_KEY", "")
PORT = int(os.environ.get("FEISHU_BOT_PORT", "6600"))
HOST = os.environ.get("FEISHU_BOT_HOST", "127.0.0.1")


# ════════════════════════════════════════════════════════════════
# Tenant Access Token 缓存 (2h 有效, 提前 5 分钟续期)
# ════════════════════════════════════════════════════════════════

_token_lock = threading.Lock()
_token: Dict[str, Any] = {"value": None, "expires_at": 0}


def get_tenant_access_token() -> Optional[str]:
    if not APP_ID or not APP_SECRET:
        log.warning("FEISHU_APP_ID/SECRET 未配置, 无法获取 token")
        return None
    with _token_lock:
        now = time.time()
        if _token["value"] and _token["expires_at"] > now + 300:
            return _token["value"]
        try:
            r = requests.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": APP_ID, "app_secret": APP_SECRET},
                timeout=10,
            )
            data = r.json()
            if data.get("code") != 0:
                log.error("获取 tenant_access_token 失败: %s", data)
                return None
            _token["value"] = data["tenant_access_token"]
            _token["expires_at"] = now + int(data.get("expire", 7200))
            return _token["value"]
        except Exception as ex:
            log.error("获取 tenant_access_token 异常: %s", ex)
            return None


# ════════════════════════════════════════════════════════════════
# AES 解密 (可选, 只有飞书"加密模式"才用)
# ════════════════════════════════════════════════════════════════

def _decrypt_feishu(encrypted: str, key: str) -> Dict:
    """飞书加密算法: AES-256-CBC, key = SHA256(ENCRYPT_KEY), iv = 前 16 字节"""
    from Crypto.Cipher import AES  # type: ignore
    raw = base64.b64decode(encrypted)
    iv = raw[:16]
    ct = raw[16:]
    aes_key = hashlib.sha256(key.encode()).digest()
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    pt = cipher.decrypt(ct)
    # PKCS7 unpad
    pt = pt[:-pt[-1]]
    return json.loads(pt.decode("utf-8"))


# ════════════════════════════════════════════════════════════════
# 命令路由
# ════════════════════════════════════════════════════════════════

COMMANDS = {}  # name → handler(arg: str) -> str


def command(name: str, alias: Optional[list] = None, desc: str = ""):
    """装饰器: 注册命令"""
    def deco(fn: Callable):
        COMMANDS[name] = {"handler": fn, "desc": desc}
        for a in alias or []:
            COMMANDS[a] = {"handler": fn, "desc": desc, "alias_of": name}
        return fn
    return deco


def _get_tools_lazy():
    """懒加载 MCP 工具实例"""
    from argus_server.server import _get_tools
    return _get_tools()


@command("帮助", alias=["help", "?", "菜单"], desc="显示所有可用命令")
def cmd_help(arg: str) -> str:
    lines = ["**Argus 机器人 · 可用命令**", ""]
    seen = set()
    for name, info in COMMANDS.items():
        if info.get("alias_of"):
            continue
        if name in seen:
            continue
        seen.add(name)
        lines.append(f"- `{name}` — {info.get('desc', '')}")
    lines.append("")
    lines.append("_用法: @Argus <命令> [参数]。例: `@Argus 搜 AI 监管`_")
    return "\n".join(lines)


@command("搜", alias=["查", "search", "搜索"], desc="BM25 全文搜索最近 7 天")
def cmd_search(arg: str) -> str:
    arg = arg.strip()
    if not arg:
        return "用法: `搜 <关键词>`,例 `搜 AI 监管`"
    t = _get_tools_lazy()
    res = t['semantic'].search(query=arg, window_days=7, limit=10)
    if not res.get("success"):
        return f"❌ 搜索失败: {(res.get('error') or {}).get('message')}"
    hits = (res.get("data") or {}).get("results") or []
    if not hits:
        return f"未找到 \"{arg}\" 相关内容 (最近 7 天)"
    lines = [f"**🔍 搜索 \"{arg}\"** · 命中 {len(hits)} 条", ""]
    for h in hits[:8]:
        title = h["title"]
        if len(title) > 50:
            title = title[:50] + "…"
        line = f"- `{h['platform']}` {title}"
        if h.get("url"):
            line = f"- `{h['platform']}` [{title}]({h['url']})"
        lines.append(line)
    return "\n".join(lines)


@command("早报", alias=["brief", "简报"], desc="立即推送今日早报(同日重复推)")
def cmd_brief(arg: str) -> str:
    t = _get_tools_lazy()
    res = t['daily_brief'].render(top_keywords=8, top_per_platform=2, max_platforms=6)
    if not res.get("success"):
        return f"❌ {(res.get('error') or {}).get('message')}"
    return (res.get("data") or {}).get("content", "(空)")


@command("异常", alias=["anomaly", "突发"], desc="检测过去 14 天内的突发话题")
def cmd_anomaly(arg: str) -> str:
    t = _get_tools_lazy()
    res = t['ai_analytics'].detect_anomaly(lookback_days=14, z_threshold=2.0, top_n=10)
    if not res.get("success"):
        return f"❌ {(res.get('error') or {}).get('message')}"
    anomalies = (res.get("data") or {}).get("anomalies") or []
    if not anomalies:
        return "未检测到异常话题 (可能数据连续性不足,需累积 3 天以上)"
    lines = [f"**⚡ 突发话题 Top {len(anomalies)}**", ""]
    for a in anomalies[:10]:
        trend = {"spike": "📈", "decline": "📉", "new_emergence": "🆕"}.get(a.get("trend"), "")
        lines.append(
            f"- {trend} **{a['keyword']}**  z={a['z_score']}  今日 {a['latest_count']} / 基线 {a['baseline_mean']}"
        )
    return "\n".join(lines)


@command("热词", alias=["trending", "趋势"], desc="今日 Top 热词")
def cmd_trending(arg: str) -> str:
    t = _get_tools_lazy()
    res = t['daily_brief'].render(top_keywords=15, top_per_platform=0, max_platforms=0)
    if not res.get("success"):
        return f"❌ {(res.get('error') or {}).get('message')}"
    return (res.get("data") or {}).get("content", "(空)")


@command("状态", alias=["status", "健康", "health"], desc="系统健康检查")
def cmd_health(arg: str) -> str:
    t = _get_tools_lazy()
    res = t['health'].system_health()
    checks = (res.get("data") or {}).get("checks", {})
    lines = ["**🏥 Argus 状态**", ""]
    for name, c in checks.items():
        icon = "✅" if c.get("ok") else "❌"
        detail = ""
        if "age_hours" in c:
            detail = f" · 数据 {c['age_hours']}h 前"
        elif "doc_count" in c:
            detail = f" · {c['doc_count']} 条"
        elif "status_code" in c:
            detail = f" · HTTP {c['status_code']}"
        elif "free_gb" in c:
            detail = f" · {c['free_gb']} GB 空闲"
        elif "count" in c:
            detail = f" · {c['count']}"
        lines.append(f"- {icon} {name}{detail}")
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════
# 发回复
# ════════════════════════════════════════════════════════════════

def send_reply(chat_id: str, content_md: str) -> Dict:
    token = get_tenant_access_token()
    if not token:
        return {"ok": False, "reason": "no_token"}
    payload = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps({
            "schema": "2.0",
            "body": {
                "elements": [{"tag": "markdown", "content": content_md}]
            },
        }, ensure_ascii=False),
    }
    try:
        r = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
            timeout=15,
        )
        data = r.json()
        return {"ok": data.get("code") == 0, "code": data.get("code"), "msg": data.get("msg")}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


# ════════════════════════════════════════════════════════════════
# 解析消息 + 路由
# ════════════════════════════════════════════════════════════════

_AT_MENTION_RE = re.compile(r"^@_user_\d+\s*")


def parse_command(text: str) -> Tuple[str, str]:
    """去掉 @mention 前缀, 返回 (command, arg)"""
    text = text.strip()
    # 去掉飞书格式的 @mention (群消息才有, 私聊直接是内容)
    text = _AT_MENTION_RE.sub("", text)
    text = text.strip()
    if not text:
        return "", ""
    parts = text.split(maxsplit=1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""
    return cmd, arg


def handle_message_event(event_body: Dict) -> None:
    """处理 im.message.receive_v1, 在后台线程跑(避免阻塞回调)"""
    try:
        event = event_body.get("event") or {}
        msg = event.get("message") or {}
        chat_id = msg.get("chat_id")
        chat_type = msg.get("chat_type", "p2p")
        msg_type = msg.get("message_type")
        if msg_type != "text":
            return

        content_raw = msg.get("content", "")
        try:
            content = json.loads(content_raw)
        except Exception:
            return
        text = content.get("text", "")

        # 群消息: 必须 @ 机器人才响应; 私聊: 直接响应
        if chat_type == "group":
            mentions = msg.get("mentions") or []
            if not any(m.get("name") in ("Argus", "argus") for m in mentions):
                # 没 @ 机器人, 忽略
                return

        cmd, arg = parse_command(text)
        if not cmd:
            return

        info = COMMANDS.get(cmd)
        if info is None:
            reply = f"未知命令 `{cmd}`。发送 `帮助` 查看所有命令。"
        else:
            try:
                reply = info["handler"](arg)
            except Exception as ex:
                log.exception("命令 %s 处理异常", cmd)
                reply = f"❌ 命令执行异常: {type(ex).__name__}: {ex}"

        result = send_reply(chat_id, reply)
        log.info("回复 chat=%s cmd=%s ok=%s", chat_id, cmd, result.get("ok"))
    except Exception:
        log.exception("handle_message_event error")


# ════════════════════════════════════════════════════════════════
# Starlette endpoints
# ════════════════════════════════════════════════════════════════

async def health(_req: Request) -> PlainTextResponse:
    return PlainTextResponse("argus-feishu-bot ok")


async def event_handler(req: Request) -> JSONResponse:
    raw = await req.body()
    try:
        body = json.loads(raw)
    except Exception:
        return JSONResponse({"error": "bad_json"}, status_code=400)

    # 解密(如果启用加密模式)
    if "encrypt" in body:
        if not ENCRYPT_KEY:
            return JSONResponse({"error": "ENCRYPT_KEY_not_set"}, status_code=400)
        try:
            body = _decrypt_feishu(body["encrypt"], ENCRYPT_KEY)
        except Exception as ex:
            log.exception("解密失败")
            return JSONResponse({"error": f"decrypt_failed: {ex}"}, status_code=400)

    # URL 校验挑战(首次配置时飞书发来)
    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge", "")})

    # 事件回调 (schema 2.0)
    header = body.get("header") or {}
    # 校验 token
    if VERIFY_TOKEN and header.get("token") != VERIFY_TOKEN:
        log.warning("token 校验失败")
        return JSONResponse({"error": "invalid_token"}, status_code=401)

    event_type = header.get("event_type")
    if event_type == "im.message.receive_v1":
        # 后台处理, 立即返回 (飞书要求 3s 内 ack)
        threading.Thread(target=handle_message_event, args=(body,), daemon=True).start()
        return JSONResponse({"ok": True})

    log.info("未处理的事件类型: %s", event_type)
    return JSONResponse({"ok": True})


def create_app() -> Starlette:
    return Starlette(routes=[
        Route("/", health),
        Route("/health", health),
        Route("/feishu/event", event_handler, methods=["POST"]),
    ])


app = create_app()


def main() -> None:
    import uvicorn
    log.info("启动 Argus 飞书机器人 @ %s:%s", HOST, PORT)
    if not APP_ID or not APP_SECRET:
        log.warning("⚠️  FEISHU_APP_ID / FEISHU_APP_SECRET 未设置, 将无法回复消息")
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
