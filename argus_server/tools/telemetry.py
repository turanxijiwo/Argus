"""
工具调用遥测 - Batch 11 交付

记录每次 MCP tool 调用的 latency / success / error, 落盘到 JSONL,
提供一个 `tool_stats` MCP 工具查看统计(哪些工具被用得最多, 哪些经常失败)。

设计:
    - 装饰器 @traced("tool_name") 包 tools 实例方法
    - 不侵入 server.py 的 @mcp.tool 装饰 (MCP 框架内部实现)
    - 落盘: output/telemetry/tool_calls.jsonl (每天轮转)
"""

from __future__ import annotations

import json
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "TELEMETRY_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


class TelemetryStore:
    """JSONL 写入 + 内存聚合 (线程安全)"""

    _lock = threading.Lock()
    _instance: Optional["TelemetryStore"] = None

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self.dir = self.project_root / "output" / "telemetry"
        self.dir.mkdir(parents=True, exist_ok=True)
        # 内存聚合
        self._counts: Counter = Counter()
        self._errors: Counter = Counter()
        self._latencies: Dict[str, List[float]] = defaultdict(list)
        self._last_events: List[Dict] = []

    @classmethod
    def instance(cls, project_root: Optional[str] = None) -> "TelemetryStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(project_root)
            return cls._instance

    def _today_file(self) -> Path:
        return self.dir / f"tool_calls.{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    def record(self, tool: str, duration_ms: float, ok: bool,
               error_code: Optional[str] = None, args_preview: Optional[str] = None) -> None:
        event = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "tool": tool,
            "duration_ms": round(duration_ms, 1),
            "ok": ok,
            "error_code": error_code,
            "args_preview": (args_preview or "")[:200],
        }
        with self._lock:
            self._counts[tool] += 1
            if not ok:
                self._errors[tool] += 1
            self._latencies[tool].append(duration_ms)
            # 截断, 避免内存爆
            if len(self._latencies[tool]) > 500:
                self._latencies[tool] = self._latencies[tool][-500:]
            self._last_events.append(event)
            if len(self._last_events) > 200:
                self._last_events = self._last_events[-200:]
            # 追加到当日 jsonl
            try:
                with self._today_file().open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def stats(self, top_n: int = 30) -> Dict:
        with self._lock:
            total_calls = sum(self._counts.values())
            total_errors = sum(self._errors.values())
            rows = []
            for tool, count in self._counts.most_common(top_n):
                lats = sorted(self._latencies.get(tool) or [])
                if lats:
                    p50 = lats[len(lats) // 2]
                    p95 = lats[min(len(lats) - 1, int(len(lats) * 0.95))]
                    mean = sum(lats) / len(lats)
                else:
                    p50 = p95 = mean = 0
                rows.append({
                    "tool": tool,
                    "calls": count,
                    "errors": self._errors.get(tool, 0),
                    "error_rate": round(self._errors.get(tool, 0) / count, 3) if count else 0,
                    "latency_ms": {"p50": round(p50, 1), "p95": round(p95, 1), "mean": round(mean, 1)},
                })
            recent = list(self._last_events[-20:])
            return {
                "total_calls": total_calls,
                "total_errors": total_errors,
                "unique_tools": len(self._counts),
                "error_rate": round(total_errors / total_calls, 3) if total_calls else 0,
                "by_tool": rows,
                "recent_events": recent,
            }


def traced(tool_name: str):
    """装饰器: 包 tools 实例方法, 自动记录调用"""

    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            store = TelemetryStore.instance()
            t0 = time.time()
            ok = True
            error_code = None
            try:
                result = fn(*args, **kwargs)
                if isinstance(result, dict) and result.get("success") is False:
                    ok = False
                    error_code = (result.get("error") or {}).get("code")
                return result
            except Exception as ex:
                ok = False
                error_code = type(ex).__name__
                raise
            finally:
                dt = (time.time() - t0) * 1000
                preview = json.dumps({k: type(v).__name__ for k, v in (kwargs or {}).items()})[:200]
                store.record(tool_name, dt, ok, error_code, preview)

        return wrapper

    return decorator


class HealthTools:
    """健康监控 + 遥测聚合"""

    def __init__(
        self,
        project_root: Optional[str] = None,
        ai_adapter: Any = None,
        notification_adapter: Any = None,
    ):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self._store = TelemetryStore.instance(str(self.project_root))
        self._ai_adapter = ai_adapter
        self._notification_adapter = notification_adapter

    def tool_stats(self, top_n: int = 30) -> Dict:
        """当前会话的工具调用统计"""
        stats = self._store.stats(top_n=top_n)
        return _ok(stats, **{k: v for k, v in stats.items() if isinstance(v, (int, float))})

    def system_health(self) -> Dict:
        """Run readiness checks without confusing execution success with readiness."""
        import sqlite3
        import shutil
        import requests
        import yaml

        health = {"checks": {}, "ts": datetime.now().isoformat(timespec="seconds")}
        checks = health["checks"]

        config_path = self.project_root / "config" / "config.yaml"
        if not config_path.exists():
            checks["configuration"] = _health_check(
                False, required=True, status="needs_setup", reason="config/config.yaml 不存在"
            )
        else:
            try:
                config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                valid = isinstance(config, dict) and bool(config)
                checks["configuration"] = _health_check(
                    valid,
                    required=True,
                    status="ready" if valid else "invalid",
                    reason=None if valid else "config/config.yaml 为空或不是映射",
                )
            except Exception as ex:
                checks["configuration"] = _health_check(
                    False, required=True, status="invalid", reason=str(ex)
                )

        news_dir = self.project_root / "output" / "news"
        dbs = sorted(
            news_dir.glob("*.db") if news_dir.exists() else [],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if dbs:
            latest = dbs[0]
            age_hours = (time.time() - latest.stat().st_mtime) / 3600
            try:
                with sqlite3.connect(
                    f"{latest.resolve().as_uri()}?mode=ro", uri=True
                ) as connection:
                    item_count = connection.execute(
                        "SELECT COUNT(*) FROM news_items"
                    ).fetchone()[0]
                fresh = age_hours < 48
                has_data = item_count > 0
                checks["news_data"] = _health_check(
                    has_data and fresh,
                    required=True,
                    status="no_data" if not has_data else "ready" if fresh else "stale",
                    latest_file=latest.name,
                    age_hours=round(age_hours, 1),
                    total_db_count=len(dbs),
                    item_count=item_count,
                )
            except sqlite3.Error as ex:
                checks["news_data"] = _health_check(
                    False,
                    required=True,
                    status="invalid",
                    latest_file=latest.name,
                    total_db_count=len(dbs),
                    reason=str(ex),
                )
        else:
            checks["news_data"] = _health_check(
                False, required=True, status="no_data", reason="no db files"
            )

        idx = self.project_root / "output" / "semantic_index" / "meta.json"
        if idx.exists():
            try:
                meta = json.loads(idx.read_text(encoding="utf-8"))
                checks["semantic_index"] = _health_check(
                    True,
                    required=False,
                    status="ready",
                    doc_count=meta.get("doc_count"),
                    built_at=meta.get("built_at"),
                )
            except Exception as ex:
                checks["semantic_index"] = _health_check(
                    False, required=False, status="invalid", reason=str(ex)
                )
        else:
            checks["semantic_index"] = _health_check(
                False, required=False, status="needs_setup", reason="未构建"
            )

        try:
            r = requests.get("http://localhost:1200/", timeout=3)
            rsshub_ok = r.status_code < 500
            checks["rsshub"] = _health_check(
                rsshub_ok,
                required=False,
                status="ready" if rsshub_ok else "unavailable",
                status_code=r.status_code,
            )
        except Exception:
            checks["rsshub"] = _health_check(
                False, required=False, status="unavailable", reason="connection_failed"
            )

        try:
            usage = shutil.disk_usage(str(self.project_root))
            disk_ok = usage.free > 1024 * 1024 * 1024
            checks["disk"] = _health_check(
                disk_ok,
                required=True,
                status="ready" if disk_ok else "low_space",
                free_gb=round(usage.free / 1024 / 1024 / 1024, 1),
                total_gb=round(usage.total / 1024 / 1024 / 1024, 1),
            )
        except Exception as ex:
            checks["disk"] = _health_check(
                False, required=True, status="check_failed", reason=str(ex)
            )

        sched_dir = self.project_root / "output" / "scheduled_tasks"
        task_count = len(list(sched_dir.glob("*.json"))) if sched_dir.exists() else 0
        checks["scheduled_tasks"] = _health_check(
            True,
            required=False,
            status="ready" if task_count else "not_configured",
            count=task_count,
        )

        alerts_path = self.project_root / "config" / "alerts.yaml"
        checks["alert_rules"] = _health_check(
            True,
            required=False,
            status="ready" if alerts_path.exists() else "not_configured",
            configured=alerts_path.exists(),
            file=str(alerts_path) if alerts_path.exists() else None,
            size=alerts_path.stat().st_size if alerts_path.exists() else 0,
        )

        cli_packages = {
            "bili": "bilibili-cli",
            "xhs": "xiaohongshu-cli",
            "twitter": "twitter-cli",
            "tg": "kabi-tg-cli",
        }
        cli_status = {}
        for name, package in cli_packages.items():
            installed = bool(shutil.which(name))
            cli_status[name] = {
                "installed": installed,
                "package": package,
                "authentication": "not_checked" if installed else None,
                "supported": True,
            }
        cli_status["discord"] = {
            "installed": bool(shutil.which("discord")),
            "package": None,
            "authentication": None,
            "supported": False,
            "status": "policy_unsupported",
            "replacement": "discord_bot_or_oauth2",
        }
        installed_cli_count = sum(
            1 for item in cli_status.values() if item["installed"] and item["supported"]
        )
        checks["social_cli"] = _health_check(
            False,
            required=False,
            status="needs_auth_check" if installed_cli_count else "needs_setup",
            installed=installed_cli_count,
            total=len(cli_packages),
            tools=cli_status,
            note="安装状态不等于登录就绪；使用对应 auth status 工具做显式验证。",
        )

        checks["ai_providers"] = self._ai_provider_health()
        checks["notifications"] = self._notification_health()

        required_check_names = [
            name for name, check in checks.items() if check["required"]
        ]
        blocking_check_names = [
            name for name in required_check_names if not checks[name]["ok"]
        ]
        degraded_check_names = [
            name
            for name, check in checks.items()
            if not check["required"] and not check["ok"]
        ]
        ready = not blocking_check_names
        if not ready:
            status = "not_ready"
        elif degraded_check_names:
            status = "degraded"
        else:
            status = "ready"

        health.update({
            "status": status,
            "ready": ready,
            "ok": ready,
            "contract": {
                "success": "check_execution",
                "ready": "required_business_readiness",
                "status": "ready | degraded | not_ready",
            },
        })
        return _ok(
            health,
            status=status,
            ready=ready,
            ok=ready,
            checks_total=len(checks),
            required_checks=len(required_check_names),
            blocking_checks=blocking_check_names,
            degraded_checks=degraded_check_names,
        )

    def _ai_provider_health(self) -> Dict:
        if self._ai_adapter is None:
            return _health_check(
                False, required=False, status="not_checked", reason="AI adapter not attached"
            )
        try:
            response = self._ai_adapter.check_ai_providers()
            if not response.get("success"):
                error = response.get("error") or {}
                return _health_check(
                    False,
                    required=False,
                    status="check_failed",
                    reason=error.get("message") or "provider check failed",
                    error_code=error.get("code"),
                )
            providers = response.get("data") or {}
            configured = sum(
                1 for provider in providers.values() if provider.get("configured")
            )
            return _health_check(
                configured > 0,
                required=False,
                status="ready" if configured else "needs_setup",
                configured=configured,
                total=len(providers),
                providers=providers,
            )
        except Exception as ex:
            return _health_check(
                False, required=False, status="check_failed", reason=str(ex)
            )

    def _notification_health(self) -> Dict:
        if self._notification_adapter is None:
            return _health_check(
                False,
                required=False,
                status="not_checked",
                reason="notification adapter not attached",
            )
        try:
            response = self._notification_adapter.get_notification_channels()
            if not response.get("success"):
                error = response.get("error") or {}
                return _health_check(
                    False,
                    required=False,
                    status="check_failed",
                    reason=error.get("message") or "notification check failed",
                    error_code=error.get("code"),
                )
            channels = response.get("channels") or []
            configured = sum(1 for channel in channels if channel.get("configured"))
            enabled = bool(response.get("notification_enabled", True))
            return _health_check(
                enabled and configured > 0,
                required=False,
                status="ready" if enabled and configured else "needs_setup",
                enabled=enabled,
                configured=configured,
                total=len(channels),
                channels=channels,
            )
        except Exception as ex:
            return _health_check(
                False, required=False, status="check_failed", reason=str(ex)
            )


def _health_check(ok: bool, required: bool, status: str, **details: Any) -> Dict:
    check = {"ok": ok, "required": required, "status": status}
    check.update({key: value for key, value in details.items() if value is not None})
    return check
