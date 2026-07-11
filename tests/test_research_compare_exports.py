import json
import os
import tempfile
import unittest

from argus_server.tools.research_citation_bundle import (
    build_comparison_citation_bundle,
    save_comparison_citation_bundle,
)
from argus_server.tools.research_compare import ResearchComparisonTools
from tests.test_research_compare import FakeComparisonRunner, write_artifact


class ResearchComparisonExportsTest(unittest.TestCase):
    def test_builds_bundle_with_unique_csl_ids(self):
        sources = [
            self._source("S1", "same-key", "First"),
            self._source("S2", "same-key", "Second"),
        ]

        result = build_comparison_citation_bundle(sources)

        self.assertTrue(result["success"])
        self.assertEqual(
            [item["id"] for item in result["data"]["csl_json"]],
            ["same-key", "same-key-s2"],
        )
        self.assertEqual(result["data"]["ris"].count("ER  -"), 2)

    def test_saves_comparison_citation_files_and_handoff_paths(self):
        with tempfile.TemporaryDirectory() as project_root:
            paths = [
                write_artifact(
                    project_root, "one.json", "One", "one evidence " * 80,
                    "https://example.com/one",
                ),
                write_artifact(
                    project_root, "two.json", "Two", "two evidence " * 80,
                    "https://example.com/two",
                ),
            ]
            tool = ResearchComparisonTools(
                project_root,
                comparison_runner=FakeComparisonRunner(),
            )

            result = tool.research_compare_artifacts(
                paths,
                save=True,
                save_citations=True,
            )

            self.assertTrue(result["success"])
            self.assertTrue(result["summary"]["citations_saved"])
            handoff = result["data"]["handoff"]
            self.assertTrue(os.path.isfile(os.path.join(project_root, handoff["csl_json_path"])))
            self.assertTrue(os.path.isfile(os.path.join(project_root, handoff["ris_path"])))
            self.assertNotIn(project_root, json.dumps(handoff))
            with open(os.path.join(project_root, handoff["csl_json_path"]), encoding="utf-8") as handle:
                csl_items = json.load(handle)
            with open(os.path.join(project_root, handoff["ris_path"]), encoding="utf-8") as handle:
                ris = handle.read()
            self.assertEqual(len(csl_items), 2)
            self.assertEqual(ris.count("ER  -"), 2)
            with open(os.path.join(project_root, handoff["artifact_path"]), encoding="utf-8") as handle:
                saved_report = json.load(handle)
            self.assertEqual(
                saved_report["citation_artifacts"]["csl_json"]["item_count"],
                2,
            )

    def test_requires_report_save_for_citation_files(self):
        runner = FakeComparisonRunner()
        tool = ResearchComparisonTools(comparison_runner=runner)

        result = tool.research_compare_artifacts(
            ["missing-one.json", "missing-two.json"],
            save_citations=True,
        )

        self.assertFalse(result["success"])
        self.assertEqual(
            result["error"]["code"],
            "CITATION_SAVE_REQUIRES_REPORT_SAVE",
        )
        self.assertEqual(runner.calls, [])

    def test_rejects_unsafe_bundle_output(self):
        with tempfile.TemporaryDirectory() as project_root:
            result = save_comparison_citation_bundle(
                project_root=project_root,
                sources=[self._source("S1", "one", "One")],
                output_dir="../outside",
                query="comparison",
                timestamp="20260711T000000Z",
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "UNSAFE_OUTPUT_DIR")

    @staticmethod
    def _source(source_id: str, citation_id: str, title: str):
        return {
            "source_id": source_id,
            "citation": {
                "csl_json": {"id": citation_id, "type": "article", "title": title},
                "ris": f"TY  - GEN\nTI  - {title}\nER  -",
            },
        }


if __name__ == "__main__":
    unittest.main()
