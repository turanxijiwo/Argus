import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from argus.web.app import health as web_health
from argus_server.tools.system import SystemManagementTools
from argus_server.tools.telemetry import HealthTools


def _ai_adapter(configured=0):
    adapter = Mock()
    providers = {
        "llm_chat": {"configured": configured > 0},
        "tavily": {"configured": False},
        "exa": {"configured": False},
        "perplexity": {"configured": False},
        "brave": {"configured": False},
    }
    adapter.check_ai_providers.return_value = {
        "success": True,
        "summary": {"total": 5, "configured": configured},
        "data": providers,
    }
    return adapter


def _notification_adapter(configured=0, enabled=True):
    adapter = Mock()
    adapter.get_notification_channels.return_value = {
        "success": True,
        "notification_enabled": enabled,
        "channels": [
            {"id": "feishu", "configured": index < configured}
            for index in range(9)
        ],
    }
    return adapter


def _prepare_core_runtime(root):
    config_dir = root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_text(
        "platforms:\n  enabled: true\n  sources:\n    - id: demo\n",
        encoding="utf-8",
    )
    news_dir = root / "output" / "news"
    news_dir.mkdir(parents=True)
    with sqlite3.connect(news_dir / "2026-07-14.db") as connection:
        connection.execute("CREATE TABLE news_items (id INTEGER PRIMARY KEY, title TEXT)")
        connection.execute("INSERT INTO news_items (title) VALUES ('OpenAI update')")


