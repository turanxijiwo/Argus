import unittest
from unittest.mock import patch

import requests

from argus_server.tools import research_audio


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, params, headers, timeout):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        if self.error:
            raise self.error
        return self.response


class ResearchAudioTest(unittest.TestCase):
    def test_search_normalizes_dedupes_and_filters_without_download_metadata(self):
        audio_url = "https://cdn.example.com/birdsong.mp3"
        payload = {
            "result_count": 4,
            "results": [
                {
                    "title": "Woodland birdsong",
                    "foreign_landing_url": "https://example.com/sounds/1",
                    "url": audio_url,
                    "creator": "Example Creator",
                    "creator_url": "https://example.com/creators/1",
                    "provider": "freesound",
                    "license": "by",
                    "license_version": "4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution": "Woodland birdsong by Example Creator, CC BY 4.0",
                    "duration": 300267,
                    "filetype": "mp3",
                    "filesize": 6901092,
                    "mature": False,
                    "waveform": "https://api.openverse.org/waveform/1",
                    "alt_files": [{"url": "https://example.com/full.wav"}],
                },
                {"title": "Duplicate", "url": audio_url, "mature": False},
                {
                    "title": "Mature result",
                    "url": "https://example.com/mature.mp3",
                    "mature": True,
                },
                {"title": "Invalid URL", "url": "ftp://example.com/audio.mp3"},
            ],
        }
        response = FakeResponse(
            payload=payload,
            headers={
                "x-ratelimit-limit-anon_burst": "20/min",
                "x-ratelimit-available-anon_burst": "19",
                "x-ratelimit-limit-anon_sustained": "200/day",
                "x-ratelimit-available-anon_sustained": "199",
            },
        )
        session = FakeSession(response=response)

        with patch.object(research_audio, "create_research_session", return_value=session):
            result = research_audio.search_openverse_audio(
                "  birdsong  ",
                limit=50,
                timeout=1,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"], {"count": 1, "reported_result_count": 4})
        self.assertEqual(len(result["data"]["audio"]), 1)
        item = result["data"]["audio"][0]
        self.assertEqual(item["query"], "birdsong")
        self.assertEqual(item["source"], "audio:openverse")
        self.assertEqual(item["audio_url"], audio_url)
        self.assertEqual(item["duration_ms"], 300267)
        self.assertEqual(item["filesize"], 6901092)
        self.assertTrue(item["license_verification_required"])
        self.assertFalse(item["mature"])
        self.assertNotIn("waveform", item)
        self.assertNotIn("alt_files", item)
        self.assertIn("Made using Openverse", result["data"]["provider_notice"])
        self.assertIn("independently verify", result["data"]["license_notice"])
        self.assertEqual(
            result["data"]["rate_limit"]["anonymous_sustained_limit"],
            "200/day",
        )
        self.assertEqual(
            session.calls,
            [
                {
                    "url": research_audio.OPENVERSE_AUDIO_URL,
                    "params": {"q": "birdsong", "page_size": 20, "mature": "false"},
                    "headers": {"Accept": "application/json"},
                    "timeout": 3,
                }
            ],
        )

    def test_search_rejects_empty_query_before_creating_session(self):
        with patch.object(research_audio, "create_research_session") as create_session:
            result = research_audio.search_openverse_audio(" \n ")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_QUERY")
        create_session.assert_not_called()

    def test_search_preserves_rate_limit_metadata(self):
        response = FakeResponse(
            payload={},
            status_code=429,
            headers={
                "retry-after": "60",
                "x-ratelimit-available-anon_burst": "0",
            },
        )
        session = FakeSession(response=response)

        with patch.object(research_audio, "create_research_session", return_value=session):
            result = research_audio.search_openverse_audio("birdsong")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "RATE_LIMITED")
        self.assertEqual(result["error"]["rate_limit"]["retry_after"], "60")

    def test_search_reports_timeout(self):
        session = FakeSession(error=requests.Timeout("timed out"))

        with patch.object(research_audio, "create_research_session", return_value=session):
            result = research_audio.search_openverse_audio("birdsong")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "TIMEOUT")

    def test_search_reports_invalid_json(self):
        session = FakeSession(response=FakeResponse(payload=ValueError("invalid")))

        with patch.object(research_audio, "create_research_session", return_value=session):
            result = research_audio.search_openverse_audio("birdsong")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_PROVIDER_RESPONSE")

    def test_search_rejects_missing_results_list(self):
        session = FakeSession(response=FakeResponse(payload={"result_count": 1}))

        with patch.object(research_audio, "create_research_session", return_value=session):
            result = research_audio.search_openverse_audio("birdsong")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_PROVIDER_RESPONSE")


if __name__ == "__main__":
    unittest.main()
