import unittest

from argus_server.tools.research_compare_sources import (
    MAX_LOCATOR_CHARS,
    build_comparison_source,
    build_evidence_locators,
    public_comparison_source,
)


class ResearchComparisonSourceTest(unittest.TestCase):
    def test_paper_source_builds_doi_bibtex_and_traceable_locators(self):
        text = (
            "  \n\n"
            "# Example Paper\n\n"
            "## Abstract\n\n"
            "First paragraph explains the main contribution.\n\n"
            "Page 2\n\n"
            "Second paragraph reports the experiment."
        )
        payload = {
            "resource_type": "paper",
            "resource": {
                "resource_type": "paper",
                "title": "Models & Evidence",
                "creators": ["Ada Lovelace", "Grace Hopper"],
                "year": 2020,
                "identifiers": {
                    "doi": "https://doi.org/10.1000/example",
                    "arxiv": "https://arxiv.org/abs/2001.00001v2",
                },
            },
            "selection": {"url": "https://example.org/paper"},
            "documents": [{"success": True, "text": text}],
        }

        source_result = build_comparison_source(
            payload,
            "output/research/paper.json",
            "S1",
            8000,
        )

        self.assertTrue(source_result["success"])
        source = source_result["data"]
        self.assertEqual(source["authors"], ["Ada Lovelace", "Grace Hopper"])
        citation = source["citation"]
        self.assertEqual(citation["doi"], "10.1000/example")
        self.assertEqual(citation["doi_url"], "https://doi.org/10.1000/example")
        self.assertEqual(citation["arxiv_id"], "2001.00001v2")
        self.assertEqual(citation["entry_type"], "article")
        self.assertIn("author = {Ada Lovelace and Grace Hopper}", citation["bibtex"])
        self.assertIn("title = {Models \\& Evidence}", citation["bibtex"])
        self.assertEqual(citation["csl_json"]["type"], "article")
        self.assertEqual(
            citation["csl_json"]["author"],
            [
                {"family": "Lovelace", "given": "Ada"},
                {"family": "Hopper", "given": "Grace"},
            ],
        )
        self.assertEqual(citation["csl_json"]["issued"], {"date-parts": [[2020]]})
        self.assertEqual(citation["csl_json"]["DOI"], "10.1000/example")
        self.assertEqual(citation["csl_json"]["archive"], "arXiv")
        self.assertIn("TY  - JOUR", citation["ris"])
        self.assertIn("AU  - Ada Lovelace", citation["ris"])
        self.assertIn("DO  - 10.1000/example", citation["ris"])
        self.assertIn("AN  - 2001.00001v2", citation["ris"])
        self.assertTrue(citation["ris"].endswith("ER  -"))
        self.assertEqual(source["locators"][0]["section"], "Abstract")
        self.assertEqual(source["locators"][1]["page"], 2)
        for locator in source["locators"]:
            self.assertEqual(
                text[locator["start_char"]:locator["end_char"]],
                locator["text"],
            )

        public_source = public_comparison_source(source)
        self.assertNotIn("text", public_source)
        self.assertNotIn("text", public_source["locators"][0])
        self.assertEqual(public_source["locators"][0]["locator_id"], "S1:L1")

    def test_course_bibtex_uses_institution_without_inventing_year(self):
        payload = {
            "resource_type": "course",
            "resource": {
                "resource_type": "course",
                "title": "Introduction to Algorithms",
                "creators": [],
                "institution": "MIT",
                "identifiers": {},
            },
            "selection": {"url": "https://ocw.mit.edu/course"},
            "documents": [{"success": True, "text": "## Course Description\n\nAlgorithms course material."}],
        }

        source = build_comparison_source(payload, "course.json", "S2", 8000)["data"]

        citation = source["citation"]
        self.assertEqual(citation["entry_type"], "misc")
        self.assertEqual(citation["institution"], "MIT")
        self.assertNotIn("year", citation)
        self.assertIn("organization = {MIT}", citation["bibtex"])
        self.assertEqual(citation["csl_json"]["type"], "webpage")
        self.assertNotIn("issued", citation["csl_json"])
        self.assertIn("TY  - ELEC", citation["ris"])
        self.assertNotIn("PY  -", citation["ris"])

    def test_book_bibtex_uses_first_isbn(self):
        payload = {
            "resource_type": "book",
            "resource": {
                "resource_type": "book",
                "title": "Example Book",
                "creators": ["Jane Writer"],
                "year": 2018,
                "identifiers": {"isbn": ["9780000000001", "9780000000002"]},
            },
            "selection": {"url": "https://example.org/book"},
            "documents": [{"success": True, "text": "A readable book landing page."}],
        }

        citation = build_comparison_source(payload, "book.json", "S1", 8000)["data"]["citation"]

        self.assertEqual(citation["entry_type"], "book")
        self.assertEqual(citation["isbn"], "9780000000001")
        self.assertIn("isbn = {9780000000001}", citation["bibtex"])
        self.assertEqual(citation["csl_json"]["type"], "book")
        self.assertEqual(citation["csl_json"]["ISBN"], "9780000000001")
        self.assertIn("TY  - BOOK", citation["ris"])
        self.assertIn("SN  - 9780000000001", citation["ris"])

    def test_preprint_ris_does_not_invent_journal_publication(self):
        payload = {
            "resource_type": "paper",
            "resource": {
                "resource_type": "paper",
                "title": "Example Preprint",
                "creators": ["Research Author"],
                "year": 2024,
                "identifiers": {"arxiv": "2401.00001"},
            },
            "selection": {"url": "https://arxiv.org/abs/2401.00001"},
            "documents": [{"success": True, "text": "Preprint evidence."}],
        }

        citation = build_comparison_source(payload, "paper.json", "S1", 8000)["data"]["citation"]

        self.assertEqual(citation["csl_json"]["type"], "article")
        self.assertIn("TY  - GEN", citation["ris"])
        self.assertNotIn("TY  - JOUR", citation["ris"])
        self.assertNotIn("ID  -", citation["ris"])

    def test_long_paragraph_locators_preserve_bounded_character_ranges(self):
        text = "word " * 400

        locators = build_evidence_locators(text, "S1", document_index=0)

        self.assertGreater(len(locators), 1)
        for locator in locators:
            self.assertLessEqual(len(locator["text"]), MAX_LOCATOR_CHARS)
            self.assertEqual(
                text[locator["start_char"]:locator["end_char"]],
                locator["text"],
            )

    def test_total_page_count_is_not_treated_as_current_page(self):
        text = "Number of Pages: 15\n\nEvidence paragraph."

        locators = build_evidence_locators(text, "S1", document_index=0)

        self.assertTrue(locators)
        self.assertTrue(all(locator["page"] is None for locator in locators))


if __name__ == "__main__":
    unittest.main()
