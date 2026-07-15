"""
外部 CLI 工具适配器 (jackwener's AI-agent CLI 套件)

Wrap four optional local CLIs plus one policy-disabled compatibility entry as MCP tools:

  - bili      (bilibili-cli)      B 站视频/用户/搜索/热榜/动态/字幕/AI 摘要
  - xhs       (xiaohongshu-cli)   小红书搜索/笔记/用户/话题/热榜/评论/发帖
  - twitter   (twitter-cli)       Twitter/X 时间线/书签/搜索/用户/发推
  - tg        (kabi-tg-cli)       Telegram 本地 SQLite 同步/搜索/导出/监控
  - discord   (disabled)          Reserved compatibility entry; user-token automation is unsupported

设计理念:
  1. 每个 CLI 一个通用 run_* 工具, 传 subcommand + args → 返回 YAML/JSON envelope
  2. Supported CLIs are optional uv tools discovered from PATH
  3. 输出统一 envelope {ok, schema_version, data, error}

参考文档:
  - 各工具的 /tmp/search_tools/<tool>-main/SKILL.md (Agent 使用指南)
  - 各工具的 /tmp/search_tools/<tool>-main/SCHEMA.md (输出格式)
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
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
_XHS_CONFIG_DIR = ".xiaohongshu-cli"
_XHS_COOKIE_FILE = "cookies.json"
_DISCORD_POLICY_MESSAGE = (
    "Discord 普通用户 token 自动化（self-bot）不受支持，因为它违反 Discord 平台规则。"
    "请改用 Discord Developer Portal 创建的 Bot 或 OAuth2 应用。"
)


class CLIToolsAdapter:
    """外部 CLI 工具统一调用接口"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root
        self._user_home = Path.home()
        self._xhs_runtime = tempfile.TemporaryDirectory(
            prefix="argus-xhs-", ignore_cleanup_errors=True
        )
        self._xhs_runtime_home = Path(self._xhs_runtime.name)
        self._xhs_runtime_home.chmod(0o700)
        # 确保子进程能找到 uv tool 装的 CLI
        self._env = os.environ.copy()
        if _UV_TOOL_BIN not in self._env.get("PATH", ""):
            self._env["PATH"] = f"{_UV_TOOL_BIN}:{self._env.get('PATH', '')}"

    def __del__(self):
        runtime = getattr(self, "_xhs_runtime", None)
        if runtime is not None:
            runtime.cleanup()

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
        if binary == "discord":
            return _err(
                _DISCORD_POLICY_MESSAGE,
                code="POLICY_UNSUPPORTED",
                binary="discord",
                replacement="discord_bot_or_oauth2",
            )
        if not shutil.which(binary, path=self._env["PATH"]):
            return _err(
                f"CLI '{binary}' 未安装或不在 PATH 中. "
                f"安装: uv tool install {self._pkg_for(binary)}",
                code="NOT_INSTALLED",
                binary=binary,
            )
        command_env = self._env
        if binary == "xhs":
            command_env, setup_error = self._prepare_xhs_runtime()
            if setup_error:
                return setup_error
        cmd = [binary]
        if subcommand:
            cmd.append(subcommand)
        cmd.extend(args or [])
        # 强制 YAML 输出 (agent 友好)
        if "--yaml" not in cmd and "--json" not in cmd:
            cmd.append("--yaml")

        try:
            stdin_args = (
                {"stdin": subprocess.DEVNULL}
                if input_text is None
                else {"input": input_text}
            )
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=command_env,
                **stdin_args,
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
            friendly_error = self._friendly_cli_error(
                binary=binary,
                subcommand=subcommand,
                returncode=result.returncode,
                stderr=stderr,
            )
            if friendly_error:
                return friendly_error
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
            friendly_error = self._friendly_cli_error(
                binary=binary,
                subcommand=subcommand,
                returncode=result.returncode,
                stderr=stdout,
            )
            if friendly_error:
                return friendly_error
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
                "error": self._normalize_cli_envelope_error(binary, parsed.get("error") or {}),
                "summary": {"binary": binary, "subcommand": subcommand},
            }
        # 非 envelope 输出, 原样返回
        return _ok({"raw": parsed}, binary=binary, subcommand=subcommand)

    def _prepare_xhs_runtime(self) -> tuple[Dict[str, str], Optional[Dict]]:
        """Give xhs a private writable HOME while reusing the user's saved login."""
        source_cookie = self._user_home / _XHS_CONFIG_DIR / _XHS_COOKIE_FILE
        if not source_cookie.is_file():
            return self._env, _err(
                "xhs CLI 尚无可复用的本地登录。请先在本机浏览器登录小红书并运行 xhs login。",
                code="AUTH_REQUIRED",
                binary="xhs",
                action_required="manual_login_refresh",
            )

        runtime_config = self._xhs_runtime_home / _XHS_CONFIG_DIR
        runtime_cookie = runtime_config / _XHS_COOKIE_FILE
        try:
            runtime_config.mkdir(mode=0o700, parents=True, exist_ok=True)
            runtime_config.chmod(0o700)
            if (
                not runtime_cookie.exists()
                or source_cookie.stat().st_mtime_ns > runtime_cookie.stat().st_mtime_ns
            ):
                shutil.copy2(source_cookie, runtime_cookie)
            runtime_cookie.chmod(0o600)
        except OSError:
            return self._env, _err(
                "xhs CLI 无法准备隔离的本地登录运行目录。",
                code="AUTH_STORAGE_UNAVAILABLE",
                binary="xhs",
                action_required="manual_login_or_local_cookie_permission",
            )

        command_env = self._env.copy()
        command_env["HOME"] = str(self._xhs_runtime_home)
        return command_env, None

    def _friendly_cli_error(
        self,
        binary: str,
        subcommand: Optional[str],
        returncode: int,
        stderr: str,
    ) -> Optional[Dict]:
        if binary != "xhs":
            return None
        text = stderr or ""
        lowered = text.lower()
        if ".xiaohongshu-cli" in text and "permissionerror" in lowered:
            return _err(
                "xhs CLI 无法访问本地小红书登录 cookie 存储。请在本机终端/浏览器完成小红书登录, 并允许访问 ~/.xiaohongshu-cli/cookies.json。",
                code="AUTH_STORAGE_UNAVAILABLE",
                binary=binary,
                subcommand=subcommand,
                returncode=returncode,
                action_required="manual_login_or_local_cookie_permission",
            )
        if "login" in lowered or "auth" in lowered or "cookie" in lowered:
            return _err(
                "xhs CLI 登录态不可用或已过期。请在本机浏览器/CLI 手动刷新小红书登录后重试。",
                code="AUTH_REQUIRED",
                binary=binary,
                subcommand=subcommand,
                returncode=returncode,
                action_required="manual_login_refresh",
            )
        if "traceback" in lowered:
            return _err(
                "xhs CLI 执行失败。请先运行 xhs_auth_status 查看安装和登录状态。",
                code="CLI_TRACEBACK",
                binary=binary,
                subcommand=subcommand,
                returncode=returncode,
            )
        return None

    def _normalize_cli_envelope_error(self, binary: str, error: Dict) -> Dict:
        if not isinstance(error, dict):
            return {"code": "cli_error", "message": str(error or "unknown")}
        if binary != "xhs":
            return error or {"code": "cli_error", "message": "unknown"}
        message = str(error.get("message") or error.get("detail") or "")
        code = str(error.get("code") or "cli_error")
        friendly = self._friendly_cli_error(
            binary=binary,
            subcommand=None,
            returncode=0,
            stderr=f"{code} {message}",
        )
        if friendly:
            return friendly["error"]
        return error or {"code": "cli_error", "message": "unknown"}

    @staticmethod
    def _pkg_for(binary: str) -> str:
        return {
            "bili": "bilibili-cli",
            "xhs": "xiaohongshu-cli",
            "twitter": "twitter-cli",
            "tg": "kabi-tg-cli",
        }.get(binary, binary)

    # ────────────────── 一键检查所有 CLI 认证状态 ──────────────────

    def check_cli_auth(self) -> Dict:
        """检查 5 个 CLI 的认证状态 + 安装情况"""
        statuses = {}
        for binary in ("bili", "xhs", "twitter", "tg", "discord"):
            if binary == "discord":
                statuses[binary] = {
                    "installed": bool(shutil.which(binary, path=self._env["PATH"])),
                    "supported": False,
                    "auth": None,
                    "error_code": "POLICY_UNSUPPORTED",
                    "hint": _DISCORD_POLICY_MESSAGE,
                }
                continue
            if not shutil.which(binary, path=self._env["PATH"]):
                statuses[binary] = {
                    "installed": False,
                    "supported": True,
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
                    "supported": True,
                    "auth": bool(data.get("authenticated")),
                    "user": data.get("user"),
                }
            else:
                err = r.get("error", {})
                statuses[binary] = {
                    "installed": True,
                    "supported": True,
                    "auth": False,
                    "error_code": err.get("code"),
                    "hint": err.get("message", "")[:200],
                }
        return _ok(statuses, cli_count=len(statuses))

    def xhs_auth_status(self, timeout: int = 20) -> Dict:
        """Check xhs installation and login readiness without bypassing authentication."""
        if not shutil.which("xhs", path=self._env["PATH"]):
            return _ok(
                {
                    "installed": False,
                    "authenticated": False,
                    "status": "not_installed",
                    "action_required": "install_xhs_cli",
                    "hint": "uv tool install xiaohongshu-cli",
                },
                binary="xhs",
            )

        r = self._exec("xhs", "status", [], timeout=timeout)
        if r.get("success"):
            data = r.get("data") or {}
            authenticated = bool(data.get("authenticated"))
            return _ok(
                {
                    "installed": True,
                    "authenticated": authenticated,
                    "status": "ready" if authenticated else "needs_login",
                    "user": data.get("user"),
                    "raw": data,
                    "action_required": None if authenticated else "manual_login_refresh",
                },
                binary="xhs",
            )

        error = r.get("error") or {}
        status = "needs_login" if error.get("code") in ("AUTH_REQUIRED", "AUTH_STORAGE_UNAVAILABLE") else "error"
        return _ok(
            {
                "installed": True,
                "authenticated": False,
                "status": status,
                "error": error,
                "action_required": error.get("action_required") or "manual_check",
            },
            binary="xhs",
        )

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
        """Reject Discord user-token automation while preserving the MCP contract."""
        return _err(
            _DISCORD_POLICY_MESSAGE,
            code="POLICY_UNSUPPORTED",
            binary="discord",
            replacement="discord_bot_or_oauth2",
        )
