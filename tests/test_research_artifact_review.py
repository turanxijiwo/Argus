import importlib.util
import json
import pathlib
import tempfile
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "research_artifact_review.py"
SPEC = importlib.util.spec_from_file_location("research_artifact_review", SCRIPT_PATH)
research_artifact_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_artifact_review)


def write_artifact(tmpdir, name="research-openai.json", payload=None):
    artifact_path = pathlib.Path(tmpdir) / name
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload or ready_payload(str(artifact_path))), encoding="utf-8")
    return artifact_path


def ready_payload(path):
    return {
        "query": "OpenAI",
        "sources": {"wikipedia": {"success": True}},
        "source_errors": [],
        "artifact": {"format": "json", "path": path},
        "brief": {
            "content": "# Research Brief: OpenAI\n\n" + ("useful brief " * 30),
            "artifact": {"format": "markdown", "path": path.replace(".json", ".md")},
        },
        "documents": [
            {
                "success": True,
                "source": "wikipedia",
                "url": "https://example.com/openai",
                "final_url": "https://example.com/openai",
                "page_title": "OpenAI",
                "status_code": 200,
                "text": "Evidence text. " * 80,
                "links": [{"url": "https://example.com/next"}],
                "images": [{"url": "https://example.com/image.png"}],
            }
        ],
        "images": [{"image_url": "https://example.com/image.png"}],
    }


class ResearchArtifactReviewTest(unittest.TestCase):
    def test_review_artifact_scores_ready_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_artifact(tmpdir)

            review = research_artifact_review.review_artifact(str(path), tmpdir)

            self.assertTrue(review["success"])
            self.assertEqual(review["quality_status"], "ready")
            self.assertEqual(review["score"], 100)
            self.assertEqual(review["warnings"], [])
            self.assertEqual(review["counts"]["successful_documents"], 1)
            self.assertEqual(review["key_documents"][0]["title"], "OpenAI")

    def test_review_artifact_reports_partial_quality_warnings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "research-partial.json"
            payload = ready_payload(str(path))
            payload["brief"]["content"] = "short"
            payload["documents"][0]["text"] = "tiny"
            payload["documents"].append(
                {
                    "success": False,
                    "title": "Failed page",
                    "url": "https://example.com/fail",
                    "error": {"code": "NETWORK_ERROR", "message": "Request failed"},
                }
            )
            payload["source_errors"] = [{"source": "wikipedia", "code": "NETWORK_ERROR", "message": "Down"}]
            write_artifact(tmpdir, "research-partial.json", payload)

            review = research_artifact_review.review_artifact(str(path), tmpdir)

            self.assertEqual(review["quality_status"], "partial")
            self.assertIn("short_brief", review["warnings"])
            self.assertIn("low_evidence_text", review["warnings"])
            self.assertIn("source_errors_present", review["warnings"])
            self.assertEqual(review["page_errors"][0]["code"], "NETWORK_ERROR")

    def test_review_artifact_reports_unreadable_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "broken.json"
            path.write_text("{not json", encoding="utf-8")

            review = research_artifact_review.review_artifact(str(path), tmpdir)

            self.assertFalse(review["success"])
            self.assertEqual(review["quality_status"], "unreadable")
            self.assertIn("json_unreadable", review["warnings"])

    def test_review_collection_counts_statuses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ready_path = write_artifact(tmpdir, "ready.json")
            broken_path = pathlib.Path(tmpdir) / "broken.json"
            broken_path.write_text("{not json", encoding="utf-8")

            report = research_artifact_review.review_collection([str(ready_path), str(broken_path)], tmpdir)

            self.assertTrue(report["success"])
            self.assertEqual(report["artifact_count"], 2)
            self.assertEqual(report["status_counts"]["ready"], 1)
            self.assertEqual(report["status_counts"]["unreadable"], 1)

    def test_render_markdown_report_includes_warnings_and_key_documents(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_artifact(tmpdir)
            report = research_artifact_review.review_collection([str(path)], tmpdir)

            markdown = research_artifact_review.render_markdown_report(report)

            self.assertIn("# Research Artifact Review", markdown)
            self.assertIn("Status: `ready`", markdown)
            self.assertIn("Key documents:", markdown)
            self.assertIn("[OpenAI](https://example.com/openai)", markdown)

    def test_find_artifacts_limits_latest_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            older = write_artifact(tmpdir, "older.json")
            newer = write_artifact(tmpdir, "nested/newer.json")
            newer.touch()

            found = research_artifact_review.find_artifacts(None, tmpdir, latest=1)

            self.assertEqual(found, [str(newer)])
            self.assertNotIn(str(older), found)

    def test_write_report_rejects_paths_outside_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = research_artifact_review.write_report("report", "/tmp/outside-review.md", tmpdir)

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "UNSAFE_OUTPUT_PATH")

    def test_exit_code_distinguishes_unreadable_artifacts(self):
        self.assertEqual(research_artifact_review.exit_code_for_report({"success": False}), 2)
        self.assertEqual(
            research_artifact_review.exit_code_for_report({"success": True, "status_counts": {"unreadable": 1}}),
            3,
        )
        self.assertEqual(
            research_artifact_review.exit_code_for_report({"success": True, "status_counts": {"ready": 1}}),
            0,
        )


if __name__ == "__main__":
    unittest.main()
