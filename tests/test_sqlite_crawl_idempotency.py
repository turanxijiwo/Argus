import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from argus.storage.base import NewsData, NewsItem, RSSData, RSSItem
from argus.storage.local import LocalStorageBackend


TEST_DATE = "2026-07-14"


class SQLiteCrawlIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.backend = LocalStorageBackend(
            data_dir=str(self.data_dir),
            enable_txt=False,
            enable_html=False,
        )

    def tearDown(self):
        self.backend.cleanup()
        self.temp_dir.cleanup()

    @staticmethod
    def _news_data(crawl_time, rank=1):
        return NewsData(
            date=TEST_DATE,
            crawl_time=crawl_time,
            items={
                "source": [
                    NewsItem(
                        title=f"Example news rank {rank}",
                        source_id="source",
                        source_name="Source",
                        rank=rank,
                        url="https://example.com/news/1",
                    )
                ]
            },
            id_to_name={"source": "Source"},
        )

    @staticmethod
    def _rss_data(crawl_time, title="Example article"):
        return RSSData(
            date=TEST_DATE,
            crawl_time=crawl_time,
            items={
                "feed": [
                    RSSItem(
                        title=title,
                        feed_id="feed",
                        feed_name="Feed",
                        url="https://example.com/article/1",
                    )
                ]
            },
            id_to_name={"feed": "Feed"},
        )

    def _query_news(self, sql):
        db_path = self.data_dir / "news" / f"{TEST_DATE}.db"
        with sqlite3.connect(db_path) as conn:
            return conn.execute(sql).fetchall()

    def _query_rss(self, sql):
        db_path = self.data_dir / "rss" / f"{TEST_DATE}.db"
        with sqlite3.connect(db_path) as conn:
            return conn.execute(sql).fetchall()

    def test_distinct_news_crawl_times_accumulate_normally(self):
        self.assertTrue(self.backend.save_news_data(self._news_data("18-00", rank=1)))
        self.assertTrue(self.backend.save_news_data(self._news_data("18-01", rank=2)))

        self.assertEqual(self._query_news("SELECT COUNT(*) FROM crawl_records"), [(2,)])
        self.assertEqual(self._query_news("SELECT COUNT(*) FROM rank_history"), [(2,)])
        self.assertEqual(
            self._query_news("SELECT rank, crawl_count FROM news_items"),
            [(2, 2)],
        )

    def test_same_minute_news_retry_is_a_no_op(self):
        self.assertTrue(self.backend.save_news_data(self._news_data("18-00", rank=1)))
        self.assertTrue(self.backend.save_news_data(self._news_data("18-00", rank=2)))

        self.assertEqual(self._query_news("SELECT COUNT(*) FROM crawl_records"), [(1,)])
        self.assertEqual(self._query_news("SELECT COUNT(*) FROM rank_history"), [(1,)])
        self.assertEqual(
            self._query_news("SELECT rank, crawl_count FROM news_items"),
            [(1, 1)],
        )

    def test_concurrent_same_minute_news_writes_store_one_crawl(self):
        self.backend._get_connection(TEST_DATE)
        self.backend.cleanup()
        barrier = threading.Barrier(2)

        def save_from_worker(rank):
            backend = LocalStorageBackend(
                data_dir=str(self.data_dir),
                enable_txt=False,
                enable_html=False,
            )
            try:
                backend._get_connection(TEST_DATE)
                barrier.wait(timeout=5)
                return backend.save_news_data(self._news_data("18-00", rank=rank))
            finally:
                backend.cleanup()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(save_from_worker, (1, 2)))

        self.assertEqual(outcomes, [True, True])
        self.assertEqual(self._query_news("SELECT COUNT(*) FROM crawl_records"), [(1,)])
        self.assertEqual(self._query_news("SELECT COUNT(*) FROM rank_history"), [(1,)])
        stored_rank, crawl_count = self._query_news(
            "SELECT rank, crawl_count FROM news_items"
        )[0]
        self.assertIn(stored_rank, (1, 2))
        self.assertEqual(crawl_count, 1)

    def test_failed_crawl_claim_rolls_back_transaction(self):
        invalid_data = self._news_data(None)

        self.assertFalse(self.backend.save_news_data(invalid_data))
        self.assertTrue(self.backend.save_news_data(self._news_data("18-00")))

        self.assertEqual(
            self._query_news("SELECT crawl_time FROM crawl_records"),
            [("18-00",)],
        )

    def test_same_minute_rss_retry_is_a_no_op(self):
        self.assertTrue(self.backend.save_rss_data(self._rss_data("18-00")))
        self.assertTrue(
            self.backend.save_rss_data(
                self._rss_data("18-00", title="Changed on duplicate run")
            )
        )

        self.assertEqual(self._query_rss("SELECT COUNT(*) FROM rss_crawl_records"), [(1,)])
        self.assertEqual(
            self._query_rss("SELECT title, crawl_count FROM rss_items"),
            [("Example article", 1)],
        )


if __name__ == "__main__":
    unittest.main()
