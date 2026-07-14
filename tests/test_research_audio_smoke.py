import argparse
import asyncio
import importlib.util
import io
import json
import pathlib
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_audio_smoke.py"
SPEC = importlib.util.spec_from_file_location("research_audio_smoke", SCRIPT_PATH)
research_audio_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_audio_smoke)


def successful_result():
    return {
        "success": True,
        "data": {
            "audio": [
                {
                    "title": "Woodland birdsong",
                    "audio_url": "https://cdn.example.com/birdsong.mp3",
                    "source_page_url": "https://example.com/sounds/1",
                    "source": "audio:openverse",
                    "provider": "freesound",
                    "license": "by",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution": "Woodland birdsong by Example Creator, CC BY 4.0",
                    "mature": False,
                    "license_verification_required": True,
                }
            ],
            "provider_notice": "Made using Openverse.",
            "license_notice": "Independently verify usage rights.",
            "rate_limit": {"anonymous_sustained_limit": "200/day"},
        },
    }


class FakeMCPTool:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def run(self, arguments):
        self.calls.append(arguments)
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(self.result))]
        )


class FakeMCPServer:
    def __init__(self, tool):
        self.tool = tool
        self.requested_tools = []

    async def get_tool(self, name):
        self.requested_tools.append(name)
        return self.tool


class ResearchAudioSmokeTest(unittest.TestCase):
    def test_invoke_registered_audio_uses_public_mcp_tool(self):
        tool = FakeMCPTool(successful_result())
        mcp_server = FakeMCPServer(tool)

        result = asyncio.run(
            research_audio_smoke.invoke_registered_audio(
                "birdsong", 2, 12, mcp_server=mcp_server
            )
        )

        self.assertEqual(result, successful_result())
        self.assertEqual(mcp_server.requested_tools, ["research_audio"])
        self.assertEqual(
            tool.calls,
            [{"query": "birdsong", "limit": 2, "timeout": 12}],
        )

    def test_run_smoke_passes_metadata_only_contract(self):
        calls = []

        def invoke_audio(query, limit, timeout):
            calls.append((query, limit, timeout))
            return successful_result()

        args = argparse.Namespace(query="birdsong", limit=2, min_results=1, timeout=12)
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = research_audio_smoke.run_smoke(args, invoke_audio=invoke_audio)

        summary = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(summary["passed"])
        self.assertFalse(summary["download_requested"])
        self.assertTrue(summary["checks"]["metadata_only"])
        self.assertEqual(summary["mcp_tool"], "research_audio")
        self.assertEqual(calls, [("birdsong", 2, 12)])

    def test_summary_rejects_duplicate_mature_incomplete_and_media_fields(self):
        result = successful_result()
        duplicate = dict(result["data"]["audio"][0])
        duplicate.update({"license": "", "mature": True, "waveform": "encoded"})
        result["data"]["audio"].append(duplicate)

        summary = research_audio_smoke.summarize_audio(result, min_results=1)

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["checks"]["unique_audio_urls"])
        self.assertFalse(summary["checks"]["non_mature"])
        self.assertFalse(summary["checks"]["license_metadata"])
        self.assertFalse(summary["checks"]["metadata_only"])
        self.assertEqual(summary["exit_code"], 3)

    def test_rate_limit_is_reported_as_unavailable(self):
        result = {
            "success": False,
            "error": {"code": "RATE_LIMITED", "message": "Try later"},
        }

        summary = research_audio_smoke.summarize_audio(result, min_results=1)

        self.assertEqual(summary["status"], "unavailable")
        self.assertEqual(summary["exit_code"], 2)

    def test_invalid_provider_response_is_a_contract_failure(self):
        result = {
            "success": False,
            "error": {
                "code": "INVALID_PROVIDER_RESPONSE",
                "message": "Missing results",
            },
        }

        summary = research_audio_smoke.summarize_audio(result, min_results=1)

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["exit_code"], 3)

    def test_malformed_audio_collection_is_a_contract_failure(self):
        result = {
            "success": True,
            "data": {
                "audio": {"unexpected": "mapping"},
                "provider_notice": "Made using Openverse.",
                "license_notice": "Independently verify usage rights.",
                "rate_limit": {"anonymous_sustained_limit": "200/day"},
            },
        }

        summary = research_audio_smoke.summarize_audio(result, min_results=1)

        self.assertFalse(summary["checks"]["audio_list"])
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["exit_code"], 3)

    def test_run_smoke_reports_malformed_mcp_output_as_contract_failure(self):
        args = argparse.Namespace(query="birdsong", limit=2, min_results=1, timeout=12)
        output = io.StringIO()

        def invalid_output(query, limit, timeout):
            raise ValueError("MCP response must contain a JSON object")

        with redirect_stdout(output):
            exit_code = research_audio_smoke.run_smoke(args, invoke_audio=invalid_output)

        summary = json.loads(output.getvalue())
        self.assertEqual(exit_code, 3)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["tool_error"]["code"], "MCP_CONTRACT_ERROR")


if __name__ == "__main__":
    unittest.main()
