import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/sidework/sidework-terms-check/scripts/check_sidework_terms.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def payload(**overrides):
    base = {
        "as_of": "2026-09-20",
        "engagement": "contract_work",
        "offer": {"form": "email", "received_date": "2026-09-18"},
        "items": [],
        "work": [
            {"label": "資料の読み込み", "hours": 4, "paid": False},
            {"label": "執筆", "hours": 9, "hours_max": 12, "paid": True},
            {"label": "打合せ", "hours": 2, "paid": False},
            {"label": "修正対応", "hours": 2, "hours_max": 4, "paid": True},
        ],
        "compensation": {
            "basis": "fixed",
            "fixed_amount": 90000,
            "expenses_borne_by_worker": 3000,
            "withholding": True,
            "consumption_tax": "excluded",
        },
        "payment": {
            "delivery_date": "2026-10-15",
            "due_date": "2026-11-30",
            "reference_term_days": 60,
        },
        "availability": {"weekly_hours": 6, "weeks": 4},
        "revisions": {"rounds": 2, "hours": 4},
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def entry(report, code):
    return next(item for item in report["checklist"] if item["code"] == code)


def flag(report, code):
    return next(item for item in report["flags"] if item["code"] == code)


class EngagementTest(unittest.TestCase):
    def test_employment_is_sent_to_the_offer_terms_skill(self):
        report = MODULE.check(payload(engagement="employment"))
        self.assertIn("offer-terms-check", flag(report, "engagement_is_employment")["message"])

    def test_an_unknown_engagement_asks_for_the_actual_arrangement(self):
        self.assertIn("engagement_unknown", codes(MODULE.check(payload(engagement="unknown"))))


class WritingTest(unittest.TestCase):
    def test_chat_is_not_treated_as_writing(self):
        report = MODULE.check(payload(offer={"form": "chat"}))
        self.assertFalse(report["offer"]["in_writing"])
        self.assertIn("terms_not_in_writing", codes(report))

    def test_nothing_received_yet_is_reported_first(self):
        report = MODULE.check(payload(offer={"form": "none"}))
        self.assertIn("no_offer_received", codes(report))

    def test_a_term_agreed_only_in_chat_does_not_count_as_written(self):
        report = MODULE.check(
            payload(items=[{"code": "payment_amount", "status": "stated", "source": "chat"}])
        )
        self.assertFalse(entry(report, "payment_amount")["in_writing"])
        self.assertIn("payment_amount", flag(report, "start_blockers")["items"])

    def test_a_written_term_clears_that_blocker(self):
        report = MODULE.check(
            payload(items=[{"code": "payment_amount", "status": "stated", "source": "contract"}])
        )
        self.assertEqual(report["summary"]["start_required_in_writing"], 1)
        self.assertNotIn("payment_amount", flag(report, "start_blockers")["items"])


class ScopeTest(unittest.TestCase):
    def test_an_item_marked_not_applicable_leaves_the_counts(self):
        report = MODULE.check(
            payload(items=[{"code": "revision_limit", "status": "missing", "applicable": False}])
        )
        self.assertNotIn("revision_limit", flag(report, "start_blockers")["items"])
        self.assertIs(entry(report, "revision_limit")["applicable"], False)

    def test_conditional_items_stay_undecided_until_supplied(self):
        report = MODULE.check(payload())
        self.assertIsNone(entry(report, "inspection")["applicable"])
        self.assertIn("inspection", flag(report, "applicability_undecidable")["items"])

    def test_unconditional_items_default_to_applicable(self):
        self.assertIs(entry(MODULE.check(payload()), "deliverable")["applicable"], True)

    def test_an_unreadable_term_becomes_a_question(self):
        report = MODULE.check(
            payload(items=[{"code": "payment_due", "status": "unclear", "source": "email"}])
        )
        self.assertIn("terms_unclear", codes(report))

    def test_an_unknown_code_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(items=[{"code": "salary", "status": "stated"}]))

    def test_open_ended_revisions_are_flagged(self):
        report = MODULE.check(payload(revisions={"rounds": None, "hours": None}))
        self.assertIn("revision_scope_open_ended", codes(report))

    def test_work_without_a_deliverable_is_not_warned_about_revisions(self):
        report = MODULE.check(
            payload(
                revisions={"rounds": None, "hours": None},
                items=[{"code": "revision_limit", "status": "missing", "applicable": False}],
            )
        )
        self.assertNotIn("revision_scope_open_ended", codes(report))


class HoursTest(unittest.TestCase):
    def test_unpaid_work_is_counted_as_hours(self):
        report = MODULE.check(payload())
        self.assertEqual(report["hours"]["total_min"], 17.0)
        self.assertEqual(report["hours"]["total_max"], 22.0)
        self.assertEqual(report["hours"]["paid_min"], 11.0)
        self.assertEqual(report["hours"]["unpaid_min"], 6.0)
        self.assertIn("unpaid_hours_included", codes(report))

    def test_an_unestimated_task_is_not_filled_with_zero(self):
        report = MODULE.check(
            payload(work=[{"label": "執筆", "hours": 9, "paid": True}, {"label": "打合せ"}])
        )
        self.assertEqual(report["hours"]["total_min"], 9.0)
        self.assertIn("打合せ", flag(report, "hours_unestimated")["items"])

    def test_an_unstated_payment_status_is_not_assumed_unpaid(self):
        report = MODULE.check(payload(work=[{"label": "打合せ", "hours": 2}]))
        self.assertIsNone(report["hours"]["paid_min"])
        self.assertIsNone(report["hours"]["unpaid_min"])
        self.assertIn("payment_status_unknown", codes(report))

    def test_a_max_below_the_min_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(work=[{"label": "執筆", "hours": 9, "hours_max": 4}]))


