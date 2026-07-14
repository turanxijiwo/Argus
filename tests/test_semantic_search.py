import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from argus_server.tools.semantic_search import SemanticSearchTools


class FakeStorageManager:
    def __init__(self, news_data=None, read_error=None):
        self.news_data = news_data
        self.read_error = read_error
        self.read_thread = None
        self.cleanup_thread = None
        self.cleanup_calls = 0

    def get_today_all_data(self, date):
        self.read_thread = threading.get_ident()
        if self.read_error:
            raise self.read_error
        return self.news_data

    def cleanup(self):
        self.cleanup_calls += 1
        self.cleanup_thread = threading.get_ident()


class SemanticIndexStorageLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.project_root = Path(self.tmpdir.name).resolve()
        news_dir = self.project_root / "output" / "news"
        news_dir.mkdir(parents=True)
        (news_dir / "2026-07-14.db").touch()
        self.tools = SemanticSearchTools(str(self.project_root))

    def _rebuild(self, manager):
        with (
            patch(
                "argus.storage.get_storage_manager",
                side_effect=AssertionError("global storage manager must not be used"),
            ),
            patch("argus.storage.StorageManager", return_value=manager) as constructor,
            patch(
                "argus_server.tools.semantic_search._tokenize",
                side_effect=lambda text: text.lower().split(),
            ),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            response = executor.submit(self.tools.rebuild, 30).result()

        constructor.assert_called_once_with(
            backend_type="local",
            data_dir=str(self.project_root / "output"),
            enable_txt=False,
            enable_html=False,
        )
        return response

    def test_rebuild_uses_scoped_manager_and_cleans_up_in_worker_thread(self):
        news_data = SimpleNamespace(
            items={
                "demo": [
                    SimpleNamespace(
                        title="AI policy update",
                        url="https://example.com/ai-policy",
                    )
                ]
            },
            id_to_name={"demo": "Demo"},
        )
        manager = FakeStorageManager(news_data=news_data)

        response = self._rebuild(manager)

        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["doc_count"], 1)
        self.assertEqual(manager.cleanup_calls, 1)
        self.assertEqual(manager.cleanup_thread, manager.read_thread)
        self.assertTrue(self.tools.index_path.exists())
        self.assertTrue(self.tools.meta_path.exists())

    def test_rebuild_cleans_up_when_date_read_fails(self):
        manager = FakeStorageManager(read_error=RuntimeError("database unavailable"))

        response = self._rebuild(manager)

        self.assertFalse(response["success"])
        self.assertEqual(response["error"]["code"], "NO_DATA")
        self.assertEqual(manager.cleanup_calls, 1)
        self.assertEqual(manager.cleanup_thread, manager.read_thread)


if __name__ == "__main__":
    unittest.main()
