import json
import tempfile
import unittest
from pathlib import Path

from argus_server.tools.research_locator import (
    MAX_EXCERPT_CHARS,
    MAX_EXCERPT_WORDS,
    MAX_LOCATOR_REQUESTS,
    ResearchLocatorTools,
)


class ResearchLocatorToolsTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.project_root = Path(self.temporary_directory.name)
        self.english_text = " ".join(f"word{index}" for index in range(40))
        self.cjk_text = "证据" * 200
        self._write_json(
            "source.json",
            {
                "documents": [
                    {"success": True, "text": self.english_text},
                    {"success": True, "text": self.cjk_text},
                ]
            },
        )
        self.comparison = {
            "sources": [
                {
                    "source_id": "S1",
                    "artifact_path": "source.json",
                    "title": "Example Source",
                    "citation": {
                        "bibtex": "@misc{example}",
                        "csl_json": {"id": "example", "type": "article"},
                        "ris": "TY  - GEN\nER  -",
                    },
                    "locators": [
                        {
                            "locator_id": "S1:L1",
                            "document_index": 0,
                            "paragraph_index": 1,
                            "section": "Introduction",
                            "page": None,
                            "kind": "section",
                            "start_char": 0,
                            "end_char": len(self.english_text),
                        },
                        {
                            "locator_id": "S1:L2",
                            "document_index": 1,
                            "paragraph_index": 1,
                            "section": None,
                            "page": 2,
                            "kind": "page",
                            "start_char": 0,
                            "end_char": len(self.cjk_text),
                        },
                    ],
                }
            ]
        }
        self._write_json("comparison.json", self.comparison)
        self.tools = ResearchLocatorTools(str(self.project_root))

    def test_resolves_evidence_with_word_limit_and_citation_metadata(self):
        result = self.tools.research_resolve_locators(
            "comparison.json",
            ["S1:L1"],
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["summary"]["locator_count"], 1)
        evidence = result["data"]["evidence"][0]
        self.assertEqual(evidence["artifact_path"], "source.json")
        self.assertEqual(evidence["excerpt_words"], MAX_EXCERPT_WORDS)
        self.assertLessEqual(evidence["excerpt_chars"], MAX_EXCERPT_CHARS)
        self.assertTrue(evidence["excerpt_truncated"])
        self.assertEqual(evidence["citation"]["csl_json"]["id"], "example")
        self.assertNotIn("word39", json.dumps(result))

    def test_resolves_cjk_evidence_with_requested_character_limit(self):
        result = self.tools.research_resolve_locators(
            "comparison.json",
            ["S1:L2"],
            max_chars=80,
        )

        self.assertTrue(result["success"])
        evidence = result["data"]["evidence"][0]
        self.assertEqual(evidence["excerpt_chars"], 80)
        self.assertEqual(evidence["excerpt_words"], 1)
        self.assertTrue(evidence["excerpt_truncated"])
        self.assertEqual(result["data"]["limits"]["max_excerpt_chars"], 80)

    def test_rejects_more_than_ten_locator_ids(self):
        result = self.tools.research_resolve_locators(
            "comparison.json",
            [f"S1:L{index}" for index in range(1, MAX_LOCATOR_REQUESTS + 2)],
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "TOO_MANY_LOCATORS")

    def test_rejects_unknown_locator(self):
        result = self.tools.research_resolve_locators("comparison.json", ["S1:L99"])

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "UNKNOWN_LOCATORS")
        self.assertEqual(result["error"]["locator_ids"], ["S1:L99"])

    def test_rejects_unsafe_comparison_and_source_paths(self):
        unsafe_comparison = self.tools.research_resolve_locators(
            str(self.project_root.parent / "outside.json"),
            ["S1:L1"],
        )
        self.assertEqual(
            unsafe_comparison["error"]["code"],
            "UNSAFE_COMPARISON_ARTIFACT_PATH",
        )

        comparison = json.loads(json.dumps(self.comparison))
        comparison["sources"][0]["artifact_path"] = str(
            self.project_root.parent / "outside.json"
        )
        self._write_json("unsafe-source.json", comparison)
        unsafe_source = self.tools.research_resolve_locators(
            "unsafe-source.json",
            ["S1:L1"],
        )
        self.assertEqual(
            unsafe_source["error"]["code"],
            "UNSAFE_SOURCE_ARTIFACT_PATH",
        )

    def test_rejects_stale_character_range(self):
        comparison = json.loads(json.dumps(self.comparison))
        comparison["sources"][0]["locators"][0]["end_char"] = len(self.english_text) + 1
        self._write_json("stale.json", comparison)

        result = self.tools.research_resolve_locators("stale.json", ["S1:L1"])

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "STALE_LOCATOR")
        self.assertEqual(result["error"]["reason"], "invalid_character_range")

    def test_rejects_non_string_source_artifact_path(self):
        comparison = json.loads(json.dumps(self.comparison))
        comparison["sources"][0]["artifact_path"] = ["source.json"]
        self._write_json("invalid-source-path.json", comparison)

        result = self.tools.research_resolve_locators(
            "invalid-source-path.json",
            ["S1:L1"],
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_COMPARISON_ARTIFACT")
        self.assertEqual(result["error"]["reason"], "invalid_source_artifact_path")

    def _write_json(self, path: str, payload: dict) -> None:
        (self.project_root / path).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
