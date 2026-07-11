import unittest

from argus_server.server import mcp


class MCPRegistrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_research_toolkit_tools_are_registered(self):
        tools = await mcp.get_tools()
        expected_research_tools = {
            "research_toolkit_health",
            "crawl_url",
            "discover_page_images",
            "research_images",
            "research_pack",
            "research_workflow",
            "research_batch_workflow",
            "research_review_artifact",
            "research_runtime_probe",
            "find_research_resource",
            "research_resource_workflow",
            "research_compare_artifacts",
            "research_resolve_locators",
            "download_gallery",
            "research_topic",
        }

        self.assertEqual(len(tools), 170)
        self.assertTrue(expected_research_tools.issubset(tools))

        for tool_name in expected_research_tools:
            registered_tool = await mcp.get_tool(tool_name)
            self.assertEqual(registered_tool.name, tool_name)


if __name__ == "__main__":
    unittest.main()
