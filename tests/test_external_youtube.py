import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from argus_server.tools.external_apis import ExternalAPITools


class FakeResponse:
    def __init__(self, status_code=200, content=b"<feed />"):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class ExternalYoutubeTest(unittest.TestCase):
    channel_id = "UC4QobU6STFB0P71PMvOGN5A"

    def test_youtube_rss_remains_primary_transport(self):
        tools = ExternalAPITools()
        tools._get = Mock(return_value=FakeResponse())
        feed = SimpleNamespace(
            entries=[
                SimpleNamespace(
                    title="RSS video",
                    link="https://www.youtube.com/watch?v=jNQXAC9IVRw",
                    yt_videoid="jNQXAC9IVRw",
                    published="2005-04-24T00:00:00Z",
                    author="Example channel",
                    summary="Public description",
                )
            ],
            feed={"title": "Example channel"},
        )

        with patch("argus_server.tools.external_apis.feedparser.parse", return_value=feed), patch(
            "argus_server.tools.external_apis.inspect_channel_videos"
        ) as fallback:
            result = tools.get_youtube_channel(self.channel_id, limit=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["transport"], "youtube_rss")
        self.assertEqual(result["data"]["videos"][0]["video_id"], "jNQXAC9IVRw")
        fallback.assert_not_called()

    def test_youtube_404_uses_metadata_only_ytdlp_fallback(self):
        tools = ExternalAPITools()
        tools._get = Mock(return_value=FakeResponse(status_code=404))
        fallback_result = {
            "success": True,
            "data": {
                "channel_title": "Example channel",
                "videos": [
                    {
                        "title": "Fallback video",
                        "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
                        "video_id": "jNQXAC9IVRw",
                        "published": "20050424",
                        "author": "Example channel",
                        "description": "",
                    }
                ],
                "safety": {"downloaded_media": False, "cookies_used": False},
            },
        }

        with patch(
            "argus_server.tools.external_apis.inspect_channel_videos",
            return_value=fallback_result,
        ) as fallback:
            result = tools.get_youtube_channel(self.channel_id, limit=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["transport"], "yt_dlp_flat_playlist")
        self.assertEqual(result["summary"]["fallback_from"], "NOT_FOUND")
        self.assertEqual(result["data"]["videos"][0]["video_id"], "jNQXAC9IVRw")
        fallback.assert_called_once_with(self.channel_id, limit=1, timeout=60)

    def test_youtube_reports_both_transport_failures(self):
        tools = ExternalAPITools()
        tools._get = Mock(return_value=FakeResponse(status_code=404))

        with patch(
            "argus_server.tools.external_apis.inspect_channel_videos",
            return_value={
                "success": False,
                "error": {"code": "NOT_INSTALLED", "message": "yt-dlp missing"},
            },
        ):
            result = tools.get_youtube_channel(self.channel_id, limit=1)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "ALL_SOURCES_FAILED")
        self.assertEqual(
            [item["transport"] for item in result["error"]["source_errors"]],
            ["youtube_rss", "yt_dlp_flat_playlist"],
        )

    def test_youtube_rejects_invalid_limit_before_network_or_fallback(self):
        tools = ExternalAPITools()
        tools._get = Mock()

        with patch("argus_server.tools.external_apis.inspect_channel_videos") as fallback:
            result = tools.get_youtube_channel(self.channel_id, limit="many")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_PARAM")
        tools._get.assert_not_called()
        fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
