import copy
import json
import os
import tempfile
import unittest

from argus_server.tools.research_compare import ResearchComparisonTools


VALID_COMPARISON = {
    "title": "Transformer Resource Comparison",
    "overview": "The sources cover attention-based models from complementary angles.",
    "agreements": [
        {
            "statement": "Both sources treat attention as central to the architecture.",
            "citations": ["S1", "S2"],
        }
    ],
    "differences": [
        {
            "statement": "One source emphasizes the paper while the other emphasizes teaching.",
            "citations": ["S1", "S2"],
        }
    ],
    "evidence": [
        {"statement": "The paper describes self-attention.", "citations": ["S1"]},
        {"statement": "The course organizes related learning material.", "citations": ["S2"]},
    ],
    "open_questions": ["How should the materials be sequenced for study?"],
}


class FakeComparisonRunner:
    def __init__(self, payload=None, raises=False):
        self.payload = payload if payload is not None else VALID_COMPARISON
        self.raises = raises
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise RuntimeError("runner detail must not leak")
        return copy.deepcopy(self.payload)


def write_artifact(
    project_root,
    name,
    title,
    text,
    url,
    resource_type="paper",
):
    relative_path = os.path.join("output", "research", name)
    path = os.path.join(project_root, relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "query": title,
        "resource_type": resource_type,
        "resource": {"title": title, "authors": ["Example Author"]},
        "selection": {"url": url},
        "summary": {"summary": f"Summary for {title}"},
        "documents": [
            {
                "success": True,
                "page_title": title,
                "final_url": url,
                "text": text,
                "text_truncated": False,
            }
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return relative_path


class ResearchComparisonToolsTest(unittest.TestCase):
    def test_compares_artifacts_with_valid_source_citations(self):
        with tempfile.TemporaryDirectory() as project_root:
            paths = [
                write_artifact(
                    project_root,
                    "paper.json",
                    "Transformer Paper",
                    "PAPER_PRIVATE_EVIDENCE " * 80,
                    "https://arxiv.org/abs/1706.03762",
                ),
                write_artifact(
                    project_root,
                    "course.json",
                    "Transformer Course",
                    "COURSE_PRIVATE_EVIDENCE " * 80,
                    "https://example.edu/course",
                    resource_type="course",
                ),
            ]
            runner = FakeComparisonRunner()
            tool = ResearchComparisonTools(project_root, comparison_runner=runner)

            result = tool.research_compare_artifacts(
                paths,
                focus="Compare transformer learning resources",
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["summary"]["source_count"], 2)
            self.assertEqual(result["summary"]["claim_count"], 4)
            self.assertEqual(result["summary"]["citation_count"], 6)
            report = result["data"]
            self.assertEqual([source["source_id"] for source in report["sources"]], ["S1", "S2"])
            self.assertEqual(report["comparison"]["runner"], "injected")
            self.assertTrue(report["comparison"]["citation_validation"]["valid"])
            self.assertIn("## Evidence", report["brief"]["content"])
            self.assertIn("`S1`", report["brief"]["content"])
            self.assertEqual(report["handoff"]["status"], "partial")
            self.assertEqual(
                report["handoff"]["schema"],
                "argus.research.comparison.handoff.v1",
            )
            self.assertIn("PAPER_PRIVATE_EVIDENCE", runner.calls[0]["sources"][0]["text"])
            self.assertNotIn("PAPER_PRIVATE_EVIDENCE", json.dumps(report))

    def test_saves_json_and_markdown_with_ready_handoff(self):
        with tempfile.TemporaryDirectory() as project_root:
            paths = [
                write_artifact(project_root, "one.json", "One", "one evidence " * 80, "https://example.com/one"),
                write_artifact(project_root, "two.json", "Two", "two evidence " * 80, "https://example.com/two"),
            ]
            tool = ResearchComparisonTools(
                project_root,
                comparison_runner=FakeComparisonRunner(),
            )

            result = tool.research_compare_artifacts(paths, save=True)

            self.assertTrue(result["success"])
            handoff = result["data"]["handoff"]
            self.assertTrue(handoff["ready"])
            self.assertTrue(os.path.isfile(os.path.join(project_root, handoff["artifact_path"])))
            self.assertTrue(os.path.isfile(os.path.join(project_root, handoff["brief_path"])))
            self.assertNotIn(project_root, json.dumps(handoff))
            with open(os.path.join(project_root, handoff["artifact_path"]), encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertEqual(saved["comparison"]["claim_count"], 4)

    def test_requires_two_artifact_paths(self):
        runner = FakeComparisonRunner()
        tool = ResearchComparisonTools(comparison_runner=runner)

        result = tool.research_compare_artifacts(["one.json"])

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "NOT_ENOUGH_ARTIFACTS")
        self.assertEqual(runner.calls, [])

    def test_rejects_duplicate_artifacts_after_canonicalization(self):
        with tempfile.TemporaryDirectory() as project_root:
            path = write_artifact(project_root, "same.json", "Same", "evidence " * 80, "https://example.com")
            tool = ResearchComparisonTools(
                project_root,
                comparison_runner=FakeComparisonRunner(),
            )

            result = tool.research_compare_artifacts([path, path])

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "NOT_ENOUGH_UNIQUE_ARTIFACTS")

    def test_rejects_artifact_symlink_escape(self):
        with tempfile.TemporaryDirectory() as project_root, tempfile.TemporaryDirectory() as outside:
            valid = write_artifact(project_root, "valid.json", "Valid", "evidence " * 80, "https://example.com")
            outside_path = write_artifact(outside, "outside.json", "Outside", "outside " * 80, "https://outside.example")
            os.symlink(outside, os.path.join(project_root, "linked"))
            linked_path = os.path.join("linked", outside_path)
            tool = ResearchComparisonTools(
                project_root,
                comparison_runner=FakeComparisonRunner(),
            )

            result = tool.research_compare_artifacts([valid, linked_path])

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "UNSAFE_ARTIFACT_PATH")

    def test_rejects_artifact_without_readable_evidence(self):
        with tempfile.TemporaryDirectory() as project_root:
            valid = write_artifact(project_root, "valid.json", "Valid", "evidence " * 80, "https://example.com")
            empty = write_artifact(project_root, "empty.json", "Empty", "", "https://example.com/empty")
            tool = ResearchComparisonTools(
                project_root,
                comparison_runner=FakeComparisonRunner(),
            )

            result = tool.research_compare_artifacts([valid, empty])

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "NO_READABLE_EVIDENCE")
            self.assertEqual(result["error"]["artifact_index"], 1)

    def test_rejects_unknown_citations(self):
        payload = copy.deepcopy(VALID_COMPARISON)
        payload["agreements"][0]["citations"] = ["S1", "S9"]
        with tempfile.TemporaryDirectory() as project_root:
            paths = [
                write_artifact(project_root, "one.json", "One", "one " * 80, "https://example.com/one"),
                write_artifact(project_root, "two.json", "Two", "two " * 80, "https://example.com/two"),
            ]
            tool = ResearchComparisonTools(
                project_root,
                comparison_runner=FakeComparisonRunner(payload=payload),
            )

            result = tool.research_compare_artifacts(paths)

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "INVALID_CITATIONS")
            self.assertEqual(result["error"]["issues"][0]["citations"], ["S9"])

    def test_requires_cited_evidence(self):
        payload = copy.deepcopy(VALID_COMPARISON)
        payload["evidence"] = []
        with tempfile.TemporaryDirectory() as project_root:
            paths = [
                write_artifact(project_root, "one.json", "One", "one " * 80, "https://example.com/one"),
                write_artifact(project_root, "two.json", "Two", "two " * 80, "https://example.com/two"),
            ]
            tool = ResearchComparisonTools(
                project_root,
                comparison_runner=FakeComparisonRunner(payload=payload),
            )

            result = tool.research_compare_artifacts(paths)

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "MISSING_EVIDENCE")

    def test_rejects_unsafe_output_before_loading_artifacts(self):
        with tempfile.TemporaryDirectory() as project_root:
            runner = FakeComparisonRunner()
            tool = ResearchComparisonTools(project_root, comparison_runner=runner)

            result = tool.research_compare_artifacts(
                ["missing-one.json", "missing-two.json"],
                save=True,
                output_dir="../outside",
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "UNSAFE_OUTPUT_DIR")
            self.assertEqual(runner.calls, [])

    def test_sanitizes_runner_failure(self):
        with tempfile.TemporaryDirectory() as project_root:
            paths = [
                write_artifact(project_root, "one.json", "One", "one " * 80, "https://example.com/one"),
                write_artifact(project_root, "two.json", "Two", "two " * 80, "https://example.com/two"),
            ]
            tool = ResearchComparisonTools(
                project_root,
                comparison_runner=FakeComparisonRunner(raises=True),
            )

            result = tool.research_compare_artifacts(paths)

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "CODEX_RUNNER_ERROR")
            self.assertNotIn("runner detail", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
