"""
MCP 反向挂载 - Batch 5b 交付

让 Argus MCP server 作为 client 连外部 MCP server (stdio 子进程),
把外部工具以 "<prefix>__<tool>" 形式暴露给上游。

工具:
    mcp_proxy_add(name, command, args, env?)   注册一个外部 server
    mcp_proxy_list()                           列出所有已注册 + 是否在线
    mcp_proxy_remove(name)                     移除
    mcp_proxy_list_tools(name?)                列出外部暴露的工具
    mcp_proxy_call(name, tool, args)           调用外部工具

配置落盘到 output/mcp_proxies.json
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "MCP_PROXY_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,30}$")


class MCPProxyTools:
    """反向挂载外部 MCP server, 把它们的工具 proxy 出来"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self.config_path = self.project_root / "output" / "mcp_proxies.json"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config: Dict[str, Dict] = self._load_config()
        # 内存缓存: name → {tools: [...], last_seen_at}
        self._tool_cache: Dict[str, Dict] = {}

    # ────────────── 配置读写 ──────────────

    def _load_config(self) -> Dict[str, Dict]:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_config(self) -> None:
        self.config_path.write_text(
            json.dumps(self._config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ────────────── 公开方法 (同步, 内部跑 asyncio) ──────────────

    def add(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        description: str = "",
    ) -> Dict:
        if not _NAME_RE.match(name or ""):
            return _err("name 必须以字母开头, <=31 位字母数字下划线横线", code="INVALID_NAME")
        if not command:
            return _err("command 不能为空", code="INVALID_PARAM")

        self._config[name] = {
            "command": command,
            "args": list(args or []),
            "env": dict(env or {}),
            "description": description,
        }
        self._save_config()

        # 立即连接一次, 缓存 tool 列表
        try:
            tools = asyncio.run(self._fetch_tools(name))
            self._tool_cache[name] = {"tools": tools}
            return _ok(
                {"name": name, "tools_count": len(tools), "tools": [t["name"] for t in tools]},
                registered=True,
            )
        except Exception as ex:
            # 注册成功但启动失败, 返回警告
            return _ok(
                {"name": name, "tools_count": 0, "warning": f"启动失败: {ex}"},
                registered=True,
            )

    def remove(self, name: str) -> Dict:
        if name not in self._config:
            return _err(f"未找到 proxy: {name}", code="NOT_FOUND")
        self._config.pop(name, None)
        self._tool_cache.pop(name, None)
        self._save_config()
        return _ok({"name": name, "removed": True})

    def list_proxies(self) -> Dict:
        out = []
        for name, cfg in self._config.items():
            cached = self._tool_cache.get(name, {})
            out.append({
                "name": name,
                "command": cfg.get("command"),
                "args": cfg.get("args", []),
                "description": cfg.get("description", ""),
                "tools_cached": len(cached.get("tools", [])),
            })
        return _ok({"proxies": out}, count=len(out))

    def list_tools(self, name: Optional[str] = None, refresh: bool = False) -> Dict:
        """列出一个(或所有) proxy 上的工具"""
        names = [name] if name else list(self._config.keys())
        if name and name not in self._config:
            return _err(f"未找到 proxy: {name}", code="NOT_FOUND")

        result = {}
        for n in names:
            if refresh or n not in self._tool_cache:
                try:
                    tools = asyncio.run(self._fetch_tools(n))
                    self._tool_cache[n] = {"tools": tools}
                except Exception as ex:
                    result[n] = {"error": f"{type(ex).__name__}: {ex}", "tools": []}
                    continue
            result[n] = {"tools": self._tool_cache[n]["tools"]}
        return _ok(result, proxies=len(names))

    def call(self, name: str, tool: str, arguments: Optional[Dict] = None) -> Dict:
        if name not in self._config:
            return _err(f"未找到 proxy: {name}", code="NOT_FOUND")
        try:
            res = asyncio.run(self._call_tool(name, tool, arguments or {}))
            return _ok(res, proxy=name, tool=tool)
        except Exception as ex:
            return _err(f"{type(ex).__name__}: {ex}", code="UPSTREAM_ERROR", proxy=name, tool=tool)

    # ────────────── asyncio 实现 ──────────────

    def _build_params(self, name: str) -> StdioServerParameters:
        cfg = self._config[name]
        import os as _os
        base_env = _os.environ.copy()
        base_env.update(cfg.get("env") or {})
        # 把 ~/.local/bin 加到 PATH 以便 uv tool 装的工具能找到
        extra = str(Path.home() / ".local/bin")
        if extra not in base_env.get("PATH", ""):
            base_env["PATH"] = f"{extra}:{base_env.get('PATH', '')}"
        return StdioServerParameters(
            command=cfg["command"],
            args=cfg.get("args", []),
            env=base_env,
        )

    async def _fetch_tools(self, name: str) -> List[Dict]:
        params = self._build_params(name)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await asyncio.wait_for(session.initialize(), timeout=30)
                listing = await asyncio.wait_for(session.list_tools(), timeout=20)
                tools = []
                for t in getattr(listing, "tools", []) or []:
                    tools.append({
                        "name": getattr(t, "name", ""),
                        "description": getattr(t, "description", "") or "",
                        "input_schema": getattr(t, "inputSchema", None) or {},
                    })
                return tools

    async def _call_tool(self, name: str, tool: str, arguments: Dict) -> Any:
        params = self._build_params(name)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await asyncio.wait_for(session.initialize(), timeout=30)
                resp = await asyncio.wait_for(
                    session.call_tool(tool, arguments), timeout=120
                )
                # resp.content 是 list[TextContent|ImageContent|...]
                parts = []
                for c in getattr(resp, "content", []) or []:
                    if hasattr(c, "text"):
                        parts.append({"type": "text", "text": c.text})
                    elif hasattr(c, "data"):
                        parts.append({"type": getattr(c, "type", "blob"),
                                      "data_preview": str(c.data)[:200]})
                    else:
                        parts.append({"type": "unknown", "repr": repr(c)[:200]})
                return {
                    "is_error": getattr(resp, "isError", False),
                    "content": parts,
                }
