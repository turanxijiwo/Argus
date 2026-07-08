import argparse
import contextlib
import io
import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_batch_workflow.py"
SPEC = importlib.util.spec_from_file_location("research_batch_workflow", SCRIPT_PATH)
research_batch_workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_batch_workflow)


class FakeReviewModule:
    @staticmethod
    def review_collection(paths, project_root):
        return {
            "success": True,
            "artifact_count": len(paths),
            "status_counts": {"ready": len(paths)},
            "average_score": 100,
            "reviews": [],
        }

    @staticmethod
    def render_markdown_report(report):
        return "# Research Artifact Review\n"

    @staticmethod
    def write_report(content, path, project_root):
        return {"success": True, "path": "output/research/artifact-reviews/batch-review.md"}


class FakeResearchTools:
    def __init__(self, project_root):
        self.project_root = pathlib.Path(project_root)

    def research_workflow(self, query, **kwargs):
        artifact_path = self.project_root / kwargs["output_dir"] / "research.json"
        brief_path = self.project_root / kwargs["output_dir"] / "research.md"
        return {
            "success": True,
            "data": {
                "artifact": {"path": str(artifact_path)},
                "brief": {
                    "content": "# Brief\n",
                    "artifact": {"path": str(brief_path)},
                },
                "documents": [{"success": True}],
                "images": [],
                "source_errors": [],
            },
        }


class ResearchBatchWorkflowTest(unittest.TestCase):
    def test_load_queries_dedupes_cli_and_file_queries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_path = pathlib.Path(tmpdir) / "queries.txt"
            queries_path.write_text("# comment\nOpenAI\nAI safety\nOpenAI\n", encoding="utf-8")
            args = argparse.Namespace(query=["OpenAI", "Browser agents"], queries_file=str(queries_path))

            queries = research_batch_workflow.load_queries(args)

            self.assertEqual(queries, ["OpenAI", "Browser agents", "AI safety"])

    def test_read_queries_file_accepts_json_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            queries_path = pathlib.Path(tmpdir) / "queries.json"
            queries_path.write_text('["OpenAI", "AI safety"]', encoding="utf-8")

            queries = research_batch_workflow.read_queries_file(str(queries_path))

            self.assertEqual(queries, ["OpenAI", "AI safety"])

    def test_summarize_workflow_result_tracks_artifact_and_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = {
                "success": True,
                "data": {
                    "artifact": {"path": str(pathlib.Path(tmpdir) / "research.json")},
                    "brief": {
                        "content": "# Brief",
                        "artifact": {"path": str(pathlib.Path(tmpdir) / "research.md")},
                    },
                    "documents": [{"success": True}, {"success": False}],
                    "images": [{"image_url": "https://example.com/image.png"}],
                    "source_errors": [{"source": "wikipedia", "code": "NETWORK_ERROR"}],
                },
            }

            summary = research_batch_workflow.summarize_workflow_result("OpenAI", result, tmpdir)

            self.assertTrue(summary["success"])
            self.assertEqual(summary["artifact_path"], "research.json")
            self.assertEqual(summary["brief_path"], "research.md")
            self.assertEqual(summary["document_count"], 2)
            self.assertEqual(summary["successful_document_count"], 1)
            self.assertEqual(summary["source_error_count"], 1)
            self.assertEqual(summary["crawl_error_count"], 1)

    def test_build_review_uses_review_module_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(research_batch_workflow, "load_review_module", return_value=FakeReviewModule):
                report = research_batch_workflow.build_review(
                    [str(pathlib.Path(tmpdir) / "research.json")],
                    "output/research/artifact-reviews/batch-review.md",
                    tmpdir,
                )

            self.assertTrue(report["success"])
            self.assertEqual(report["artifact_count"], 1)
            self.assertEqual(report["report_artifact"]["path"], "output/research/artifact-reviews/batch-review.md")
            self.assertGreater(report["markdown_chars"], 0)

    def test_run_workflows_reports_relative_paths_but_keeps_review_paths_internal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_research = FakeResearchTools(tmpdir)
            fake_server = types.SimpleNamespace(_get_tools=lambda: {"research": fake_research})
            args = argparse.Namespace(
                source=None,
                limit=1,
                timeout=20,
                max_chars_per_page=1500,
                images_per_page=5,
                retries=1,
                output_dir="output/research/batch",
            )

            with mock.patch.dict(sys.modules, {"argus_server.server": fake_server}):
                summary = research_batch_workflow.run_workflows(args, ["OpenAI"], tmpdir)

            self.assertEqual(summary["artifact_paths"], ["output/research/batch/research.json"])
            self.assertEqual(
                summary["_review_artifact_paths"],
                [str(pathlib.Path(tmpdir) / "output/research/batch/research.json")],
            )

    def test_run_batch_omits_internal_review_paths_from_printed_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            internal_path = str(pathlib.Path(tmpdir) / "output/research/batch/research.json")
            args = argparse.Namespace(
                query=["OpenAI"],
                queries_file=None,
                output_dir="output/research/batch",
                review_report="output/research/artifact-reviews/batch-review.md",
            )
            workflows = {
                "success": True,
                "status": "ran",
                "sources": ["wikipedia"],
                "runs": [{"success": True}],
                "artifact_paths": ["output/research/batch/research.json"],
                "_review_artifact_paths": [internal_path],
            }
            review = {
                "success": True,
                "status_counts": {"ready": 1},
                "report_artifact": {"success": True},
            }

            output = io.StringIO()
            with mock.patch.object(research_batch_workflow, "run_workflows", return_value=workflows):
                with mock.patch.object(research_batch_workflow, "build_review", return_value=review):
                    with contextlib.redirect_stdout(output):
                        exit_code = research_batch_workflow.run_batch(args)

            printed = output.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("output/research/batch/research.json", printed)
            self.assertNotIn("_review_artifact_paths", printed)
            self.assertNotIn(tmpdir, printed)

    def test_batch_passed_requires_successful_runs_review_and_report(self):
        summary = {
            "success": True,
            "workflows": {"status": "ran", "runs": [{"success": True}]},
            "review": {"success": True, "status_counts": {"ready": 1}, "report_artifact": {"success": True}},
        }

        self.assertTrue(research_batch_workflow.batch_passed(summary))

        summary["review"]["status_counts"] = {"unreadable": 1}
        self.assertFalse(research_batch_workflow.batch_passed(summary))

    def test_exit_code_reports_unavailable_workflow_import(self):
        self.assertEqual(
            research_batch_workflow.exit_code_for_summary({"passed": False, "workflows": {"status": "unavailable"}}),
            2,
        )
        self.assertEqual(
            research_batch_workflow.exit_code_for_summary({"passed": False, "workflows": {"status": "ran"}}),
            3,
        )
        self.assertEqual(
            research_batch_workflow.exit_code_for_summary({"passed": True, "workflows": {"status": "ran"}}),
            0,
        )


if __name__ == "__main__":
    unittest.main()
