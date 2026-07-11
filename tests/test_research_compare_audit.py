import json
import tempfile
import unittest
from pathlib import Path

from argus_server.tools.research_compare_audit import ResearchComparisonAuditTools
from argus_server.tools.research_integrity import build_content_fingerprint


class ResearchComparisonAuditToolsTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.project_root = Path(self.temporary_directory.name)
        self.source_texts = {
            "S1": "private alpha evidence for the first source",
            "S2": "private beta evidence for the second source",
        }
        self._write_source("source-one.json", self.source_texts["S1"])
        self._write_source("source-two.json", self.source_texts["S2"])
        self.comparison = {
            "sources": [
                self._comparison_source("S1", "Source One", "source-one.json"),
                self._comparison_source("S2", "Source Two", "source-two.json"),
            ],
            "comparison": {
                "agreements": [
                    {
                        "statement": "The sources agree.",
                        "citations": ["S1", "S2"],
                        "locators": ["S1:L1", "S2:L1"],
                    }
                ],
                "differences": [],
                "evidence": [
                    {
                        "statement": "The first source provides evidence.",
                        "citations": ["S1"],
                        "locators": ["S1:L1"],
                    }
                ],
            },
        }
        self._write_json("comparison.json", self.comparison)
        self.tools = ResearchComparisonAuditTools(str(self.project_root))

    def test_verifies_every_unique_used_locator_without_returning_text(self):
        result = self.tools.research_audit_comparison("comparison.json")

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["status"], "verified")
        self.assertEqual(result["data"]["claim_count"], 2)
        self.assertEqual(result["data"]["used_locator_count"], 2)
        self.assertEqual(result["data"]["verified_locator_count"], 2)
        self.assertEqual(result["data"]["issues"], [])
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("excerpt", serialized)
        self.assertNotIn("evidence_text", serialized)
        for source_text in self.source_texts.values():
            self.assertNotIn(source_text, serialized)

    def test_marks_legacy_comparison_without_fingerprints_unverified(self):
        comparison = self._copy_comparison()
        for source in comparison["sources"]:
            source.pop("content_fingerprint")
        self._write_json("legacy.json", comparison)

        result = self.tools.research_audit_comparison("legacy.json")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["status"], "unverified")
        self.assertEqual(result["data"]["unverified_locator_count"], 2)
        self.assertEqual(result["data"]["failed_locator_count"], 0)

    def test_reports_source_mutation_and_continues_other_sources(self):
        self._write_source("source-one.json", "X" + self.source_texts["S1"][1:])

        result = self.tools.research_audit_comparison("comparison.json")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["status"], "failed")
        self.assertEqual(result["data"]["verified_locator_count"], 1)
        self.assertEqual(result["data"]["failed_locator_count"], 1)
        self.assertEqual(result["data"]["issues"][0]["code"], "SOURCE_CONTENT_MISMATCH")
        self.assertEqual(result["data"]["issues"][0]["locator_id"], "S1:L1")

    def test_reports_stale_and_unknown_locator_references(self):
        comparison = self._copy_comparison()
        comparison["sources"][1]["locators"][0]["end_char"] += 1
        comparison["comparison"]["evidence"][0]["locators"].append("S9:L1")
        self._write_json("invalid-locators.json", comparison)

        result = self.tools.research_audit_comparison("invalid-locators.json")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["status"], "failed")
        self.assertEqual(result["data"]["used_locator_count"], 3)
        self.assertEqual(result["data"]["failed_locator_count"], 2)
        self.assertEqual(
            {issue["code"] for issue in result["data"]["issues"]},
            {"STALE_LOCATOR", "UNKNOWN_LOCATOR_REFERENCE"},
        )

    def test_reports_invalid_fingerprint_metadata(self):
        comparison = self._copy_comparison()
        comparison["sources"][0]["content_fingerprint"]["documents"][0][
            "document_index"
        ] = False
        self._write_json("invalid-fingerprint.json", comparison)

        result = self.tools.research_audit_comparison("invalid-fingerprint.json")

        self.assertTrue(result["success"])
        issue = result["data"]["issues"][0]
        self.assertEqual(issue["code"], "INVALID_CONTENT_FINGERPRINT")
        self.assertEqual(issue["reason"], "missing_or_duplicate_document")

    def test_reports_locator_outside_fingerprinted_prefix(self):
        comparison = self._copy_comparison()
        fingerprint_chars = 12
        comparison["sources"][0]["content_fingerprint"] = build_content_fingerprint(
            [(0, self.source_texts["S1"][:fingerprint_chars])]
        )
        comparison["sources"][0]["locators"][0]["start_char"] = fingerprint_chars + 1
        comparison["sources"][0]["locators"][0]["end_char"] = fingerprint_chars + 10
        self._write_json("outside-fingerprint.json", comparison)

        result = self.tools.research_audit_comparison("outside-fingerprint.json")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["status"], "failed")
        issue = result["data"]["issues"][0]
        self.assertEqual(issue["code"], "STALE_LOCATOR")
        self.assertEqual(issue["reason"], "outside_fingerprint_scope")

    def test_rejects_unsafe_comparison_and_reports_unsafe_source(self):
        outside_path = self.project_root.parent / "outside.json"
        unsafe_comparison = self.tools.research_audit_comparison(str(outside_path))
        self.assertFalse(unsafe_comparison["success"])
        self.assertEqual(
            unsafe_comparison["error"]["code"],
            "UNSAFE_COMPARISON_ARTIFACT_PATH",
        )

        comparison = self._copy_comparison()
        comparison["sources"][0]["artifact_path"] = str(outside_path)
        self._write_json("unsafe-source.json", comparison)
        unsafe_source = self.tools.research_audit_comparison("unsafe-source.json")

        self.assertTrue(unsafe_source["success"])
        self.assertEqual(unsafe_source["data"]["status"], "failed")
        self.assertEqual(
            unsafe_source["data"]["issues"][0]["code"],
            "UNSAFE_SOURCE_ARTIFACT_PATH",
        )
        self.assertNotIn(str(outside_path), json.dumps(unsafe_source))

    def test_rejects_comparison_without_used_locators(self):
        comparison = self._copy_comparison()
        for category in ("agreements", "differences", "evidence"):
            for claim in comparison["comparison"][category]:
                claim["locators"] = []
        self._write_json("no-locators.json", comparison)

        result = self.tools.research_audit_comparison("no-locators.json")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "NO_USED_LOCATORS")

    def _comparison_source(
        self,
        source_id: str,
        title: str,
        artifact_path: str,
    ) -> dict:
        text = self.source_texts[source_id]
        return {
            "source_id": source_id,
            "title": title,
            "artifact_path": artifact_path,
            "content_fingerprint": build_content_fingerprint([(0, text)]),
            "locators": [
                {
                    "locator_id": f"{source_id}:L1",
                    "document_index": 0,
                    "paragraph_index": 1,
                    "section": "Evidence",
                    "page": None,
                    "kind": "section",
                    "start_char": 0,
                    "end_char": len(text),
                }
            ],
        }

    def _copy_comparison(self) -> dict:
        return json.loads(json.dumps(self.comparison))

    def _write_source(self, path: str, text: str) -> None:
        self._write_json(path, {"documents": [{"success": True, "text": text}]})

    def _write_json(self, path: str, payload: dict) -> None:
        (self.project_root / path).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
