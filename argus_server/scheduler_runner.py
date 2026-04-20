"""
Scheduled task runner - launchd 调起的真实执行器

读取 output/scheduled_tasks/<name>.json, 按 steps 顺序调用对应的 MCP tool 方法。

CLI:
    python -m argus_server.scheduler_runner --name <task_name> [--project-root PATH]

输出:
    - 实时日志到 stdout/stderr (由 plist 的 StandardOutPath/StandardErrorPath 捕获)
    - 每步结果汇总到 output/scheduled_tasks/<name>.last_run.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[{_now()}] {msg}", flush=True)


def _run_step(tools: Dict, step: Dict) -> Dict:
    """执行一步. 直接调 tool 实例的同名方法 (同步部分)"""
    tool_name = step["tool"]
    args = step.get("args", {}) or {}

    # tool_name → 定位 tools 实例里的方法
    registry = {
        "trigger_crawl": ("system", "trigger_crawl"),
        "sync_from_remote": ("storage", "sync_from_remote"),
        "ai_brief_news": ("ai", "ai_brief_news"),
        "ai_summarize": ("ai", "ai_summarize"),
        "ai_translate": ("ai", "ai_translate"),
        "send_notification": ("notification", "send_notification"),
        "generate_summary_report": ("analytics", "generate_summary_report"),
        "detect_anomaly": ("ai_analytics", "detect_anomaly"),
        "semantic_deduplicate": ("ai_analytics", "semantic_deduplicate"),
        "analyze_with_ai": ("ai_analytics", "analyze_with_ai"),
        "get_latest_news": ("data", "get_latest_news"),
        "get_trending_topics": ("analytics", "get_trending_topics"),
        "search_news": ("search", "search_news_unified"),
        "narrative_tracking": ("cross", "narrative_tracking"),
        "universal_search": ("cross", "universal_search"),
        "semantic_index_rebuild": ("semantic", "rebuild"),
        "semantic_search": ("semantic", "search"),
        "alert_run_all": ("alerts", "run_all"),
        "export_daily_brief": ("exporter", "export_daily_brief"),
        "export_query_report": ("exporter", "export_query_report"),
        "export_anomalies": ("exporter", "export_anomalies"),
        "route_dispatch": ("router", "dispatch"),
        "push_daily_brief": ("daily_brief", "push"),
    }

    if tool_name not in registry:
        return {"tool": tool_name, "ok": False, "error": f"未知 tool: {tool_name}"}

    instance_key, method_name = registry[tool_name]
    instance = tools.get(instance_key)
    if instance is None or not hasattr(instance, method_name):
        return {
            "tool": tool_name, "ok": False,
            "error": f"无法定位 {instance_key}.{method_name}",
        }
    method = getattr(instance, method_name)
    _log(f"→ {tool_name}({', '.join(f'{k}=...' for k in args)})")
    try:
        result = method(**args)
        ok = True
        if isinstance(result, dict) and result.get("success") is False:
            ok = False
        return {"tool": tool_name, "ok": ok, "result": result}
    except Exception as ex:
        import traceback
        return {
            "tool": tool_name, "ok": False,
            "error": f"{type(ex).__name__}: {ex}",
            "traceback": traceback.format_exc()[:2000],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Argus scheduled task runner")
    parser.add_argument("--name", required=True, help="任务名")
    parser.add_argument("--project-root", help="项目根目录")
    args = parser.parse_args()

    root = Path(args.project_root).resolve() if args.project_root else Path(__file__).resolve().parents[1]
    task_dir = root / "output" / "scheduled_tasks"
    wf_path = task_dir / f"{args.name}.json"
    last_run_path = task_dir / f"{args.name}.last_run.json"

    if not wf_path.exists():
        _log(f"[ERROR] workflow 文件不存在: {wf_path}")
        return 1

    # 确保能 import argus_server
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    payload = json.loads(wf_path.read_text(encoding="utf-8"))
    workflow = payload.get("workflow", {})
    steps = workflow.get("steps", [])

    _log(f"=== start task: {args.name}, {len(steps)} steps ===")

    from argus_server.server import _get_tools
    tools = _get_tools(str(root))

    run_report: Dict[str, Any] = {
        "name": args.name,
        "started_at": _now(),
        "steps": [],
        "ok": True,
    }

    prev_result = None
    for i, step in enumerate(steps):
        _log(f"[step {i+1}/{len(steps)}] tool={step.get('tool')}")
        # 支持 args 引用上一步结果: {"__prev__": "data.result_key"}
        args_dict = step.get("args", {}) or {}
        resolved: Dict[str, Any] = {}
        for k, v in args_dict.items():
            if isinstance(v, dict) and "__prev__" in v and prev_result is not None:
                path = v["__prev__"].split(".")
                cur: Any = prev_result
                for seg in path:
                    if isinstance(cur, dict):
                        cur = cur.get(seg)
                    else:
                        cur = None
                        break
                resolved[k] = cur
            else:
                resolved[k] = v
        step_with_resolved = {"tool": step["tool"], "args": resolved}
        result = _run_step(tools, step_with_resolved)
        run_report["steps"].append(result)
        prev_result = result.get("result")
        if not result["ok"]:
            _log(f"    FAILED: {result.get('error', 'see result')}")
            run_report["ok"] = False
            if step.get("continue_on_error"):
                continue
            break
        else:
            _log(f"    ok")

    run_report["finished_at"] = _now()
    last_run_path.write_text(
        json.dumps(run_report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    _log(f"=== finished: ok={run_report['ok']}, report={last_run_path} ===")
    return 0 if run_report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
