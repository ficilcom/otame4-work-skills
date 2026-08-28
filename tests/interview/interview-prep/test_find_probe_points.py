import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/interview/interview-prep/scripts/find_probe_points.py"
SPEC = importlib.util.spec_from_file_location("find_probe_points", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def claim(**overrides):
    base = {
        "id": "c1",
        "topic": "在庫管理システムの刷新",
        "source": "shokumu",
        "role_stated": "owner",
        "metrics": ["欠品率を12%から4%へ"],
        "claims_outcome": True,
        "verifiable_by_user": True,
        "repeatable_stated": True,
    }
    base.update(overrides)
    return base


def payload(**overrides):
    base = {
        "role": "Webアプリケーションエンジニア",
        "track": "chuto",
        "stage": "first",
        "claims": [claim()],
        "timeline": [{"label": "架空A社", "start": "2019-04", "end": None}],
        "requirements": [
            {"text": "開発経験3年以上", "kind": "must", "covered_by": ["c1"]},
        ],
        "prepared": [{"topic": "self_introduction", "status": "drafted"}],
        "questions_to_ask": ["評価はどの単位で決まるか"],
    }
    base.update(overrides)
    return base


def probe_codes(report):
    return [probe["code"] for probe in report["probe_points"]]


def codes(report):
    return {flag["code"] for flag in report["flags"]}


class ClaimProbeTest(unittest.TestCase):
    def test_a_well_supported_claim_raises_nothing(self):
        report = MODULE.analyze(payload())
        self.assertEqual(probe_codes(report), [])

    def test_team_wording_is_probed_for_scope(self):
        report = MODULE.analyze(payload(claims=[claim(role_stated="team")]))
        self.assertIn("role_unclear", probe_codes(report))

    def test_member_wording_is_left_alone(self):
        report = MODULE.analyze(payload(claims=[claim(role_stated="member")]))
        self.assertNotIn("role_unclear", probe_codes(report))

    def test_outcome_without_metrics_is_probed(self):
        report = MODULE.analyze(payload(claims=[claim(metrics=[])]))
        self.assertIn("unquantified_outcome", probe_codes(report))

    def test_unsupported_claim_is_high_priority_and_flagged(self):
        report = MODULE.analyze(payload(claims=[claim(verifiable_by_user=False)]))
        probe = next(p for p in report["probe_points"] if p["code"] == "unverifiable_claim")
        self.assertEqual(probe["priority"], "high")
        self.assertIn("unverifiable_claims_in_documents", codes(report))

    def test_unchecked_support_is_probed_but_reported_separately(self):
        entry = claim()
        del entry["verifiable_by_user"]
        report = MODULE.analyze(payload(claims=[entry]))
        self.assertIn("unverifiable_claim", probe_codes(report))
        self.assertIn("claim_support_unconfirmed", codes(report))
        self.assertNotIn("unverifiable_claims_in_documents", codes(report))

    def test_confidential_claim_is_probed(self):
        report = MODULE.analyze(payload(claims=[claim(confidential_risk=True)]))
        self.assertIn("confidential_content", probe_codes(report))

    def test_repeatability_is_probed_for_mid_career_only(self):
        report = MODULE.analyze(payload(claims=[claim(repeatable_stated=False)]))
        self.assertIn("repeatability_unstated", probe_codes(report))
        fresh = MODULE.analyze(payload(track="shinsotsu", claims=[claim(repeatable_stated=False)]))
        self.assertNotIn("repeatability_unstated", probe_codes(fresh))


class TimelineTest(unittest.TestCase):
    def test_continuous_history_raises_nothing(self):
        report = MODULE.analyze(
            payload(
                timeline=[
                    {"label": "架空A社", "start": "2019-04", "end": "2022-03"},
                    {"label": "架空B社", "start": "2022-04", "end": None},
                ]
            )
        )
        self.assertEqual(probe_codes(report), [])

    def test_gap_is_counted_in_empty_months(self):
        report = MODULE.analyze(
            payload(
                timeline=[
                    {"label": "架空A社", "start": "2019-04", "end": "2022-03"},
                    {"label": "架空B社", "start": "2022-10", "end": None},
                ]
            )
        )
        probe = next(p for p in report["probe_points"] if p["code"] == "employment_gap")
        self.assertIn("6か月", probe["prepare"])

    def test_short_gap_is_not_probed(self):
        report = MODULE.analyze(
            payload(
                timeline=[
                    {"label": "架空A社", "start": "2019-04", "end": "2022-03"},
                    {"label": "架空B社", "start": "2022-06", "end": None},
                ]
            )
        )
        self.assertNotIn("employment_gap", probe_codes(report))

    def test_overlapping_history_is_probed(self):
        report = MODULE.analyze(
            payload(
                timeline=[
                    {"label": "架空A社", "start": "2019-04", "end": "2022-06"},
                    {"label": "架空B社", "start": "2022-03", "end": None},
                ]
            )
        )
        self.assertIn("overlapping_employment", probe_codes(report))

    def test_short_tenure_is_probed(self):
        report = MODULE.analyze(
            payload(
                timeline=[
                    {"label": "架空A社", "start": "2022-04", "end": "2022-11"},
                    {"label": "架空B社", "start": "2022-12", "end": None},
                ]
            )
        )
        self.assertIn("short_tenure", probe_codes(report))

    def test_current_employment_needs_no_end_date(self):
        report = MODULE.analyze(payload())
        self.assertNotIn("short_tenure", probe_codes(report))


class RequirementTest(unittest.TestCase):
    def test_uncovered_must_requirement_is_probed(self):
        report = MODULE.analyze(
            payload(
                requirements=[
                    {"text": "SQLの実務経験", "kind": "must", "covered_by": []},
                ]
            )
        )
        self.assertIn("uncovered_must_requirement", probe_codes(report))
        self.assertEqual(report["summary"]["uncovered_must_requirements"], 1)

    def test_uncovered_preferred_requirement_is_not_probed(self):
        report = MODULE.analyze(
            payload(requirements=[{"text": "チームリード経験", "kind": "want", "covered_by": []}])
        )
        self.assertNotIn("uncovered_must_requirement", probe_codes(report))


class PreparationTest(unittest.TestCase):
    def test_track_selects_the_topic_list(self):
        chuto = {entry["topic"] for entry in MODULE.analyze(payload())["preparation"]}
        shinsotsu = {
            entry["topic"] for entry in MODULE.analyze(payload(track="shinsotsu"))["preparation"]
        }
        self.assertIn("career_change_reason", chuto)
        self.assertNotIn("career_change_reason", shinsotsu)
        self.assertIn("student_experience", shinsotsu)

    def test_unprepared_topics_are_flagged(self):
        report = MODULE.analyze(payload())
        self.assertIn("topics_not_prepared", codes(report))

    def test_missing_reverse_questions_are_flagged(self):
        report = MODULE.analyze(payload(questions_to_ask=[]))
        self.assertIn("no_questions_to_ask", codes(report))


class OutputContractTest(unittest.TestCase):
    def test_probes_are_ordered_by_preparation_priority(self):
        report = MODULE.analyze(
            payload(claims=[claim(role_stated="team", metrics=[], verifiable_by_user=False)])
        )
        priorities = [probe["priority"] for probe in report["probe_points"]]
        self.assertEqual(priorities, sorted(priorities, key=["high", "medium", "low"].index))

    def test_output_makes_no_outcome_prediction(self):
        serialized = json.dumps(MODULE.analyze(payload()), ensure_ascii=False)
        for forbidden in ("score", "pass_rate", "likelihood", "recommend"):
            self.assertNotIn(forbidden, serialized)

    def test_notes_state_that_priority_is_not_an_evaluation(self):
        report = MODULE.analyze(payload())
        self.assertTrue(any("評価" in note for note in report["notes"]))


class InputValidationTest(unittest.TestCase):
    def test_rejects_duplicate_claim_ids(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(claims=[claim(), claim()]))

    def test_rejects_coverage_pointing_at_an_unknown_claim(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(
                payload(requirements=[{"text": "SQL", "kind": "must", "covered_by": ["c9"]}])
            )

    def test_rejects_malformed_month(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(timeline=[{"label": "架空A社", "start": "2019/04"}]))

    def test_rejects_end_before_start(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(
                payload(timeline=[{"label": "架空A社", "start": "2022-04", "end": "2021-04"}])
            )

    def test_rejects_unknown_track(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(track="part_time"))

    def test_rejects_unknown_prepared_topic(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(prepared=[{"topic": "hobbies", "status": "drafted"}]))


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
        self.assertEqual(json.loads(completed.stdout)["summary"]["probe_points"], 0)

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"role": ""}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
