import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from argus_server.server import mcp


class MCPRegistrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_server_initializes_from_non_project_workdir(self):
        project_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as working_dir:
            transport = StdioTransport(
                command=sys.executable,
                args=[
                    "-m",
                    "argus_server.server",
                    "--project-root",
                    str(project_root),
                ],
                cwd=working_dir,
            )
            async with Client(transport, init_timeout=20) as client:
                tools = await client.list_tools()
                resources = await client.list_resources()
                system_health = await client.call_tool("system_health", {})
                toolkit_health = await client.call_tool(
                    "research_toolkit_health",
                    {},
                )

        self.assertEqual(len(tools), 173)
        self.assertEqual(len(resources), 8)
        self.assertTrue(json.loads(system_health.content[0].text)["success"])
        self.assertTrue(json.loads(toolkit_health.content[0].text)["success"])

    def test_server_cli_rejects_invalid_transport(self):
        project_root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as working_dir:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "argus_server.server",
                    "--transport",
                    "invalid",
                    "--project-root",
                    str(project_root),
                ],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("invalid choice", completed.stderr)

    async def test_retired_crossref_events_tool_is_not_registered(self):
        tools = await mcp.get_tools()

        self.assertNotIn("get_crossref_events", tools)

    async def test_research_toolkit_tools_are_registered(self):
        tools = await mcp.get_tools()
        expected_research_tools = {
            "research_toolkit_health",
            "crawl_url",
            "discover_page_images",
            "research_images",
            "research_audio",
            "research_video_metadata",
            "research_pack",
            "research_workflow",
            "research_batch_workflow",
            "research_review_artifact",
            "research_runtime_probe",
            "find_research_resource",
            "research_resource_workflow",
            "research_compare_artifacts",
            "research_audit_comparison",
            "research_resolve_locators",
            "download_gallery",
            "research_topic",
        }

        self.assertEqual(len(tools), 173)
        self.assertIn("initialize_config", tools)
        self.assertTrue(expected_research_tools.issubset(tools))

        for tool_name in expected_research_tools:
            registered_tool = await mcp.get_tool(tool_name)
            self.assertEqual(registered_tool.name, tool_name)

        comparison_tool = await mcp.get_tool("research_compare_artifacts")
        self.assertIn("save_citations", comparison_tool.parameters["properties"])
        audit_tool = await mcp.get_tool("research_audit_comparison")
        self.assertEqual(
            set(audit_tool.parameters["properties"]),
            {"comparison_artifact_path"},
        )
        audio_tool = await mcp.get_tool("research_audio")
        self.assertEqual(
            set(audio_tool.parameters["properties"]),
            {"query", "limit", "timeout"},
        )
        self.assertEqual(audio_tool.parameters["required"], ["query"])
        video_tool = await mcp.get_tool("research_video_metadata")
        self.assertEqual(
            set(video_tool.parameters["properties"]),
            {"url", "timeout"},
        )
        self.assertEqual(video_tool.parameters["required"], ["url"])

    async def test_research_audio_mcp_delegates_and_serializes_result(self):
        expected = {"success": True, "data": {"audio": [{"title": "Birdsong"}]}}
        research_audio = Mock(return_value=expected)
        fake_tools = {"research": SimpleNamespace(research_audio=research_audio)}

        with patch("argus_server.server._get_tools", return_value=fake_tools):
            tool = await mcp.get_tool("research_audio")
            result = await tool.run(
                {"query": "birdsong", "limit": 7, "timeout": 12}
            )

        self.assertEqual(json.loads(result.content[0].text), expected)
        research_audio.assert_called_once_with(
            query="birdsong",
            limit=7,
            timeout=12,
        )

    async def test_research_audio_mcp_preserves_structured_adapter_error(self):
        expected = {
            "success": False,
            "error": {"code": "RATE_LIMITED", "message": "Openverse rate limit reached"},
        }
        research_audio = Mock(return_value=expected)
        fake_tools = {"research": SimpleNamespace(research_audio=research_audio)}

        with patch("argus_server.server._get_tools", return_value=fake_tools):
            tool = await mcp.get_tool("research_audio")
            result = await tool.run({"query": "birdsong"})

        self.assertEqual(json.loads(result.content[0].text), expected)
        research_audio.assert_called_once_with(
            query="birdsong",
            limit=5,
            timeout=20,
        )

    async def test_research_video_metadata_mcp_delegates_and_serializes_result(self):
        expected = {
            "success": True,
            "data": {"metadata": {"id": "video-123", "title": "Public video"}},
        }
        inspect = Mock(return_value=expected)
        fake_tools = {"research": SimpleNamespace(research_video_metadata=inspect)}

        with patch("argus_server.server._get_tools", return_value=fake_tools):
            tool = await mcp.get_tool("research_video_metadata")
            result = await tool.run(
                {"url": "https://video.example/watch/video-123", "timeout": 45}
            )

        self.assertEqual(json.loads(result.content[0].text), expected)
        inspect.assert_called_once_with(
            url="https://video.example/watch/video-123",
            timeout=45,
        )

    async def test_research_video_metadata_mcp_preserves_structured_error(self):
        expected = {
            "success": False,
            "error": {"code": "EXTRACTOR_ERROR", "message": "metadata unavailable"},
        }
        inspect = Mock(return_value=expected)
        fake_tools = {"research": SimpleNamespace(research_video_metadata=inspect)}

        with patch("argus_server.server._get_tools", return_value=fake_tools):
            tool = await mcp.get_tool("research_video_metadata")
            result = await tool.run({"url": "https://video.example/watch/missing"})

        self.assertEqual(json.loads(result.content[0].text), expected)
        inspect.assert_called_once_with(
            url="https://video.example/watch/missing",
            timeout=60,
        )


if __name__ == "__main__":
    unittest.main()
