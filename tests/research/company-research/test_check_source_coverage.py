import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/research/company-research/scripts/check_source_coverage.py"
SPEC = importlib.util.spec_from_file_location("check_source_coverage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

AS_OF = "2026-08-28"


def source(tier="primary_filing", **overrides):
    base = {
        "url": "https://example.com/doc",
        "tier": tier,
        "retrieved_on": AS_OF,
        "published_on": "2026-06-25",
    }
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


def claim(identifier="c1", topic="financials", sources=None, **overrides):
    base = {
        "id": identifier,
        "topic": topic,
        "statement": "架空の記述",
        "sources": [source()] if sources is None else sources,
    }
    base.update(overrides)
    return base


def payload(*claims, **overrides):
    base = {"company": "架空株式会社", "as_of": AS_OF, "claims": list(claims)}
    base.update(overrides)
    return base


class EvidenceTest(unittest.TestCase):
    def test_filing_and_official_are_confirmed(self):
        for tier in ("primary_filing", "company_official", "regulated_public"):
            report = MODULE.analyze(payload(claim(sources=[source(tier)])))
            self.assertEqual(report["claims"][0]["evidence"], "confirmed", tier)

    def test_journalism_and_user_provided_are_reported(self):
        report = MODULE.analyze(payload(claim(sources=[source("journalism")])))
        self.assertEqual(report["claims"][0]["evidence"], "reported")
        report = MODULE.analyze(payload(claim(sources=[source("user_provided", url=None)])))
        self.assertEqual(report["claims"][0]["evidence"], "reported")

    def test_review_sites_are_unverified(self):
        report = MODULE.analyze(payload(claim(sources=[source("unverified")])))
        self.assertEqual(report["claims"][0]["evidence"], "unverified")
        self.assertEqual(report["must_not_state_as_fact"], ["c1"])

    def test_no_source_is_unknown_not_confirmed(self):
        report = MODULE.analyze(payload(claim(sources=[])))
        self.assertEqual(report["claims"][0]["evidence"], "unknown")
        self.assertIn("c1", report["must_not_state_as_fact"])

    def test_strongest_source_wins(self):
        report = MODULE.analyze(
            payload(claim(sources=[source("unverified"), source("primary_filing")]))
        )
        self.assertEqual(report["claims"][0]["evidence"], "confirmed")


class FreshnessTest(unittest.TestCase):
    def test_old_journalism_is_stale(self):
        report = MODULE.analyze(
            payload(claim(sources=[source("journalism", published_on="2024-01-01")]))
        )
        self.assertTrue(report["claims"][0]["all_sources_stale"])
        self.assertEqual(report["stale_claim_ids"], ["c1"])

    def test_filings_tolerate_a_longer_window(self):
        report = MODULE.analyze(
            payload(claim(sources=[source("primary_filing", published_on="2025-06-25")]))
        )
        self.assertFalse(report["claims"][0]["all_sources_stale"])

    def test_missing_publication_date_is_not_treated_as_fresh(self):
        report = MODULE.analyze(payload(claim(sources=[source(published_on=None)])))
        self.assertEqual(report["claims"][0]["undated_source_count"], 1)
        self.assertIsNone(report["claims"][0]["sources"][0]["age_days"])
        self.assertFalse(report["claims"][0]["all_sources_stale"])

    def test_one_fresh_source_clears_staleness(self):
        report = MODULE.analyze(
            payload(
                claim(
                    sources=[
                        source("journalism", published_on="2024-01-01"),
                        source("journalism", published_on="2026-08-01"),
                    ]
                )
            )
        )
        self.assertFalse(report["claims"][0]["all_sources_stale"])


class CoverageTest(unittest.TestCase):
    def test_topics_without_confirmed_claims_are_gaps(self):
        report = MODULE.analyze(
            payload(
                claim("c1", "financials"),
                claim("c2", "risks", sources=[source("unverified")]),
            )
        )
        gaps = set(report["coverage_gaps"])
        self.assertNotIn("financials", gaps)
        self.assertIn("risks", gaps)
        self.assertIn("business_model", gaps)

    def test_weak_and_missing_are_distinguished(self):
        report = MODULE.analyze(payload(claim("c1", "risks", sources=[source("journalism")])))
        by_topic = {item["topic"]: item for item in report["topic_coverage"]}
        self.assertEqual(by_topic["risks"]["status"], "weak")
        self.assertEqual(by_topic["organization"]["status"], "missing")
        self.assertIsNone(by_topic["organization"]["best_evidence"])

    def test_custom_topics_replace_the_defaults(self):
        report = MODULE.analyze(payload(claim("c1", "custom"), topics=["custom"]))
        self.assertEqual(report["coverage_gaps"], [])
        self.assertEqual(len(report["topic_coverage"]), 1)


class ConflictTest(unittest.TestCase):
    def test_conflicts_mark_both_claims(self):
        report = MODULE.analyze(
            payload(claim("c1", conflicts_with=["c2"]), claim("c2", "risks"))
        )
        self.assertEqual(report["conflict_pairs"], [["c1", "c2"]])
        self.assertEqual(sorted(report["contested_claim_ids"]), ["c1", "c2"])

    def test_conflict_pairs_are_not_duplicated(self):
        report = MODULE.analyze(
            payload(
                claim("c1", conflicts_with=["c2"]),
                claim("c2", "risks", conflicts_with=["c1"]),
            )
        )
        self.assertEqual(report["conflict_pairs"], [["c1", "c2"]])

    def test_unknown_conflict_id_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim("c1", conflicts_with=["nope"])))

    def test_self_conflict_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim("c1", conflicts_with=["c1"])))


class ValidationTest(unittest.TestCase):
    def test_rejects_unknown_tier(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim(sources=[source("blog")])))

    def test_rejects_missing_url_for_web_sources(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim(sources=[source(url=None)])))

    def test_allows_missing_url_for_user_provided(self):
        report = MODULE.analyze(payload(claim(sources=[source("user_provided", url=None)])))
        self.assertIsNone(report["claims"][0]["sources"][0]["url"])

    def test_rejects_non_http_url(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim(sources=[source(url="ftp://example.com")])))

    def test_rejects_retrieval_after_as_of(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim(sources=[source(retrieved_on="2026-09-01")])))

    def test_rejects_publication_after_as_of(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim(sources=[source(published_on="2026-09-01")])))

    def test_rejects_bad_date_format(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim(sources=[source(retrieved_on="2026/08/28")])))

    def test_rejects_duplicate_ids(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim("c1"), claim("c1", "risks")))

    def test_rejects_unknown_topic(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claim("c1", "made_up_topic")))

    def test_rejects_empty_claims(self):
        with self.assertRaises(ValueError):
            MODULE.analyze({"company": "架空株式会社", "as_of": AS_OF, "claims": []})


class NotesTest(unittest.TestCase):
    def test_clean_input_produces_no_notes(self):
        report = MODULE.analyze(payload(claim()))
        self.assertEqual(report["notes"], [])

    def test_unverified_claims_add_a_note(self):
        report = MODULE.analyze(payload(claim(sources=[source("unverified")])))
        self.assertTrue(any("口コミ" in note for note in report["notes"]))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload(claim()), ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["claim_count"], 1)

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"company": "x", "as_of": AS_OF, "claims": []}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
