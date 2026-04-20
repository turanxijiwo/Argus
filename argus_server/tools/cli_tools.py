"""
外部 CLI 工具适配器 (jackwener's AI-agent CLI 套件)

将 5 个本地安装的 CLI 工具包装为 MCP 工具:

  - bili      (bilibili-cli)      B 站视频/用户/搜索/热榜/动态/字幕/AI 摘要
  - xhs       (xiaohongshu-cli)   小红书搜索/笔记/用户/话题/热榜/评论/发帖
  - twitter   (twitter-cli)       Twitter/X 时间线/书签/搜索/用户/发推
  - tg        (kabi-tg-cli)       Telegram 本地 SQLite 同步/搜索/导出/监控
  - discord   (kabi-discord-cli)  Discord 本地同步/搜索/导出

设计理念:
  1. 每个 CLI 一个通用 run_* 工具, 传 subcommand + args → 返回 YAML/JSON envelope
  2. 所有 CLI 已通过 uv tool install 安装到 PATH
  3. 输出统一 envelope {ok, schema_version, data, error}

参考文档:
  - 各工具的 /tmp/search_tools/<tool>-main/SKILL.md (Agent 使用指南)
  - 各工具的 /tmp/search_tools/<tool>-main/SCHEMA.md (输出格式)
"""

import os
import shutil
import subprocess
from typing import Dict, List, Optional, Any

try:
    import yaml
except ImportError:
    yaml = None


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "CLI_ERROR", **extra) -> Dict:
    return {
        "success": False,
        "error": {"code": code, "message": message, **extra},
    }


# 添加 uv tool 的 bin 路径到 PATH
_UV_TOOL_BIN = os.path.expanduser("~/.local/bin")


class CLIToolsAdapter:
    """外部 CLI 工具统一调用接口"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root
        # 确保子进程能找到 uv tool 装的 CLI
        self._env = os.environ.copy()
        if _UV_TOOL_BIN not in self._env.get("PATH", ""):
            self._env["PATH"] = f"{_UV_TOOL_BIN}:{self._env.get('PATH', '')}"

    # ────────────────── 内部 helper ──────────────────

    def _exec(
        self,
        binary: str,
        subcommand: Optional[str],
        args: List[str],
        timeout: int = 60,
        input_text: Optional[str] = None,
    ) -> Dict:
        """通用 CLI 执行器. 自动加 --yaml, 解析 envelope."""
        if not shutil.which(binary, path=self._env["PATH"]):
            return _err(
                f"CLI '{binary}' 未安装或不在 PATH 中. "
                f"安装: uv tool install {self._pkg_for(binary)}",
                code="NOT_INSTALLED",
                binary=binary,
            )
        cmd = [binary]
        if subcommand:
            cmd.append(subcommand)
        cmd.extend(args or [])
        # 强制 YAML 输出 (agent 友好)
        if "--yaml" not in cmd and "--json" not in cmd:
            cmd.append("--yaml")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._env,
                input=input_text,
            )
        except subprocess.TimeoutExpired:
            return _err(
                f"{binary} 执行超时 ({timeout}s)", code="TIMEOUT", cmd=" ".join(cmd)
            )
        except Exception as ex:
            return _err(f"{binary} 启动失败: {ex}", code="EXEC_ERROR")

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        if not stdout:
            return _err(
                f"{binary} 无输出" + (f"; stderr: {stderr[:300]}" if stderr else ""),
                code="NO_OUTPUT",
                returncode=result.returncode,
            )

        # 解析 YAML envelope
        if not yaml:
            return _ok(
                {"raw_stdout": stdout[:8000], "stderr": stderr[:500]},
                binary=binary, subcommand=subcommand,
                note="PyYAML 未安装, 返回原始 stdout",
            )
        try:
            parsed = yaml.safe_load(stdout)
        except Exception as ex:
            return _err(
                f"{binary} 输出不是有效 YAML: {ex}",
                code="PARSE_ERROR",
                stdout_preview=stdout[:500],
            )

        # 透传 CLI 的 envelope
        if isinstance(parsed, dict) and "ok" in parsed:
            if parsed.get("ok"):
                return {
                    "success": True,
                    "summary": {
                        "binary": binary,
                        "subcommand": subcommand,
                        "schema_version": parsed.get("schema_version"),
                    },
                    "data": parsed.get("data"),
                    "pagination": parsed.get("pagination"),
                }
            return {
                "success": False,
                "error": parsed.get("error") or {"code": "cli_error", "message": "unknown"},
                "summary": {"binary": binary, "subcommand": subcommand},
            }
        # 非 envelope 输出, 原样返回
        return _ok({"raw": parsed}, binary=binary, subcommand=subcommand)

    @staticmethod
    def _pkg_for(binary: str) -> str:
        return {
            "bili": "bilibili-cli",
            "xhs": "xiaohongshu-cli",
            "twitter": "twitter-cli",
            "tg": "kabi-tg-cli",
            "discord": "kabi-discord-cli",
        }.get(binary, binary)

    # ────────────────── 一键检查所有 CLI 认证状态 ──────────────────

    def check_cli_auth(self) -> Dict:
        """检查 5 个 CLI 的认证状态 + 安装情况"""
        statuses = {}
        for binary in ("bili", "xhs", "twitter", "tg", "discord"):
            if not shutil.which(binary, path=self._env["PATH"]):
                statuses[binary] = {
                    "installed": False,
                    "auth": None,
                    "hint": f"uv tool install {self._pkg_for(binary)}",
                }
                continue
            # tg 的 status 可能卡网络, 限短超时
            timeout = 20 if binary != "tg" else 30
            r = self._exec(binary, "status", [], timeout=timeout)
            if r.get("success"):
                data = r.get("data") or {}
                statuses[binary] = {
                    "installed": True,
                    "auth": bool(data.get("authenticated")),
                    "user": data.get("user"),
                }
            else:
                err = r.get("error", {})
                statuses[binary] = {
                    "installed": True,
                    "auth": False,
                    "error_code": err.get("code"),
                    "hint": err.get("message", "")[:200],
                }
        return _ok(statuses, cli_count=len(statuses))

    # ────────────────── 5 个 CLI 通用包装 ──────────────────

    def run_bilibili(self, subcommand: str, args: Optional[List[str]] = None, timeout: int = 60) -> Dict:
        """执行 bili <subcommand> <args>"""
        return self._exec("bili", subcommand, args or [], timeout=timeout)

    def run_xhs(self, subcommand: str, args: Optional[List[str]] = None, timeout: int = 60) -> Dict:
        """执行 xhs <subcommand> <args>"""
        return self._exec("xhs", subcommand, args or [], timeout=timeout)

    def run_twitter(self, subcommand: str, args: Optional[List[str]] = None, timeout: int = 60) -> Dict:
        """执行 twitter <subcommand> <args>"""
        return self._exec("twitter", subcommand, args or [], timeout=timeout)

    def run_telegram(self, subcommand: str, args: Optional[List[str]] = None, timeout: int = 90) -> Dict:
        """执行 tg <subcommand> <args>"""
        return self._exec("tg", subcommand, args or [], timeout=timeout)

    def run_discord(self, subcommand: str, args: Optional[List[str]] = None, timeout: int = 60) -> Dict:
        """执行 discord <subcommand> <args>"""
        return self._exec("discord", subcommand, args or [], timeout=timeout)
