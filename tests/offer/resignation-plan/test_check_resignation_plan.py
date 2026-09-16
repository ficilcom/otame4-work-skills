import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/offer/resignation-plan/scripts/check_resignation_plan.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def plan(**overrides):
    base = {
        "as_of": "2026-09-01",
        "offer_accepted": True,
        "current": {
            "contract_type": "indefinite",
            "notice_rule_source": "employment_rules",
            "notice_days_required": 30,
        },
        "dates": {
            "intended_notice_date": "2026-09-05",
            "desired_last_day": "2026-10-31",
            "start_date_new": "2026-11-01",
            "paid_leave_days_remaining": 10,
        },
        "items": [],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def entry(report, code):
    return next(item for item in report["checklist"] if item["code"] == code)


class ScheduleTest(unittest.TestCase):
    def test_notice_period_is_measured_against_the_employer_rule(self):
        report = MODULE.check(plan())
        self.assertEqual(report["schedule"]["notice_to_last_day_days"], 56)
        self.assertNotIn("notice_period_short", codes(report))

    def test_short_notice_is_flagged_with_the_actual_days(self):
        report = MODULE.check(
            plan(
                dates={
                    "intended_notice_date": "2026-10-20",
                    "desired_last_day": "2026-10-31",
                    "start_date_new": "2026-11-01",
                }
            )
        )
        flag = next(f for f in report["flags"] if f["code"] == "notice_period_short")
        self.assertIn("11日", flag["message"])

    def test_unconfirmed_rule_is_reported_instead_of_a_default_period(self):
        report = MODULE.check(
            plan(current={"contract_type": "indefinite", "notice_rule_source": "unknown"})
        )
        self.assertIn("notice_rule_unconfirmed", codes(report))
        self.assertNotIn("notice_period_short", codes(report))
        self.assertIsNone(report["schedule"]["notice_days_required"])

    def test_consecutive_dates_leave_no_gap(self):
        report = MODULE.check(plan())
        self.assertEqual(report["schedule"]["days_between_jobs"], 0)
        self.assertNotIn("gap_between_jobs", codes(report))

    def test_a_gap_between_jobs_is_counted(self):
        report = MODULE.check(
            plan(
                dates={
                    "intended_notice_date": "2026-09-05",
                    "desired_last_day": "2026-10-31",
                    "start_date_new": "2026-11-16",
                }
            )
        )
        self.assertEqual(report["schedule"]["days_between_jobs"], 15)
        self.assertIn("gap_between_jobs", codes(report))

    def test_overlapping_employment_is_flagged(self):
        report = MODULE.check(
            plan(
                dates={
                    "intended_notice_date": "2026-09-05",
                    "desired_last_day": "2026-10-31",
                    "start_date_new": "2026-10-16",
                }
            )
        )
        self.assertIn("overlapping_employment", codes(report))

    def test_rejects_a_last_day_before_the_notice_date(self):
        with self.assertRaises(ValueError):
            MODULE.check(
                plan(
                    dates={
                        "intended_notice_date": "2026-10-31",
                        "desired_last_day": "2026-09-05",
                    }
                )
            )


class PaidLeaveTest(unittest.TestCase):
    def test_weekdays_exclude_weekends(self):
        report = MODULE.check(
            plan(
                dates={
                    "intended_notice_date": "2026-09-05",
                    "desired_last_day": "2026-09-19",
                    "paid_leave_days_remaining": 5,
                }
            )
        )
        self.assertEqual(report["schedule"]["weekdays_until_last_day"], 10)

    def test_leave_that_does_not_fit_is_flagged(self):
        report = MODULE.check(
            plan(
                dates={
                    "intended_notice_date": "2026-09-05",
                    "desired_last_day": "2026-09-19",
                    "paid_leave_days_remaining": 15,
                }
            )
        )
        self.assertFalse(report["schedule"]["paid_leave_fits_in_remaining_weekdays"])
        self.assertIn("paid_leave_may_not_fit", codes(report))

    def test_unknown_remaining_leave_is_reported(self):
        report = MODULE.check(
            plan(
                dates={
                    "intended_notice_date": "2026-09-05",
                    "desired_last_day": "2026-10-31",
                    "start_date_new": "2026-11-01",
                }
            )
        )
        self.assertIn("paid_leave_unknown", codes(report))


class OrderingTest(unittest.TestCase):
    def test_resigning_before_accepting_an_offer_is_flagged(self):
        report = MODULE.check(plan(offer_accepted=False))
        self.assertIn("offer_not_confirmed", codes(report))

    def test_unknown_acceptance_is_also_flagged(self):
        report = MODULE.check(plan(offer_accepted=None))
        self.assertIn("offer_not_confirmed", codes(report))

    def test_an_accepted_offer_clears_the_ordering_flag(self):
        report = MODULE.check(plan())
        self.assertNotIn("offer_not_confirmed", codes(report))


class ChecklistTest(unittest.TestCase):
    def test_unlisted_tasks_default_to_not_started(self):
        report = MODULE.check(plan())
        self.assertEqual(entry(report, "handover_plan")["status"], "none")
        self.assertIn("tasks_not_started", codes(report))

    def test_unlisted_documents_default_to_unknown(self):
        report = MODULE.check(plan())
        self.assertEqual(entry(report, "rishokuhyo")["status"], "unknown")
        self.assertIn("documents_unconfirmed", codes(report))

    def test_recorded_progress_is_counted(self):
        report = MODULE.check(
            plan(
                items=[
                    {"code": "confirm_rules", "status": "done"},
                    {"code": "rishokuhyo", "status": "confirmed"},
                    {"code": "health_insurance_card", "status": "confirmed"},
                ]
            )
        )
        self.assertEqual(report["summary"]["tasks_done"], 1)
        self.assertEqual(report["summary"]["documents_to_receive_confirmed"], 1)
        self.assertEqual(report["summary"]["items_to_return_confirmed"], 1)

    def test_task_and_document_statuses_are_not_interchangeable(self):
        with self.assertRaises(ValueError):
            MODULE.check(plan(items=[{"code": "confirm_rules", "status": "confirmed"}]))
        with self.assertRaises(ValueError):
            MODULE.check(plan(items=[{"code": "rishokuhyo", "status": "done"}]))

    def test_rejects_unknown_and_duplicate_codes(self):
        with self.assertRaises(ValueError):
            MODULE.check(plan(items=[{"code": "buy_cake", "status": "done"}]))
        with self.assertRaises(ValueError):
            MODULE.check(
                plan(
                    items=[
                        {"code": "confirm_rules", "status": "done"},
                        {"code": "confirm_rules", "status": "planned"},
                    ]
                )
            )


class ContractTest(unittest.TestCase):
    def test_fixed_term_contract_is_flagged(self):
        report = MODULE.check(
            plan(
                current={
                    "contract_type": "fixed_term",
                    "notice_rule_source": "contract",
                    "notice_days_required": 30,
                }
            )
        )
        self.assertIn("fixed_term_contract", codes(report))

    def test_unknown_contract_type_is_flagged(self):
        report = MODULE.check(
            plan(current={"contract_type": "unknown", "notice_rule_source": "unknown"})
        )
        self.assertIn("contract_type_unknown", codes(report))


class OutputContractTest(unittest.TestCase):
    def test_output_makes_no_legal_ruling(self):
        serialized = json.dumps(MODULE.check(plan()), ensure_ascii=False)
        for forbidden in ("lawful", "illegal", "violation", "guaranteed"):
            self.assertNotIn(forbidden, serialized)

    def test_notes_state_that_weekdays_exclude_holidays(self):
        report = MODULE.check(plan())
        self.assertTrue(any("祝日" in note for note in report["notes"]))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, plan())
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["summary"]["tasks_total"], 11)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, {"current": {"contract_type": "casual"}})
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
