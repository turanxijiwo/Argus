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
import os
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

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self._store = TelemetryStore.instance(str(self.project_root))

    def tool_stats(self, top_n: int = 30) -> Dict:
        """当前会话的工具调用统计"""
        stats = self._store.stats(top_n=top_n)
        return _ok(stats, **{k: v for k, v in stats.items() if isinstance(v, (int, float))})

    def system_health(self) -> Dict:
        """综合健康: 本地索引 / RSSHub / 数据新鲜度 / 磁盘"""
        import shutil
        import requests

        health = {"checks": {}, "ts": datetime.now().isoformat(timespec="seconds")}

        # 数据新鲜度
        news_dir = self.project_root / "output" / "news"
        if news_dir.exists():
            dbs = sorted([f for f in news_dir.glob("*.db")], key=lambda p: p.stat().st_mtime, reverse=True)
            if dbs:
                latest = dbs[0]
                age_hours = (time.time() - latest.stat().st_mtime) / 3600
                health["checks"]["news_data"] = {
                    "ok": age_hours < 48,
                    "latest_file": latest.name,
                    "age_hours": round(age_hours, 1),
                    "total_db_count": len(dbs),
                }
            else:
                health["checks"]["news_data"] = {"ok": False, "reason": "no db files"}

        # BM25 索引
        idx = self.project_root / "output" / "semantic_index" / "meta.json"
        if idx.exists():
            try:
                meta = json.loads(idx.read_text(encoding="utf-8"))
                health["checks"]["semantic_index"] = {
                    "ok": True,
                    "doc_count": meta.get("doc_count"),
                    "built_at": meta.get("built_at"),
                }
            except Exception:
                health["checks"]["semantic_index"] = {"ok": False, "reason": "meta 解析失败"}
        else:
            health["checks"]["semantic_index"] = {"ok": False, "reason": "未构建"}

        # RSSHub
        try:
            r = requests.get("http://localhost:1200/", timeout=3)
            health["checks"]["rsshub"] = {"ok": r.status_code < 500, "status_code": r.status_code}
        except Exception:
            health["checks"]["rsshub"] = {"ok": False, "reason": "connection_failed"}

        # 磁盘
        try:
            total, used, free = shutil.disk_usage(str(self.project_root))
            health["checks"]["disk"] = {
                "ok": free > 1024 * 1024 * 1024,   # 至少 1 GB
                "free_gb": round(free / 1024 / 1024 / 1024, 1),
                "total_gb": round(total / 1024 / 1024 / 1024, 1),
            }
        except Exception:
            pass

        # 定时任务数
        sched_dir = self.project_root / "output" / "scheduled_tasks"
        if sched_dir.exists():
            health["checks"]["scheduled_tasks"] = {
                "ok": True,
                "count": len(list(sched_dir.glob("*.json"))),
            }

        # 告警规则数
        alerts_path = self.project_root / "config" / "alerts.yaml"
        if alerts_path.exists():
            health["checks"]["alert_rules"] = {
                "ok": True,
                "file": str(alerts_path),
                "size": alerts_path.stat().st_size,
            }

        # 总 ok
        all_ok = all(c.get("ok", True) for c in health["checks"].values())
        health["ok"] = all_ok
        return _ok(health, ok=all_ok)
