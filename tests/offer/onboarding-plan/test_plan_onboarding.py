import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/offer/onboarding-plan/scripts/plan_onboarding.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def expectation(**overrides):
    base = {
        "id": "x1",
        "topic": "在宅勤務",
        "content": "週3日在宅可",
        "source": "interview",
        "said_by": "配属先の課長",
        "measurable": True,
        "confirm_with": "manager",
    }
    base.update(overrides)
    return base


def payload(**overrides):
    base = {
        "employer": "架空システム株式会社",
        "as_of": "2026-10-15",
        "start_date": "2026-11-01",
        "written_terms": True,
        "probation": {
            "exists": True,
            "months": 3,
            "criteria_known": True,
            "conditions_same": {"pay": True, "employment_type": True, "work_style": True},
        },
        "expectations": [expectation()],
        "checkpoints": [
            {"label": "上長との初回面談", "date": "2026-11-02", "with": "manager", "topics": ["x1"]}
        ],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def flag(report, code):
    return next(entry for entry in report["flags"] if entry["code"] == code)


class DateTest(unittest.TestCase):
    def test_probation_end_is_computed_from_months(self):
        report = MODULE.plan(payload())
        self.assertEqual(report["dates"]["probation_end"], "2027-01-31")
        self.assertTrue(report["dates"]["probation_end_computed"])
        self.assertEqual(report["dates"]["days_to_start"], 17)

    def test_add_months_clamps_to_month_end(self):
        self.assertEqual(MODULE.add_months(date(2027, 1, 31), 1), date(2027, 2, 28))

    def test_explicit_end_date_wins(self):
        report = MODULE.plan(
            payload(probation={"exists": True, "months": 3, "end_date": "2027-02-15", "criteria_known": True})
        )
        self.assertEqual(report["dates"]["probation_end"], "2027-02-15")
        self.assertFalse(report["dates"]["probation_end_computed"])

    def test_probation_ending_before_start_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(probation={"exists": True, "end_date": "2026-10-01"}))


class ExpectationTest(unittest.TestCase):
    def test_verbal_promise_is_not_treated_as_confirmed(self):
        report = MODULE.plan(payload())
        self.assertEqual(flag(report, "verbal_only")["items"], ["x1"])
        self.assertFalse(report["expectations"][0]["in_writing"])

    def test_written_source_counts_as_in_writing(self):
        report = MODULE.plan(payload(expectations=[expectation(source="notice")]))
        self.assertNotIn("verbal_only", codes(report))

    def test_posting_is_not_in_writing(self):
        report = MODULE.plan(payload(expectations=[expectation(source="posting")]))
        self.assertIn("verbal_only", codes(report))

    def test_confirmed_verbal_promise_is_cleared(self):
        report = MODULE.plan(payload(expectations=[expectation(confirmed=True)]))
        self.assertNotIn("verbal_only", codes(report))

    def test_missing_measure_is_flagged_only_when_false(self):
        report = MODULE.plan(payload(expectations=[expectation(measurable=False)]))
        self.assertIn("no_agreed_measure", codes(report))
        omitted = MODULE.plan(payload(expectations=[expectation(measurable=None)]))
        self.assertNotIn("no_agreed_measure", codes(omitted))

    def test_conflicting_sources_are_reported(self):
        report = MODULE.plan(
            payload(
                expectations=[
                    expectation(),
                    expectation(id="x2", content="会社の定めによる", source="notice"),
                ],
                checkpoints=[],
            )
        )
        self.assertEqual(report["conflicts"][0]["topic"], "在宅勤務")
        self.assertEqual(flag(report, "expectation_conflict")["items"], ["在宅勤務"])

    def test_due_before_start_is_flagged(self):
        report = MODULE.plan(payload(expectations=[expectation(due="2026-10-25")]))
        self.assertIn("pre_start_work", codes(report))

    def test_pre_start_work_without_due_is_flagged(self):
        report = MODULE.plan(payload(expectations=[expectation(before_start=True)]))
        self.assertEqual(flag(report, "pre_start_work")["items"], ["x1"])

    def test_undecided_contact_is_flagged(self):
        report = MODULE.plan(payload(expectations=[expectation(confirm_with=None)]))
        self.assertIn("confirm_with_undecided", codes(report))


