import copy
import unittest

from argus_server.tools.research_compare_contract import (
    build_comparison_prompt,
    normalize_comparison_payload,
)


SOURCES = [
    {
        "source_id": "S1",
        "title": "Source One",
        "url": "https://example.com/one",
        "authors": ["Author One"],
        "citation": {"bibtex": "@misc{s1}"},
        "summary": "Summary one",
        "text": "FLAT_PRIVATE_TEXT_ONE",
        "locators": [
            {
                "locator_id": "S1:L1",
                "document_index": 0,
                "paragraph_index": 1,
                "section": "Introduction",
                "page": None,
                "text": "Located evidence one.",
            }
        ],
    },
    {
        "source_id": "S2",
        "title": "Source Two",
        "url": "https://example.com/two",
        "authors": ["Author Two"],
        "citation": {"bibtex": "@misc{s2}"},
        "summary": "Summary two",
        "text": "FLAT_PRIVATE_TEXT_TWO",
        "locators": [
            {
                "locator_id": "S2:L1",
                "document_index": 0,
                "paragraph_index": 1,
                "section": "Overview",
                "page": 2,
                "text": "Located evidence two.",
            }
        ],
    },
]

VALID_PAYLOAD = {
    "title": "Comparison",
    "overview": "A traceable comparison.",
    "agreements": [
        {
            "statement": "Both sources provide evidence.",
            "citations": ["S1", "S2"],
            "locators": ["S1:L1", "S2:L1"],
        }
    ],
    "differences": [],
    "evidence": [
        {
            "statement": "The first source has one located claim.",
            "citations": ["S1"],
            "locators": ["S1:L1"],
        }
    ],
    "open_questions": [],
}

LOCATOR_SOURCES = {"S1:L1": "S1", "S2:L1": "S2"}


class ResearchComparisonLocatorTest(unittest.TestCase):
    def test_prompt_uses_evidence_units_instead_of_flat_source_text(self):
        prompt = build_comparison_prompt(
            SOURCES,
            focus="Compare",
            target_language="en",
            max_claims=3,
        )

        self.assertIn('"evidence_units"', prompt)
        self.assertIn("Located evidence one.", prompt)
        self.assertNotIn("FLAT_PRIVATE_TEXT_ONE", prompt)
        self.assertIn("Every claim must include supplied locator IDs", prompt)

    def test_normalizes_valid_source_and_locator_citations(self):
        result = normalize_comparison_payload(
            VALID_PAYLOAD,
            locator_sources=LOCATOR_SOURCES,
            max_claims=3,
            focus="Compare",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["locator_count"], 3)
        self.assertEqual(
            result["data"]["citation_validation"]["mode"],
            "source_and_locator_structure",
        )

    def test_rejects_unknown_locator(self):
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["evidence"][0]["locators"] = ["S1:L99"]

        result = normalize_comparison_payload(
            payload,
            locator_sources=LOCATOR_SOURCES,
            max_claims=3,
            focus="Compare",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_EVIDENCE_LOCATORS")
        self.assertTrue(
            any(issue["reason"] == "unknown_locators" for issue in result["error"]["issues"])
        )

    def test_rejects_locator_from_uncited_source(self):
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["evidence"][0]["locators"] = ["S2:L1"]

        result = normalize_comparison_payload(
            payload,
            locator_sources=LOCATOR_SOURCES,
            max_claims=3,
            focus="Compare",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_EVIDENCE_LOCATORS")
        self.assertTrue(
            any(
                issue["reason"] == "locator_source_mismatch"
                for issue in result["error"]["issues"]
            )
        )

    def test_rejects_cross_source_claim_with_one_source_locator(self):
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["agreements"][0]["locators"] = ["S1:L1"]

        result = normalize_comparison_payload(
            payload,
            locator_sources=LOCATOR_SOURCES,
            max_claims=3,
            focus="Compare",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["code"], "INVALID_EVIDENCE_LOCATORS")
        self.assertTrue(
            any(
                issue["reason"] == "missing_locator_sources"
                for issue in result["error"]["issues"]
            )
        )


if __name__ == "__main__":
    unittest.main()
