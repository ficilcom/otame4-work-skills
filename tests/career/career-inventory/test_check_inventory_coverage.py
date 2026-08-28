import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/career/career-inventory/scripts/check_inventory_coverage.py"
SPEC = importlib.util.spec_from_file_location("check_inventory_coverage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def experience(**overrides):
    base = {
        "id": "e1",
        "title": "在庫管理システムの刷新",
        "timeline_label": "架空A社",
        "period": {"start": "2019-04", "end": "2022-03"},
        "kind": "improvement",
        "role": "owner",
        "situation": "欠品が慢性化していた",
        "actions": ["要件を定義した"],
        "outcome": "欠品が減った",
        "metrics": [{"text": "欠品率12%から4%", "evidence": "record"}],
        "evidence": "record",
    }
    base.update(overrides)
    return base


def payload(**overrides):
    base = {
        "track": "chuto",
        "as_of": "2026-08",
        "timeline": [{"label": "架空A社", "start": "2019-04", "end": "2022-03"}],
        "experiences": [experience()],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def described(report, experience_id):
    return next(entry for entry in report["experiences"] if entry["id"] == experience_id)


def coverage(report, label):
    return next(entry for entry in report["coverage"] if entry["label"] == label)


class CompletenessTest(unittest.TestCase):
    def test_a_fully_recorded_experience_has_nothing_missing(self):
        report = MODULE.analyze(payload())
        self.assertEqual(described(report, "e1")["missing_fields"], [])
        self.assertTrue(described(report, "e1")["complete"])

    def test_missing_narrative_fields_are_listed(self):
        entry = experience()
        del entry["outcome"]
        report = MODULE.analyze(payload(experiences=[entry]))
        self.assertEqual(described(report, "e1")["missing_fields"], ["outcome"])
        self.assertIn("experience_incomplete", codes(report))

    def test_unstated_role_is_reported_separately(self):
        report = MODULE.analyze(payload(experiences=[experience(role="unstated")]))
        self.assertIn("role", described(report, "e1")["missing_fields"])
        self.assertIn("role_unstated", codes(report))

    def test_team_role_is_recorded_as_given(self):
        report = MODULE.analyze(payload(experiences=[experience(role="team")]))
        self.assertEqual(described(report, "e1")["role"], "team")
        self.assertNotIn("role_unstated", codes(report))

    def test_experience_without_a_period_cannot_be_placed(self):
        entry = experience()
        del entry["period"]
        report = MODULE.analyze(payload(experiences=[entry]))
        self.assertIn("period", described(report, "e1")["missing_fields"])


class EvidenceTest(unittest.TestCase):
    def test_memory_and_unknown_are_not_merged(self):
        report = MODULE.analyze(
            payload(
                experiences=[
                    experience(id="e1", evidence="memory"),
                    experience(id="e2", evidence="unknown"),
                ]
            )
        )
        self.assertEqual(described(report, "e1")["evidence_strength"], "weak")
        self.assertEqual(described(report, "e2")["evidence_strength"], "unconfirmed")
        self.assertIn("evidence_from_memory_only", codes(report))
        self.assertIn("evidence_unconfirmed", codes(report))

    def test_metric_evidence_is_tracked_apart_from_the_experience(self):
        report = MODULE.analyze(
            payload(
                experiences=[
                    experience(metrics=[{"text": "欠品率12%から4%", "evidence": "memory"}])
                ]
            )
        )
        self.assertEqual(described(report, "e1")["evidence_strength"], "strong")
        self.assertTrue(described(report, "e1")["metrics_backed_by_memory_only"])
        self.assertIn("metrics_from_memory_only", codes(report))

    def test_a_single_recorded_metric_clears_the_memory_flag(self):
        report = MODULE.analyze(
            payload(
                experiences=[
                    experience(
                        metrics=[
                            {"text": "欠品率12%から4%", "evidence": "memory"},
                            {"text": "対象店舗40店", "evidence": "record"},
                        ]
                    )
                ]
            )
        )
        self.assertFalse(described(report, "e1")["metrics_backed_by_memory_only"])

    def test_absence_of_metrics_anywhere_is_reported(self):
        report = MODULE.analyze(payload(experiences=[experience(metrics=[])]))
        self.assertIn("no_metrics_captured", codes(report))


class CoverageTest(unittest.TestCase):
    def test_a_fully_covered_period_reports_no_gap(self):
        report = MODULE.analyze(payload())
        entry = coverage(report, "架空A社")
        self.assertEqual(entry["covered_months"], entry["total_months"])
        self.assertEqual(entry["longest_uncovered_stretch"], 0)
        self.assertNotIn("period_not_inventoried", codes(report))

    def test_uncovered_months_inside_a_period_are_counted(self):
        report = MODULE.analyze(
            payload(experiences=[experience(period={"start": "2019-04", "end": "2020-03"})])
        )
        entry = coverage(report, "架空A社")
        self.assertEqual(entry["covered_months"], 12)
        self.assertEqual(entry["longest_uncovered_stretch"], 24)
        self.assertIn("period_not_inventoried", codes(report))

    def test_an_open_period_needs_as_of_to_be_measured(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(
                {
                    "timeline": [{"label": "架空A社", "start": "2022-04", "end": None}],
                    "experiences": [],
                }
            )

    def test_experience_months_are_clipped_to_the_period(self):
        report = MODULE.analyze(
            payload(experiences=[experience(period={"start": "2018-01", "end": "2030-01"})])
        )
        entry = coverage(report, "架空A社")
        self.assertEqual(entry["covered_months"], entry["total_months"])

    def test_the_latest_employer_being_empty_is_flagged_for_mid_career(self):
        report = MODULE.analyze(
            payload(
                timeline=[
                    {"label": "架空A社", "start": "2019-04", "end": "2022-03"},
                    {"label": "架空B社", "start": "2022-04", "end": None},
                ]
            )
        )
        self.assertIn("recent_period_empty", codes(report))

    def test_unplaced_experience_is_flagged(self):
        entry = experience()
        del entry["timeline_label"]
        report = MODULE.analyze(payload(experiences=[entry]))
        self.assertIn("experience_not_placed", codes(report))


class DistributionTest(unittest.TestCase):
    def test_one_sided_kinds_are_flagged_once_there_are_enough_experiences(self):
        report = MODULE.analyze(
            payload(
                experiences=[
                    experience(id="e1"),
                    experience(id="e2"),
                    experience(id="e3"),
                ]
            )
        )
        self.assertIn("kind_concentration", codes(report))

    def test_two_experiences_are_too_few_to_call_a_concentration(self):
        report = MODULE.analyze(
            payload(experiences=[experience(id="e1"), experience(id="e2")])
        )
        self.assertNotIn("kind_concentration", codes(report))

    def test_mixed_kinds_are_not_flagged(self):
        report = MODULE.analyze(
            payload(
                experiences=[
                    experience(id="e1", kind="build"),
                    experience(id="e2", kind="people"),
                    experience(id="e3", kind="sales"),
                ]
            )
        )
        self.assertNotIn("kind_concentration", codes(report))


class OutputContractTest(unittest.TestCase):
    def test_confidential_experiences_are_flagged(self):
        report = MODULE.analyze(payload(experiences=[experience(confidential_risk=True)]))
        self.assertIn("confidential_content", codes(report))

    def test_an_empty_inventory_says_so_without_other_noise(self):
        report = MODULE.analyze(payload(experiences=[]))
        self.assertEqual(codes(report), {"experiences_not_captured"})

    def test_output_carries_no_judgement_of_the_person(self):
        serialized = json.dumps(MODULE.analyze(payload()), ensure_ascii=False)
        for forbidden in ("strength_of_candidate", "aptitude", "market_value", "score", "rating"):
            self.assertNotIn(forbidden, serialized)

    def test_notes_state_that_coverage_is_not_an_evaluation(self):
        report = MODULE.analyze(payload())
        self.assertTrue(any("評価" in note for note in report["notes"]))


class InputValidationTest(unittest.TestCase):
    def test_rejects_duplicate_experience_ids(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(experiences=[experience(), experience()]))

    def test_rejects_duplicate_timeline_labels(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(
                payload(
                    timeline=[
                        {"label": "架空A社", "start": "2019-04", "end": "2022-03"},
                        {"label": "架空A社", "start": "2022-04", "end": "2023-03"},
                    ]
                )
            )

    def test_rejects_an_experience_pointing_at_an_unknown_employer(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(experiences=[experience(timeline_label="架空Z社")]))

    def test_rejects_unknown_evidence_level(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(experiences=[experience(evidence="probably")]))

    def test_rejects_malformed_month(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(timeline=[{"label": "架空A社", "start": "2019/04"}]))

    def test_rejects_period_ending_before_it_starts(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(
                payload(experiences=[experience(period={"start": "2021-04", "end": "2020-04"})])
            )


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload(), ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["summary"]["complete"], 1)

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"track": "unknown"}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