class MoneyTest(unittest.TestCase):
    def test_the_effective_hourly_drops_when_unpaid_work_is_included(self):
        money = MODULE.check(payload())["money"]
        self.assertEqual(money["effective_hourly_paid_min"], 5625)
        self.assertEqual(money["effective_hourly_all_min"], 4091)
        self.assertLess(money["effective_hourly_all_min"], money["effective_hourly_paid_min"])

    def test_expenses_are_subtracted_before_the_hourly_figure(self):
        money = MODULE.check(payload())["money"]
        self.assertEqual(money["after_expenses_min"], 87000)
        self.assertLess(
            money["effective_hourly_after_expenses_min"], money["effective_hourly_all_min"]
        )

    def test_an_hourly_basis_multiplies_only_the_paid_hours(self):
        money = MODULE.check(
            payload(compensation={"basis": "hourly", "hourly_rate": 5000})
        )["money"]
        self.assertEqual(money["planned_total_min"], 55000)
        self.assertEqual(money["planned_total_max"], 80000)

    def test_a_per_deliverable_basis_needs_both_the_unit_and_the_count(self):
        report = MODULE.check(payload(compensation={"basis": "per_deliverable", "unit_amount": 30000}))
        self.assertIsNone(report["money"]["planned_total_min"])
        self.assertIn("planned_total_unavailable", codes(report))

    def test_an_unknown_basis_produces_no_planned_total(self):
        report = MODULE.check(payload(compensation={"basis": "unknown"}))
        self.assertIsNone(report["money"]["planned_total_min"])
        self.assertIn("compensation_basis_unknown", codes(report))

    def test_expenses_at_or_above_the_fee_are_flagged(self):
        report = MODULE.check(
            payload(
                compensation={
                    "basis": "fixed",
                    "fixed_amount": 3000,
                    "expenses_borne_by_worker": 3000,
                    "withholding": False,
                    "consumption_tax": "included",
                }
            )
        )
        self.assertIn("expenses_exceed_fee", codes(report))

    def test_the_net_amount_is_never_calculated(self):
        report = MODULE.check(
            payload(compensation={"basis": "fixed", "fixed_amount": 90000, "consumption_tax": "unknown"})
        )
        self.assertFalse(report["money"]["net_amount_calculated"])
        self.assertIn("tax_treatment_unclear", codes(report))


class PaymentTest(unittest.TestCase):
    def test_days_are_counted_from_delivery(self):
        report = MODULE.check(payload())
        self.assertEqual(report["payment"]["days_from_delivery"], 46)
        self.assertIs(report["payment"]["exceeds_reference"], False)

    def test_a_longer_term_than_the_supplied_reference_is_flagged(self):
        report = MODULE.check(
            payload(
                payment={
                    "delivery_date": "2026-10-15",
                    "due_date": "2026-12-31",
                    "reference_term_days": 60,
                }
            )
        )
        self.assertIn("payment_term_exceeds_reference", codes(report))

    def test_without_a_reference_the_days_are_reported_but_not_compared(self):
        report = MODULE.check(
            payload(payment={"delivery_date": "2026-10-15", "due_date": "2026-12-31"})
        )
        self.assertEqual(report["payment"]["days_from_delivery"], 77)
        self.assertIsNone(report["payment"]["exceeds_reference"])
        self.assertIn("payment_term_reference_not_supplied", codes(report))

    def test_a_missing_due_date_is_flagged_first(self):
        report = MODULE.check(payload(payment={"delivery_date": "2026-10-15"}))
        self.assertIn("payment_due_missing", codes(report))

    def test_acceptance_before_delivery_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.check(
                payload(
                    payment={
                        "delivery_date": "2026-10-15",
                        "acceptance_date": "2026-10-01",
                        "due_date": "2026-11-30",
                    }
                )
            )


class ScheduleTest(unittest.TestCase):
    def test_the_weekly_load_fits_the_available_time(self):
        schedule = MODULE.check(payload())["schedule"]
        self.assertEqual(schedule["weekly_needed_max"], 5.5)
        self.assertIs(schedule["fits_weekly_availability"], True)

    def test_exceeding_the_available_time_is_flagged(self):
        report = MODULE.check(payload(availability={"weekly_hours": 4, "weeks": 4}))
        self.assertIn("weekly_hours_exceed_availability", codes(report))

    def test_an_unestimated_task_leaves_the_fit_undecided(self):
        report = MODULE.check(
            payload(work=[{"label": "執筆", "hours": 9, "paid": True}, {"label": "打合せ"}])
        )
        self.assertIsNone(report["schedule"]["fits_weekly_availability"])
        self.assertIn("weekly_fit_undecidable", codes(report))


class OutputContractTest(unittest.TestCase):
    def test_no_flag_judges_the_fee_or_the_legality(self):
        messages = " ".join(item["message"] for item in MODULE.check(payload())["flags"])
        for forbidden in ("違法", "適正", "妥当", "相場より", "受けるべき"):
            self.assertNotIn(forbidden, messages)

    def test_notes_state_that_the_hourly_figure_is_only_a_division(self):
        report = MODULE.check(payload())
        self.assertTrue(any("換算時給" in note for note in report["notes"]))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["money"]["planned_total_min"], 90000)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, {"offer": {"form": "fax"}})
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
