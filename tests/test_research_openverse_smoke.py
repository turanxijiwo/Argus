import argparse
import importlib.util
import io
import json
import pathlib
import unittest
from contextlib import redirect_stdout


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_openverse_smoke.py"
SPEC = importlib.util.spec_from_file_location("research_openverse_smoke", SCRIPT_PATH)
research_openverse_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_openverse_smoke)


def successful_result():
    return {
        "success": True,
        "data": {
            "images": [
                {
                    "image_url": "https://images.example.edu/campus.jpg",
                    "source_page_url": "https://example.edu/campus",
                    "source": "image:openverse",
                    "provider": "wikimedia",
                    "license": "by-sa",
                    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "attribution": "Campus by Example Author, CC BY-SA 4.0",
                    "mature": False,
                    "license_verification_required": True,
                }
            ],
            "sources": {
                "image:openverse": {
                    "success": True,
                    "data": {
                        "provider_notice": "Made using Openverse.",
                        "license_notice": "Independently verify usage rights.",
                        "rate_limit": {"anonymous_sustained_limit": "200/day"},
                    },
                }
            },
            "source_errors": [],
        },
    }


class FakeResearch:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def research_images(self, query, sources, limit, timeout):
        self.calls.append(
            {
                "query": query,
                "sources": sources,
                "limit": limit,
                "timeout": timeout,
            }
        )
        return self.result

    def download_gallery(self, *args, **kwargs):
        raise AssertionError("The Openverse smoke must not download media")


class ResearchOpenverseSmokeTest(unittest.TestCase):
    def test_run_smoke_passes_quality_contract_without_downloading(self):
        research = FakeResearch(successful_result())
        args = argparse.Namespace(query="test query", limit=3, min_results=1, timeout=10)
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = research_openverse_smoke.run_smoke(args, research=research)

        summary = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(summary["passed"])
        self.assertFalse(summary["download_requested"])
        self.assertTrue(summary["checks"]["license_metadata"])
        self.assertEqual(
            research.calls,
            [
                {
                    "query": "test query",
                    "sources": ["image:openverse"],
                    "limit": 3,
                    "timeout": 10,
                }
            ],
        )

    def test_summary_rejects_duplicate_mature_and_incomplete_results(self):
        result = successful_result()
        duplicate = dict(result["data"]["images"][0])
        duplicate.update({"license": "", "mature": True})
        result["data"]["images"].append(duplicate)

        summary = research_openverse_smoke.summarize_images(result, min_results=1)

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["checks"]["unique_image_urls"])
        self.assertFalse(summary["checks"]["non_mature"])
        self.assertFalse(summary["checks"]["license_metadata"])
        self.assertEqual(summary["exit_code"], 3)

    def test_rate_limit_is_reported_as_unavailable(self):
        result = {
            "success": True,
            "data": {
                "images": [],
                "sources": {
                    "image:openverse": {
                        "success": False,
                        "error": {"code": "RATE_LIMITED", "message": "Try later"},
                    }
                },
                "source_errors": [
                    {"source": "image:openverse", "code": "RATE_LIMITED", "message": "Try later"}
                ],
            },
        }

        summary = research_openverse_smoke.summarize_images(result, min_results=1)

        self.assertEqual(summary["status"], "unavailable")
        self.assertEqual(summary["exit_code"], 2)

    def test_invalid_provider_response_is_a_contract_failure(self):
        result = {
            "success": True,
            "data": {
                "images": [],
                "sources": {},
                "source_errors": [
                    {
                        "source": "image:openverse",
                        "code": "INVALID_PROVIDER_RESPONSE",
                        "message": "Missing results",
                    }
                ],
            },
        }

        summary = research_openverse_smoke.summarize_images(result, min_results=1)

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["exit_code"], 3)


if __name__ == "__main__":
    unittest.main()
