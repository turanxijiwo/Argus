import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from argus_server.tools.research_toolkit import ResearchToolkitTools
from argus_server.tools.research_video import inspect_video_metadata


class ResearchVideoMetadataTest(unittest.TestCase):
    def test_extracts_allowlisted_metadata_without_media_urls(self):
        raw_metadata = {
            "id": "video-123",
            "title": "Public video",
            "description": "Public description",
            "webpage_url": "https://video.example/watch/video-123",
            "extractor": "youtube",
            "channel": "Example channel",
            "channel_url": "https://video.example/channel/example",
            "duration": 42,
            "upload_date": "20260714",
            "availability": "public",
            "live_status": "not_live",
            "view_count": 100,
            "tags": ["research", "metadata"],
            "url": "https://temporary.example/direct-stream.m3u8?token=secret",
            "formats": [{"url": "https://temporary.example/format.mp4"}],
            "requested_downloads": [{"url": "https://temporary.example/download.mp4"}],
            "thumbnails": [{"url": "https://temporary.example/thumb.jpg"}],
            "subtitles": {"en": [{"url": "https://temporary.example/subtitle.vtt"}]},
        }
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(raw_metadata),
            stderr="",
        )

        with patch("argus_server.tools.research_video.shutil.which", return_value="/usr/bin/yt-dlp"), patch(
            "argus_server.tools.research_video.subprocess.run", return_value=completed
        ) as run:
            result = inspect_video_metadata("https://video.example/watch/video-123", timeout=45)

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["schema"], "argus.research.video.metadata.v1")
        self.assertEqual(result["data"]["metadata"]["duration_seconds"], 42)
        self.assertEqual(
            result["data"]["metadata"]["source_page_url"],
            "https://video.example/watch/video-123",
        )
        self.assertFalse(result["data"]["safety"]["downloaded_media"])
        self.assertFalse(result["data"]["safety"]["direct_media_urls_included"])
        serialized = json.dumps(result)
        self.assertNotIn("temporary.example", serialized)
        self.assertNotIn("formats", serialized)
        self.assertNotIn("requested_downloads", serialized)

        command = run.call_args.args[0]
        self.assertIn("--simulate", command)
        self.assertIn("--no-cookies", command)
        self.assertIn("--no-cookies-from-browser", command)
        self.assertIn("--no-cache-dir", command)
        self.assertIn("--no-remote-components", command)
        self.assertIn("--no-playlist", command)
        self.assertEqual(command[-1], "https://video.example/watch/video-123")
        self.assertEqual(run.call_args.kwargs["timeout"], 45)
        self.assertFalse(run.call_args.kwargs["check"])

    def test_toolkit_method_delegates_to_video_adapter(self):
        expected = {"success": True, "data": {"metadata": {"id": "abc"}}}
        tool = ResearchToolkitTools()

        with patch(
            "argus_server.tools.research_toolkit.inspect_video_metadata",
            return_value=expected,
        ) as inspect:
            result = tool.research_video_metadata("https://video.example/watch/abc", timeout=30)

        self.assertEqual(result, expected)
        inspect.assert_called_once_with(
            url="https://video.example/watch/abc",
            timeout=30,
        )

    def test_toolkit_health_reports_yt_dlp_and_deno_ready(self):
        paths = {
            "yt-dlp": "/usr/bin/yt-dlp",
            "deno": "/usr/bin/deno",
        }
        with patch(
            "argus_server.tools.research_health.shutil.which",
            side_effect=lambda binary: paths.get(binary),
        ), patch(
            "argus_server.tools.research_health.importlib.util.find_spec",
            return_value=None,
        ):
            result = ResearchToolkitTools().toolkit_health()

        capability = result["data"]["capabilities"]["research_video_metadata"]
        self.assertTrue(capability["can_use_now"])
        self.assertEqual(capability["mode"], "yt_dlp_metadata_only")
        self.assertEqual(capability["javascript_runtime"], "deno")
        self.assertTrue(result["data"]["optional_cli"]["yt-dlp"]["installed"])
        self.assertTrue(result["data"]["optional_cli"]["deno"]["installed"])

    def test_rejects_non_http_url_before_running_command(self):
        with patch("argus_server.tools.research_video.shutil.which", return_value="/usr/bin/yt-dlp"), patch(
            "argus_server.tools.research_video.subprocess.run"
        ) as run:
            result = inspect_video_metadata("file:///tmp/video.mp4")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_URL")
        run.assert_not_called()

    def test_reports_missing_yt_dlp(self):
        with patch("argus_server.tools.research_video.shutil.which", return_value=None):
            result = inspect_video_metadata("https://video.example/watch/abc")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "NOT_INSTALLED")

    def test_reports_timeout_without_process_output(self):
        with patch("argus_server.tools.research_video.shutil.which", return_value="/usr/bin/yt-dlp"), patch(
            "argus_server.tools.research_video.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["yt-dlp"], timeout=10),
        ):
            result = inspect_video_metadata("https://video.example/watch/abc", timeout=1)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "TIMEOUT")
        self.assertEqual(result["error"]["timeout"], 10)

    def test_sanitizes_extractor_error_urls(self):
        completed = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ERROR: failed https://private.example/watch?token=secret",
        )
        with patch("argus_server.tools.research_video.shutil.which", return_value="/usr/bin/yt-dlp"), patch(
            "argus_server.tools.research_video.subprocess.run", return_value=completed
        ):
            result = inspect_video_metadata("https://video.example/watch/abc")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "EXTRACTOR_ERROR")
        self.assertEqual(result["error"]["detail"], "ERROR: failed [url]")
        self.assertNotIn("token=secret", json.dumps(result))

    def test_rejects_invalid_json_and_playlist_responses(self):
        invalid_json = SimpleNamespace(returncode=0, stdout="not-json", stderr="")
        playlist = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"_type": "playlist", "entries": []}),
            stderr="",
        )

        with patch("argus_server.tools.research_video.shutil.which", return_value="/usr/bin/yt-dlp"), patch(
            "argus_server.tools.research_video.subprocess.run",
            side_effect=[invalid_json, playlist],
        ):
            invalid_result = inspect_video_metadata("https://video.example/watch/abc")
            playlist_result = inspect_video_metadata("https://video.example/playlist/abc")

        self.assertEqual(invalid_result["error"]["code"], "PARSE_ERROR")
        self.assertEqual(playlist_result["error"]["code"], "UNSUPPORTED_TARGET")


if __name__ == "__main__":
    unittest.main()
