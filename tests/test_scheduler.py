import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from argus_server import scheduler_runner
from argus_server.tools import scheduler as scheduler_module
from argus_server.tools.scheduler import SchedulerTools


class SchedulerToolsTests(unittest.TestCase):
    def test_schedule_task_writes_crawl_and_index_workflow_without_notification(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            launchd_dir = project_root / "LaunchAgents"
            workflow = {
                "steps": [
                    {"tool": "trigger_crawl", "args": {}},
                    {"tool": "semantic_index_rebuild", "args": {"days": 30}},
                ]
            }

            with patch.object(scheduler_module, "LAUNCHD_DIR", launchd_dir):
                tools = SchedulerTools(str(project_root))
                result = tools.schedule_task(
                    name="argus_cycle_acceptance",
                    workflow=workflow,
                    schedule={"hour": 23, "minute": 59},
                    description="Acceptance cycle without notifications",
                    enabled=False,
                )

            self.assertTrue(result["success"])
            self.assertFalse(result["summary"]["enabled"])

            workflow_path = Path(result["data"]["workflow_path"])
            saved_workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            saved_steps = saved_workflow["workflow"]["steps"]
            self.assertEqual(
                [step["tool"] for step in saved_steps],
                ["trigger_crawl", "semantic_index_rebuild"],
            )
            self.assertNotIn("send_notification", json.dumps(saved_steps))

            with Path(result["data"]["plist"]).open("rb") as plist_file:
                plist = plistlib.load(plist_file)
            self.assertEqual(
                plist["StartCalendarInterval"],
                [{"Hour": 23, "Minute": 59}],
            )
            self.assertFalse(plist["RunAtLoad"])
            self.assertEqual(plist["ProgramArguments"][0], sys.executable)
            self.assertEqual(plist["WorkingDirectory"], str(project_root.resolve()))

    def test_schedule_task_rejects_unknown_workflow_tool(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            with patch.object(
                scheduler_module,
                "LAUNCHD_DIR",
                project_root / "LaunchAgents",
            ):
                tools = SchedulerTools(str(project_root))
                result = tools.schedule_task(
                    name="invalid_workflow",
                    workflow={"steps": [{"tool": "unknown_tool"}]},
                    schedule="hourly",
                    enabled=False,
                )

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "INVALID_WORKFLOW")


class SchedulerRunnerTests(unittest.TestCase):
    def _write_workflow(self, project_root):
        task_dir = project_root / "output" / "scheduled_tasks"
        task_dir.mkdir(parents=True)
        workflow_path = task_dir / "argus_cycle_acceptance.json"
        workflow_path.write_text(
            json.dumps(
                {
                    "name": "argus_cycle_acceptance",
                    "workflow": {
                        "steps": [
                            {"tool": "trigger_crawl", "args": {}},
                            {
                                "tool": "semantic_index_rebuild",
                                "args": {"days": 30},
                            },
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        return task_dir

    def _run(self, project_root, tools):
        argv = [
            "scheduler_runner",
            "--name",
            "argus_cycle_acceptance",
            "--project-root",
            str(project_root),
        ]
        with patch("argus_server.server._get_tools", return_value=tools), patch.object(
            sys,
            "argv",
            argv,
        ):
            return scheduler_runner.main()

    def test_runner_executes_crawl_before_index_rebuild(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            task_dir = self._write_workflow(project_root)
            call_order = []
            system = SimpleNamespace(
                trigger_crawl=Mock(
                    side_effect=lambda: call_order.append("crawl")
                    or {"success": True, "summary": {"total_news": 2}}
                )
            )
            semantic = SimpleNamespace(
                rebuild=Mock(
                    side_effect=lambda days: call_order.append("index")
                    or {"success": True, "data": {"doc_count": 2}}
                )
            )

            return_code = self._run(
                project_root,
                {"system": system, "semantic": semantic},
            )

            self.assertEqual(return_code, 0)
            self.assertEqual(call_order, ["crawl", "index"])
            report = json.loads(
                (task_dir / "argus_cycle_acceptance.last_run.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(report["ok"])
            self.assertEqual([step["tool"] for step in report["steps"]], [
                "trigger_crawl",
                "semantic_index_rebuild",
            ])

    def test_runner_stops_before_index_when_crawl_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            task_dir = self._write_workflow(project_root)
            semantic_rebuild = Mock(return_value={"success": True})
            tools = {
                "system": SimpleNamespace(
                    trigger_crawl=Mock(
                        return_value={
                            "success": False,
                            "error": {"code": "CRAWL_FAILED"},
                        }
                    )
                ),
                "semantic": SimpleNamespace(rebuild=semantic_rebuild),
            }

            return_code = self._run(project_root, tools)

            self.assertEqual(return_code, 2)
            semantic_rebuild.assert_not_called()
            report = json.loads(
                (task_dir / "argus_cycle_acceptance.last_run.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(report["ok"])
            self.assertEqual(len(report["steps"]), 1)


if __name__ == "__main__":
    unittest.main()
