import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from argus_server.server import mcp


class MCPRegistrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_research_toolkit_tools_are_registered(self):
        tools = await mcp.get_tools()
        expected_research_tools = {
            "research_toolkit_health",
            "crawl_url",
            "discover_page_images",
            "research_images",
            "research_audio",
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

        self.assertEqual(len(tools), 172)
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


if __name__ == "__main__":
    unittest.main()
