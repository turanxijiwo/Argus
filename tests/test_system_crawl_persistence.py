import json
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from argus_server.server import mcp
from argus_server.tools.system import SystemManagementTools


class FakeStorage:
    def __init__(
        self,
        database_result=True,
        database_error=None,
        txt_path="output/txt/demo.txt",
        html_path="output/html/demo.html",
    ):
        self.database_result = database_result
        self.database_error = database_error
        self.txt_path = txt_path
        self.html_path = html_path
        self.database_calls = 0
        self.txt_calls = 0
        self.html_calls = 0

    def save_news_data(self, news_data):
        self.database_calls += 1
        if self.database_error:
            raise self.database_error
        return self.database_result

    def save_txt_snapshot(self, news_data):
        self.txt_calls += 1
        return self.txt_path

    def save_html_report(self, html_content, filename):
        self.html_calls += 1
        return self.html_path


class CrawlPersistenceContractTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.tools = SystemManagementTools(self.tmpdir.name)
        self.results = {
            "demo": {
                "Headline": {
                    "ranks": [1],
                    "url": "https://example.com/story",
                }
            }
        }
        self.id_to_name = {"demo": "Demo"}
        self.now = datetime(2026, 7, 14, 12, 0, 0)

    def _persist(self, storage, save_to_local):
        return self.tools._persist_crawl_data(
            storage,
            object(),
            save_to_local,
            self.results,
            self.id_to_name,
            [],
            self.now,
            "12-00",
        )

    def _response(self, persistence):
        return self.tools._build_crawl_response(
            self.results,
            self.id_to_name,
            [],
            self.now,
            False,
            persistence,
        )

    def test_default_persists_database_without_requesting_snapshots(self):
        storage = FakeStorage()

        persistence = self._persist(storage, save_to_local=False)
        response = self._response(persistence)

        self.assertEqual(storage.database_calls, 1)
        self.assertEqual(storage.txt_calls, 0)
        self.assertEqual(storage.html_calls, 0)
        self.assertEqual(persistence["status"], "complete")
        self.assertTrue(persistence["database"]["saved"])
        self.assertEqual(persistence["snapshots"]["status"], "not_requested")
        self.assertTrue(response["summary"]["saved_to_local"])
        self.assertTrue(response["summary"]["database_saved"])
        self.assertFalse(response["summary"]["snapshots_requested"])
        self.assertFalse(response["summary"]["snapshots_saved"])

    def test_requested_snapshots_report_complete_when_both_files_exist(self):
        storage = FakeStorage()

        persistence = self._persist(storage, save_to_local=True)
        response = self._response(persistence)

        self.assertEqual(persistence["status"], "complete")
        self.assertEqual(persistence["snapshots"]["status"], "saved")
        self.assertTrue(response["summary"]["snapshots_saved"])
        self.assertEqual(
            response["saved_files"],
            {
                "txt": "output/txt/demo.txt",
                "html": "output/html/demo.html",
            },
        )

    def test_missing_requested_snapshot_is_reported_as_partial(self):
        storage = FakeStorage(html_path=None)

        persistence = self._persist(storage, save_to_local=True)
        response = self._response(persistence)

        self.assertEqual(persistence["status"], "partial")
        self.assertTrue(persistence["database"]["saved"])
        self.assertEqual(persistence["snapshots"]["status"], "partial")
        self.assertFalse(response["summary"]["snapshots_saved"])
        self.assertEqual(response["saved_files"], {"txt": "output/txt/demo.txt"})
        self.assertIn("HTML snapshot was not created", response["save_error"])
        self.assertNotIn("及 output 文件夹", response["note"])

    def test_database_error_does_not_hide_successful_snapshots(self):
        storage = FakeStorage(database_error=PermissionError("read-only database"))

        persistence = self._persist(storage, save_to_local=True)
        response = self._response(persistence)

        self.assertEqual(persistence["status"], "partial")
        self.assertFalse(persistence["database"]["saved"])
        self.assertEqual(
            persistence["database"]["error"],
            "read-only database",
        )
        self.assertEqual(persistence["snapshots"]["status"], "saved")
        self.assertTrue(response["summary"]["saved_to_local"])
        self.assertFalse(response["summary"]["database_saved"])
        self.assertTrue(response["summary"]["snapshots_saved"])
        self.assertIn("read-only database", response["save_error"])
        self.assertNotIn("SQLite 数据库及", response["note"])


class CrawlPersistenceMCPContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_trigger_crawl_keeps_public_parameters_and_serializes_persistence(self):
        expected = {
            "success": True,
            "summary": {
                "saved_to_local": True,
                "database_saved": True,
                "snapshots_requested": False,
            },
            "persistence": {
                "status": "complete",
                "database": {"attempted": True, "saved": True, "error": None},
                "snapshots": {
                    "requested": False,
                    "status": "not_requested",
                    "saved": False,
                    "files": {},
                    "errors": [],
                },
            },
        }
        trigger_crawl = Mock(return_value=expected)
        fake_tools = {"system": SimpleNamespace(trigger_crawl=trigger_crawl)}

        with patch("argus_server.server._get_tools", return_value=fake_tools):
            tool = await mcp.get_tool("trigger_crawl")
            response = await tool.run({})

        self.assertEqual(
            set(tool.parameters["properties"]),
            {"platforms", "save_to_local", "include_url"},
        )
        self.assertEqual(json.loads(response.content[0].text), expected)
        trigger_crawl.assert_called_once_with(
            platforms=None,
            save_to_local=False,
            include_url=False,
        )


if __name__ == "__main__":
    unittest.main()