class ProbationTest(unittest.TestCase):
    def test_unknown_criteria_and_conditions_are_flagged(self):
        report = MODULE.plan(payload(probation={"exists": True, "months": 3}))
        self.assertIn("probation_criteria_unknown", codes(report))
        self.assertIn("probation_conditions_unknown", codes(report))

    def test_conditions_are_checked_one_by_one(self):
        report = MODULE.plan(
            payload(probation={"exists": True, "months": 3, "conditions_same": {"pay": True, "work_style": False}})
        )
        self.assertEqual(flag(report, "probation_conditions_unknown")["items"], ["employment_type"])
        self.assertEqual(flag(report, "probation_conditions_differ")["items"], ["work_style"])

    def test_unknown_condition_key_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(probation={"exists": True, "conditions_same": {"bonus": True}}))

    def test_unknown_existence_is_flagged(self):
        report = MODULE.plan(payload(probation=None))
        self.assertIn("probation_unknown", codes(report))

    def test_no_probation_has_no_probation_flags(self):
        report = MODULE.plan(payload(probation={"exists": False}))
        self.assertFalse(any(code.startswith("probation") for code in codes(report)))


class CheckpointTest(unittest.TestCase):
    def test_checkpoint_only_near_probation_end_is_flagged(self):
        report = MODULE.plan(
            payload(
                checkpoints=[
                    {"label": "試用期間の面談", "date": "2027-01-25", "with": "manager", "topics": ["x1"]}
                ]
            )
        )
        self.assertIn("no_checkpoint_before_probation_review", codes(report))

    def test_early_checkpoint_clears_the_probation_flag(self):
        report = MODULE.plan(payload())
        self.assertNotIn("no_checkpoint_before_probation_review", codes(report))

    def test_unscheduled_expectation_is_flagged(self):
        report = MODULE.plan(
            payload(expectations=[expectation(), expectation(id="x2", topic="最初の担当", content="10社の運用")])
        )
        self.assertEqual(flag(report, "not_scheduled")["items"], ["x2"])

    def test_suggestions_appear_only_without_checkpoints(self):
        report = MODULE.plan(payload(checkpoints=[]))
        self.assertIn("no_checkpoints", codes(report))
        labels = [item["label"] for item in report["suggested_checkpoints"]]
        self.assertEqual(len(labels), 3)
        dates = [item["date"] for item in report["suggested_checkpoints"]]
        # 2026-11-01 は日曜。初週は翌日の月曜、1か月後の 12-01 は火曜、
        # 試用期間の終わり 2027-01-31 の30日前 2027-01-01 は金曜。
        self.assertEqual(dates, ["2026-11-02", "2026-12-01", "2027-01-01"])
        self.assertEqual(MODULE.plan(payload())["suggested_checkpoints"], [])

    def test_unknown_topic_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(checkpoints=[{"label": "面談", "topics": ["x9"]}]))


class TaskTest(unittest.TestCase):
    def test_overdue_and_undated_tasks_are_flagged(self):
        report = MODULE.plan(
            payload(
                pre_start_tasks=[
                    {"label": "入社手続き書類の提出", "due": "2026-10-10", "status": "planned"},
                    {"label": "健康診断の受診", "status": "not_started"},
                    {"label": "口座の届出", "due": "2026-10-01", "status": "done"},
                ]
            )
        )
        self.assertEqual(flag(report, "pre_start_task_overdue")["items"], ["入社手続き書類の提出"])
        self.assertEqual(flag(report, "pre_start_task_undated")["items"], ["健康診断の受診"])


class CliTest(unittest.TestCase):
    def test_cli_succeeds_on_valid_input(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_cli_reports_bad_input_with_exit_code_two(self):
        completed = run_script(SCRIPT, {"start_date": "2026-11-01"})
        self.assertEqual(completed.returncode, 2)
        self.assertIn("employer", completed.stderr)


if __name__ == "__main__":
    unittest.main()
