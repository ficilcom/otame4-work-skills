import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/offer/offer-negotiation/scripts/plan_negotiation.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def pay_request(**overrides):
    base = {
        "id": "base",
        "topic": "月額基本給",
        "category": "pay",
        "priority": "must",
        "current_text": "基本給 月額280,000円",
        "ask_text": "基本給 月額310,000円",
        "current_amount": 280000,
        "ask_amount": 310000,
        "amount_unit": "monthly",
        "if_declined": "accept_anyway",
        "bases": [{"kind": "own_record", "note": "現職の基本給（給与明細）"}],
    }
    base.update(overrides)
    return base


def payload(**overrides):
    base = {
        "employer": "架空システム株式会社",
        "as_of": "2026-09-08",
        "written_terms": True,
        "channel": "direct",
        "offer": {"acceptance_deadline": "2026-09-15"},
        "plan": {"request_date": "2026-09-09", "response_wait_days": 3},
        "requests": [pay_request()],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def flag(report, code):
    return next(entry for entry in report["flags"] if entry["code"] == code)


class AmountTest(unittest.TestCase):
    def test_monthly_difference_is_annualized_by_twelve(self):
        report = MODULE.plan(payload())
        amount = report["requests"][0]["amount"]
        self.assertEqual(amount["difference"], 30000)
        self.assertEqual(amount["annual_difference"], 360000)
        self.assertEqual(amount["difference_percent"], 10.7)
        self.assertEqual(report["summary"]["pay_annual_difference_total"], 360000)

    def test_annual_amount_is_not_multiplied(self):
        report = MODULE.plan(
            payload(requests=[pay_request(current_amount=5000000, ask_amount=5500000, amount_unit="annual")])
        )
        self.assertEqual(report["requests"][0]["amount"]["annual_difference"], 500000)

    def test_ask_above_posted_range_is_reported_as_fact(self):
        report = MODULE.plan(
            payload(requests=[pay_request(posted_range={"min": 260000, "max": 300000, "unit": "monthly"})])
        )
        self.assertEqual(report["requests"][0]["amount"]["posted_range_position"], "above_max")
        self.assertIn("ask_above_posted_range", codes(report))

    def test_ask_within_range_is_not_flagged(self):
        report = MODULE.plan(
            payload(requests=[pay_request(posted_range={"min": 260000, "max": 340000})])
        )
        self.assertEqual(report["requests"][0]["amount"]["posted_range_position"], "within")
        self.assertNotIn("ask_above_posted_range", codes(report))

    def test_range_in_other_unit_is_not_compared(self):
        report = MODULE.plan(
            payload(requests=[pay_request(posted_range={"min": 4000000, "max": 4500000, "unit": "annual"})])
        )
        self.assertEqual(report["requests"][0]["amount"]["posted_range_position"], "unit_mismatch")
        self.assertIn("posted_range_unit_mismatch", codes(report))
        self.assertNotIn("ask_above_posted_range", codes(report))

    def test_pay_request_without_numbers_cannot_be_measured(self):
        report = MODULE.plan(payload(requests=[pay_request(current_amount=None)]))
        self.assertIn("pay_amount_incomplete", codes(report))
        self.assertIsNone(report["summary"]["pay_annual_difference_total"])

    def test_start_date_shift_is_counted_in_days(self):
        report = MODULE.plan(
            payload(
                requests=[
                    {
                        "id": "start",
                        "topic": "入社日",
                        "category": "start_date",
                        "priority": "want",
                        "ask_text": "12月1日入社",
                        "current_date": "2026-11-01",
                        "ask_date": "2026-12-01",
                        "bases": [{"kind": "own_record"}],
                    }
                ]
            )
        )
        self.assertEqual(report["requests"][0]["date_shift_days"], 30)


class BasisTest(unittest.TestCase):
    def test_request_without_basis_is_flagged(self):
        report = MODULE.plan(payload(requests=[pay_request(bases=[])]))
        self.assertEqual(flag(report, "request_without_basis")["items"], ["base"])

    def test_interview_only_basis_is_flagged(self):
        report = MODULE.plan(payload(requests=[pay_request(bases=[{"kind": "interview"}])]))
        self.assertIn("basis_is_verbal_only", codes(report))

    def test_interview_with_record_is_not_verbal_only(self):
        report = MODULE.plan(
            payload(requests=[pay_request(bases=[{"kind": "interview"}, {"kind": "written_offer"}])])
        )
        self.assertNotIn("basis_is_verbal_only", codes(report))

    def test_other_offer_is_left_to_the_user(self):
        report = MODULE.plan(payload(requests=[pay_request(bases=[{"kind": "other_offer"}])]))
        self.assertIn("discloses_other_offer", codes(report))

    def test_public_source_needs_a_date(self):
        report = MODULE.plan(payload(requests=[pay_request(bases=[{"kind": "public_source"}])]))
        self.assertIn("public_source_undated", codes(report))
        dated = MODULE.plan(
            payload(requests=[pay_request(bases=[{"kind": "public_source", "as_of": "2026-06-30"}])])
        )
        self.assertNotIn("public_source_undated", codes(dated))


class DecisionTest(unittest.TestCase):
    def test_must_without_decision_is_left_undecided(self):
        report = MODULE.plan(payload(requests=[pay_request(if_declined=None)]))
        self.assertEqual(report["requests"][0]["if_declined"], "undecided")
        self.assertIn("must_without_decision", codes(report))

    def test_flat_priorities_are_flagged(self):
        second = pay_request(id="allowance", topic="住宅手当")
        report = MODULE.plan(payload(requests=[pay_request(), second]))
        self.assertIn("priority_flat", codes(report))

    def test_missing_priority_is_flagged_not_guessed(self):
        second = pay_request(id="allowance", topic="住宅手当", priority=None)
        report = MODULE.plan(payload(requests=[pay_request(), second]))
        self.assertEqual(flag(report, "priority_unset")["items"], ["allowance"])

    def test_no_written_terms_comes_first(self):
        report = MODULE.plan(payload(written_terms=False))
        self.assertEqual(report["flags"][0]["code"], "no_written_terms")


class ScheduleTest(unittest.TestCase):
    def test_answer_within_deadline(self):
        report = MODULE.plan(payload())
        self.assertEqual(report["schedule"]["expected_answer_by"], "2026-09-12")
        self.assertTrue(report["schedule"]["answer_before_deadline"])
        self.assertEqual(report["schedule"]["days_to_deadline"], 7)

    def test_answer_after_deadline_is_flagged(self):
        report = MODULE.plan(payload(plan={"request_date": "2026-09-12", "response_wait_days": 5}))
        self.assertFalse(report["schedule"]["answer_before_deadline"])
        self.assertIn("answer_after_deadline", codes(report))

    def test_little_time_after_answer_is_flagged(self):
        report = MODULE.plan(payload(plan={"request_date": "2026-09-11", "response_wait_days": 3}))
        self.assertIn("little_time_after_answer", codes(report))

    def test_unknown_wait_is_not_filled_with_a_default(self):
        report = MODULE.plan(payload(plan={"request_date": "2026-09-09"}))
        self.assertIsNone(report["schedule"]["answer_before_deadline"])
        self.assertNotIn("answer_after_deadline", codes(report))

    def test_request_after_deadline_is_flagged(self):
        report = MODULE.plan(payload(plan={"request_date": "2026-09-16", "response_wait_days": 1}))
        self.assertIn("request_after_deadline", codes(report))

    def test_passed_deadline_is_flagged(self):
        report = MODULE.plan(payload(as_of="2026-09-20"))
        self.assertIn("deadline_passed", codes(report))


class InputTest(unittest.TestCase):
    def test_requests_are_required(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(requests=[]))

    def test_duplicate_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(requests=[pay_request(), pay_request()]))

    def test_basis_kind_is_required(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(requests=[pay_request(bases=[{"note": "x"}])]))

    def test_inverted_range_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(requests=[pay_request(posted_range={"min": 300000, "max": 200000})]))

    def test_cli_reports_bad_input_with_exit_code_two(self):
        completed = run_script(SCRIPT, {"employer": "架空システム株式会社"})
        self.assertEqual(completed.returncode, 2)
        self.assertIn("requests", completed.stderr)

    def test_cli_succeeds_on_valid_input(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
