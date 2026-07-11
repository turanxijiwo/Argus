import json
import os
import tempfile
import unittest

from argus_server.tools.research_handoff import build_workflow_handoff
from argus_server.tools.research_io import resolve_output_dir, resolve_project_path
from argus_server.tools.research_review import review_research_artifact


class ResearchPathSafetyTest(unittest.TestCase):
    def test_resolve_project_path_keeps_normal_project_path(self):
        with tempfile.TemporaryDirectory() as project_root:
            expected = os.path.realpath(
                os.path.join(project_root, "output", "research")
            )

            resolved = resolve_project_path("output/research", project_root)

            self.assertEqual(resolved, expected)

    def test_output_dir_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as project_root, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, os.path.join(project_root, "linked"))

            result = resolve_output_dir(project_root, "linked/output")

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "UNSAFE_OUTPUT_DIR")

    def test_artifact_review_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as project_root, tempfile.TemporaryDirectory() as outside:
            artifact_path = os.path.join(outside, "artifact.json")
            with open(artifact_path, "w", encoding="utf-8") as handle:
                json.dump({"query": "outside", "documents": []}, handle)
            os.symlink(outside, os.path.join(project_root, "linked"))

            result = review_research_artifact("linked/artifact.json", project_root)

            self.assertFalse(result["success"])
            self.assertEqual(result["error"]["code"], "UNSAFE_ARTIFACT_PATH")

    def test_handoff_does_not_publish_symlink_escape(self):
        with tempfile.TemporaryDirectory() as project_root, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, os.path.join(project_root, "linked"))
            workflow = {
                "query": "outside",
                "documents": [{"success": True}],
                "source_errors": [],
                "images": [],
                "artifact": {"path": os.path.join(project_root, "linked", "artifact.json")},
                "brief": None,
            }

            handoff = build_workflow_handoff(workflow, project_root)

            self.assertFalse(handoff["ready"])
            self.assertIsNone(handoff["artifact_path"])


if __name__ == "__main__":
    unittest.main()