class SystemHealthTest(unittest.TestCase):
    def test_web_health_explicitly_reports_liveness_only(self):
        response = asyncio.run(web_health(None))
        payload = json.loads(response.body)

        self.assertTrue(payload["success"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "alive")
        self.assertEqual(payload["scope"], "liveness")
        self.assertIsNone(payload["ready"])

    def test_missing_core_setup_is_not_ready_but_check_execution_succeeds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tools = HealthTools(
                tmpdir,
                ai_adapter=_ai_adapter(),
                notification_adapter=_notification_adapter(),
            )
            with (
                patch("requests.get", side_effect=RuntimeError("offline")),
                patch("shutil.which", return_value=None),
                patch(
                    "shutil.disk_usage",
                    return_value=SimpleNamespace(total=20 << 30, used=5 << 30, free=15 << 30),
                ),
            ):
                response = tools.system_health()

        self.assertTrue(response["success"])
        self.assertFalse(response["summary"]["ready"])
        self.assertFalse(response["summary"]["ok"])
        self.assertEqual(response["summary"]["status"], "not_ready")
        self.assertEqual(
            response["summary"]["blocking_checks"],
            ["configuration", "news_data"],
        )
        self.assertEqual(response["data"]["status"], "not_ready")
        self.assertFalse(response["data"]["ok"])
        self.assertEqual(response["data"]["contract"]["success"], "check_execution")
        self.assertEqual(response["data"]["checks"]["configuration"]["status"], "needs_setup")
        self.assertEqual(response["data"]["checks"]["news_data"]["status"], "no_data")
        self.assertTrue(response["data"]["checks"]["news_data"]["required"])
        self.assertEqual(response["data"]["checks"]["semantic_index"]["status"], "needs_setup")
        self.assertEqual(response["data"]["checks"]["social_cli"]["status"], "needs_setup")
        self.assertEqual(response["data"]["checks"]["ai_providers"]["configured"], 0)
        self.assertEqual(response["data"]["checks"]["notifications"]["configured"], 0)

    def test_empty_database_does_not_prove_news_readiness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "config.yaml").write_text("platforms: {}\n", encoding="utf-8")
            news_dir = root / "output" / "news"
            news_dir.mkdir(parents=True)
            with sqlite3.connect(news_dir / "2026-07-14.db") as connection:
                connection.execute("CREATE TABLE news_items (id INTEGER PRIMARY KEY, title TEXT)")
            tools = HealthTools(
                tmpdir,
                ai_adapter=_ai_adapter(),
                notification_adapter=_notification_adapter(),
            )
            with (
                patch("requests.get", side_effect=RuntimeError("offline")),
                patch("shutil.which", return_value=None),
                patch(
                    "shutil.disk_usage",
                    return_value=SimpleNamespace(total=20 << 30, used=5 << 30, free=15 << 30),
                ),
            ):
                response = tools.system_health()

        self.assertFalse(response["summary"]["ready"])
        self.assertEqual(response["data"]["checks"]["news_data"]["status"], "no_data")
        self.assertEqual(response["data"]["checks"]["news_data"]["item_count"], 0)

    def test_optional_gaps_are_degraded_without_blocking_core_readiness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_core_runtime(root)
            tools = HealthTools(
                tmpdir,
                ai_adapter=_ai_adapter(configured=1),
                notification_adapter=_notification_adapter(configured=1),
            )
            with (
                patch("requests.get", side_effect=RuntimeError("offline")),
                patch("shutil.which", return_value=None),
                patch(
                    "shutil.disk_usage",
                    return_value=SimpleNamespace(total=20 << 30, used=5 << 30, free=15 << 30),
                ),
            ):
                response = tools.system_health()

        self.assertTrue(response["success"])
        self.assertTrue(response["summary"]["ready"])
        self.assertEqual(response["summary"]["status"], "degraded")
        self.assertEqual(response["summary"]["blocking_checks"], [])
        self.assertIn("semantic_index", response["summary"]["degraded_checks"])
        self.assertIn("rsshub", response["summary"]["degraded_checks"])
        self.assertIn("social_cli", response["summary"]["degraded_checks"])
        self.assertTrue(response["data"]["ok"])
        self.assertEqual(response["data"]["checks"]["configuration"]["status"], "ready")
        self.assertEqual(response["data"]["checks"]["news_data"]["status"], "ready")
        self.assertEqual(response["data"]["checks"]["ai_providers"]["status"], "ready")
        self.assertEqual(response["data"]["checks"]["notifications"]["status"], "ready")

    def test_optional_provider_exception_stays_inside_its_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _prepare_core_runtime(root)
            ai_adapter = Mock()
            ai_adapter.check_ai_providers.side_effect = RuntimeError("provider check crashed")
            tools = HealthTools(
                tmpdir,
                ai_adapter=ai_adapter,
                notification_adapter=_notification_adapter(configured=1),
            )
            with (
                patch("requests.get", side_effect=RuntimeError("offline")),
                patch("shutil.which", return_value=None),
                patch(
                    "shutil.disk_usage",
                    return_value=SimpleNamespace(total=20 << 30, used=5 << 30, free=15 << 30),
                ),
            ):
                response = tools.system_health()

        self.assertTrue(response["success"])
        self.assertTrue(response["summary"]["ready"])
        self.assertEqual(response["summary"]["status"], "degraded")
        self.assertEqual(response["data"]["checks"]["ai_providers"]["status"], "check_failed")
        self.assertEqual(
            response["data"]["checks"]["ai_providers"]["reason"],
            "provider check crashed",
        )

    def test_get_system_status_reuses_authoritative_readiness(self):
        readiness = {
            "status": "not_ready",
            "ready": False,
            "ok": False,
            "checks": {"configuration": {"ok": False}},
        }
        health_adapter = Mock()
        health_adapter.system_health.return_value = {
            "success": True,
            "summary": {"status": "not_ready", "ready": False},
            "data": readiness,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            tools = SystemManagementTools(tmpdir, health_adapter=health_adapter)
            tools.data_service = Mock()
            tools.data_service.get_system_status.return_value = {
                "system": {"version": "test"},
                "data": {"latest_record": None},
                "cache": {},
                "health": "healthy",
            }
            response = tools.get_system_status()

        self.assertTrue(response["success"])
        self.assertEqual(response["summary"]["status"], "not_ready")
        self.assertFalse(response["summary"]["ready"])
        self.assertEqual(response["data"]["health"], "not_ready")
        self.assertEqual(response["data"]["readiness"], readiness)
        health_adapter.system_health.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
