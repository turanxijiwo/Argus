"""
定时任务调度 - Batch 5a 交付

把"每天 9 点抓 15 平台 → AI 简报 → 推到飞书"这类工作流编排成 macOS launchd 任务。

核心设计:
    - workflow_dsl 是一个 step 列表, 每步引用一个 MCP tool + args
    - 落盘成 plist + workflow JSON, launchd 调度时再反序列化运行
    - 运行入口: argus_server.scheduler_runner (见同目录下的 CLI)

工具:
    schedule_task(name, workflow, schedule)
    list_scheduled_tasks()
    remove_scheduled_task(name)
    run_scheduled_task(name)        # 立即手动触发一次
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


LAUNCHD_DIR = Path.home() / "Library" / "LaunchAgents"
TASK_LABEL_PREFIX = "com.argus.task."


def _ok(data: Any, **summary) -> Dict:
    return {"success": True, "summary": summary, "data": data}


def _err(message: str, code: str = "SCHEDULER_ERROR", **extra) -> Dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,48}$")


class SchedulerTools:
    """macOS launchd 定时任务管理"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
        self.task_dir = self.project_root / "output" / "scheduled_tasks"
        self.task_dir.mkdir(parents=True, exist_ok=True)
        LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)

    # ────────────── 内部 helper ──────────────

    @staticmethod
    def _label(name: str) -> str:
        return f"{TASK_LABEL_PREFIX}{name}"

    def _plist_path(self, name: str) -> Path:
        return LAUNCHD_DIR / f"{self._label(name)}.plist"

    def _workflow_path(self, name: str) -> Path:
        return self.task_dir / f"{name}.json"

    def _log_path(self, name: str) -> Path:
        return self.task_dir / f"{name}.log"

    def _python_path(self) -> str:
        candidate = self.project_root / ".venv" / "bin" / "python"
        if candidate.exists():
            return str(candidate)
        return sys.executable

    @staticmethod
    def _parse_schedule(schedule: Any) -> List[Dict]:
        """解析 schedule 配置 → launchd StartCalendarInterval 列表

        支持的输入:
            - "daily@09:00"          每天 09:00
            - "hourly"               每小时 0 分
            - "every:30m"            每 30 分钟 (转成 StartInterval, 见下)
            - {"hour": 9, "minute": 0, "weekday": 1}   原生字典
            - [{"hour":9}, {"hour":21}]                多触发点
        """
        if isinstance(schedule, dict):
            return [schedule]
        if isinstance(schedule, list):
            return [s for s in schedule if isinstance(s, dict)]
        if not isinstance(schedule, str):
            raise ValueError("schedule 必须是 str / dict / list")
        s = schedule.strip().lower()
        if s == "hourly":
            return [{"minute": 0}]
        if s.startswith("daily@"):
            hhmm = s.split("@", 1)[1]
            m = re.match(r"^(\d{1,2}):(\d{2})$", hhmm)
            if not m:
                raise ValueError(f"daily@HH:MM 格式错误: {hhmm}")
            return [{"hour": int(m.group(1)), "minute": int(m.group(2))}]
        if s.startswith("every:"):
            # every:30m / every:2h
            val = s.split(":", 1)[1]
            mm = re.match(r"^(\d+)([mh])$", val)
            if not mm:
                raise ValueError(f"every:<N><m|h> 格式错误: {val}")
            n = int(mm.group(1))
            unit = mm.group(2)
            # 用特殊 sentinel: {"_start_interval": seconds}
            return [{"_start_interval": n * (60 if unit == "m" else 3600)}]
        raise ValueError(f"无法识别的 schedule: {schedule}")

    # ────────────── DSL 校验 ──────────────

    _ALLOWED_TOOLS = {
        "trigger_crawl", "sync_from_remote", "ai_brief_news", "ai_summarize",
        "ai_translate", "send_notification", "generate_summary_report",
        "detect_anomaly", "semantic_deduplicate", "analyze_with_ai",
        "get_latest_news", "get_trending_topics", "search_news",
        "narrative_tracking", "universal_search",
        "semantic_index_rebuild", "semantic_search",
        "alert_run_all",
        "export_daily_brief", "export_query_report", "export_anomalies",
        "route_dispatch",
        "push_daily_brief",
    }

    def _validate_workflow(self, workflow: Any) -> Optional[str]:
        if not isinstance(workflow, dict):
            return "workflow 必须是对象 {steps: [...]}"
        steps = workflow.get("steps")
        if not isinstance(steps, list) or not steps:
            return "workflow.steps 必须是非空数组"
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return f"steps[{i}] 不是对象"
            tool = step.get("tool")
            if not tool:
                return f"steps[{i}] 缺少 tool 字段"
            if tool not in self._ALLOWED_TOOLS:
                return (f"steps[{i}] tool '{tool}' 不在白名单. "
                        f"可用: {sorted(self._ALLOWED_TOOLS)}")
            if "args" in step and not isinstance(step["args"], dict):
                return f"steps[{i}].args 必须是对象"
        return None

    # ────────────── 对外工具 ──────────────

    def schedule_task(
        self,
        name: str,
        workflow: Dict,
        schedule: Any,
        description: str = "",
        enabled: bool = True,
    ) -> Dict:
        """注册一个 launchd 定时任务

        Args:
            name: 任务名 (字母开头, 2-48 位字母数字下划线横线)
            workflow: {"steps": [{"tool": "...", "args": {...}}, ...]}
            schedule: 见 _parse_schedule 注释
            description: 描述 (存到 workflow 文件)
            enabled: 立即 load 到 launchd

        Returns: 任务信息 + 文件路径
        """
        if not _NAME_RE.match(name or ""):
            return _err(
                "name 必须以字母开头, 2-48 位字母数字下划线横线",
                code="INVALID_NAME",
            )
        err = self._validate_workflow(workflow)
        if err:
            return _err(err, code="INVALID_WORKFLOW")
        try:
            parsed_schedule = self._parse_schedule(schedule)
        except ValueError as ex:
            return _err(str(ex), code="INVALID_SCHEDULE")

        plist = self._plist_path(name)
        wf_path = self._workflow_path(name)
        log_path = self._log_path(name)

        # 写 workflow JSON
        payload = {
            "name": name,
            "description": description,
            "schedule": schedule,
            "workflow": workflow,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        wf_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        # 生成 plist
        python_bin = self._python_path()
        runner_module = "argus_server.scheduler_runner"
        program_args = [
            python_bin, "-m", runner_module,
            "--name", name,
            "--project-root", str(self.project_root),
        ]

        plist_data: Dict[str, Any] = {
            "Label": self._label(name),
            "ProgramArguments": program_args,
            "WorkingDirectory": str(self.project_root),
            "StandardOutPath": str(log_path),
            "StandardErrorPath": str(log_path),
            "RunAtLoad": False,
            "EnvironmentVariables": {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin") + ":" + str(Path.home() / ".local/bin"),
            },
        }

        # 解析 StartInterval vs StartCalendarInterval
        # Apple launchd.plist 要求 key 首字母大写: Hour / Minute / Day / Weekday / Month
        # 小写写法 launchd 识别不了,会当作"通配"导致每分钟触发
        _KEY_MAP = {
            "minute": "Minute", "hour": "Hour", "day": "Day",
            "weekday": "Weekday", "month": "Month",
        }
        sci: List[Dict] = []
        start_interval: Optional[int] = None
        for s in parsed_schedule:
            if "_start_interval" in s:
                start_interval = int(s["_start_interval"])
                continue
            entry: Dict[str, int] = {}
            for k, v in s.items():
                if not isinstance(v, (int, str)):
                    continue
                if not str(v).lstrip("-").isdigit():
                    continue
                key_plist = _KEY_MAP.get(k.lower(), k[0].upper() + k[1:].lower())
                entry[key_plist] = int(v)
            if entry:
                sci.append(entry)
        if start_interval:
            plist_data["StartInterval"] = start_interval
        if sci:
            # Apple 推荐 array 形式, 即使只有 1 条也用 array, 避免某些版本解析歧义
            plist_data["StartCalendarInterval"] = sci
        if not start_interval and not sci:
            # 退化为 RunAtLoad 一次
            plist_data["RunAtLoad"] = True

        with plist.open("wb") as fp:
            plistlib.dump(plist_data, fp)

        # launchctl load
        load_result = None
        if enabled:
            load_result = self._launchctl_load(plist)

        return _ok(
            {
                "name": name,
                "label": self._label(name),
                "plist": str(plist),
                "workflow_path": str(wf_path),
                "log_path": str(log_path),
                "schedule_parsed": parsed_schedule,
                "load_result": load_result,
            },
            enabled=enabled,
        )

    def list_scheduled_tasks(self) -> Dict:
        """列出所有 Argus 定时任务"""
        tasks = []
        for wf_file in sorted(self.task_dir.glob("*.json")):
            if wf_file.name.endswith(".last_run.json"):
                continue
            try:
                data = json.loads(wf_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            name = data.get("name") or wf_file.stem
            plist = self._plist_path(name)
            loaded = self._is_loaded(self._label(name))
            tasks.append({
                "name": name,
                "description": data.get("description", ""),
                "schedule": data.get("schedule"),
                "steps_count": len(data.get("workflow", {}).get("steps", [])),
                "created_at": data.get("created_at"),
                "plist_exists": plist.exists(),
                "loaded": loaded,
                "log": str(self._log_path(name)),
            })
        return _ok({"tasks": tasks}, count=len(tasks))

    def remove_scheduled_task(self, name: str) -> Dict:
        """卸载并删除任务"""
        plist = self._plist_path(name)
        wf = self._workflow_path(name)
        log = self._log_path(name)

        if not plist.exists() and not wf.exists():
            return _err(f"任务 {name} 不存在", code="NOT_FOUND")

        unload_result = None
        if plist.exists():
            unload_result = self._launchctl_unload(plist)
            try:
                plist.unlink()
            except Exception as ex:
                return _err(f"删除 plist 失败: {ex}", code="FS_ERROR")
        removed_files = {"plist": str(plist)}
        if wf.exists():
            wf.unlink()
            removed_files["workflow"] = str(wf)
        # 保留 log 供事后排错; 可选删
        return _ok(
            {"name": name, "removed": removed_files, "unload_result": unload_result}
        )

    def run_scheduled_task(self, name: str) -> Dict:
        """立即手动触发一次已注册任务 (launchctl kickstart)"""
        plist = self._plist_path(name)
        if not plist.exists():
            return _err(f"任务 {name} 不存在", code="NOT_FOUND")
        label = self._label(name)
        if not self._is_loaded(label):
            self._launchctl_load(plist)
        # launchctl kickstart 触发一次
        try:
            r = subprocess.run(
                ["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"],
                capture_output=True, text=True, timeout=15,
            )
        except Exception as ex:
            return _err(f"kickstart 失败: {ex}", code="LAUNCHCTL_ERROR")
        return _ok(
            {
                "name": name,
                "label": label,
                "returncode": r.returncode,
                "stdout": (r.stdout or "")[:500],
                "stderr": (r.stderr or "")[:500],
                "log_tail": self._read_log_tail(name),
            }
        )

    # ────────────── launchctl 封装 ──────────────

    @staticmethod
    def _launchctl_load(plist: Path) -> Dict:
        try:
            subprocess.run(["launchctl", "unload", str(plist)],
                           capture_output=True, text=True, timeout=10)
        except Exception:
            pass
        try:
            r = subprocess.run(["launchctl", "load", str(plist)],
                               capture_output=True, text=True, timeout=10)
            return {"returncode": r.returncode,
                    "stderr": (r.stderr or "")[:300]}
        except Exception as ex:
            return {"error": str(ex)}

    @staticmethod
    def _launchctl_unload(plist: Path) -> Dict:
        try:
            r = subprocess.run(["launchctl", "unload", str(plist)],
                               capture_output=True, text=True, timeout=10)
            return {"returncode": r.returncode,
                    "stderr": (r.stderr or "")[:300]}
        except Exception as ex:
            return {"error": str(ex)}

    @staticmethod
    def _is_loaded(label: str) -> bool:
        try:
            r = subprocess.run(["launchctl", "list"],
                               capture_output=True, text=True, timeout=10)
            return any(line.split("\t")[-1] == label for line in (r.stdout or "").splitlines())
        except Exception:
            return False

    def _read_log_tail(self, name: str, lines: int = 30) -> str:
        log = self._log_path(name)
        if not log.exists():
            return ""
        try:
            content = log.read_text(encoding="utf-8", errors="replace")
            return "\n".join(content.splitlines()[-lines:])
        except Exception:
            return ""
