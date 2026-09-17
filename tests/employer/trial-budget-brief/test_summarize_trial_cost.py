import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/employer/trial-budget-brief/scripts/summarize_trial_cost.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def payload(**overrides):
    base = {
        "as_of": "2026-09-17",
        "trial": {"label": "架空の記事改善", "kind": "paid_work"},
        "candidate_pay": {"basis": "hourly", "hourly_rate": 2000, "hours": 12, "expenses": 0},
        "company_hours": [
            {"role": "受け入れ担当", "hours": 4, "hourly_cost": 4000},
            {"role": "資料準備", "hours": 2, "hourly_cost": 4000},
        ],
        "other_costs": [{"label": "掲載料", "amount": 0, "source": "official"}],
        "budget": {"amount": 30000, "includes_company_hours": False},
        "alternatives": [],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def flag(report, code):
    return next(item for item in report["flags"] if item["code"] == code)


class TotalsTest(unittest.TestCase):
    def test_keeps_cash_and_internal_cost_apart(self):
        report = MODULE.summarize(payload())
        self.assertEqual(report["candidate_pay"]["pay_max"], 24000)
        self.assertEqual(report["company_hours"]["total_hours"], 6.0)
        self.assertEqual(report["company_hours"]["internal_cost"], 24000)
        self.assertEqual(report["totals"]["cash_max"], 24000)
        self.assertEqual(report["totals"]["with_internal_cost_max"], 48000)
        self.assertTrue(report["totals"]["cash_is_complete"])

    def test_compares_cash_with_the_budget_by_default(self):
        report = MODULE.summarize(payload())
        budget = report["totals"]["budget"]
        self.assertEqual(budget["compared_on"], "cash")
        self.assertFalse(budget["over"])
        self.assertEqual(budget["gap"], -6000)

    def test_compares_the_costed_total_when_the_budget_includes_staff_time(self):
        report = MODULE.summarize(payload(budget={"amount": 30000, "includes_company_hours": True}))
        budget = report["totals"]["budget"]
        self.assertEqual(budget["compared_on"], "with_internal_cost")
        self.assertEqual(budget["compared_amount"], 48000)
        self.assertTrue(budget["over"])
        self.assertIn("over_budget", codes(report))

    def test_uses_the_upper_estimate(self):
        report = MODULE.summarize(payload(candidate_pay={"basis": "hourly", "hourly_rate": 2000, "hours": 12, "hours_max": 16, "expenses": 0}))
        self.assertEqual(report["totals"]["cash_max"], 32000)
        self.assertTrue(report["totals"]["budget"]["over"])

    def test_adds_expenses_and_confirmed_costs_to_cash(self):
        report = MODULE.summarize(
            payload(
                candidate_pay={"basis": "fixed", "fixed_amount": 20000, "expenses": 1500},
                other_costs=[{"label": "掲載料", "amount": 5000, "source": "quote"}],
            )
        )
        self.assertEqual(report["totals"]["cash_max"], 26500)

    def test_an_unknown_cost_keeps_the_cash_total_open(self):
        other = [{"label": "掲載料", "source": "unknown"}]
        report = MODULE.summarize(payload(other_costs=other))
        self.assertEqual(report["totals"]["cash_max"], 24000)
        self.assertFalse(report["totals"]["cash_is_complete"])
        self.assertIsNone(report["totals"]["budget"]["over"])
        self.assertIn("other_costs_unknown", codes(report))
        self.assertIn("budget_undecidable", codes(report))

    def test_unknown_candidate_expenses_keep_the_cash_total_open(self):
        report = MODULE.summarize(payload(candidate_pay={"basis": "hourly", "hourly_rate": 2000, "hours": 12}))
        self.assertFalse(report["totals"]["cash_is_complete"])
        self.assertIsNone(report["totals"]["budget"]["over"])
        self.assertIn("candidate_expenses_unknown", codes(report))

    def test_an_estimated_cost_counts_but_is_flagged(self):
        other = [{"label": "交通費", "amount": 2000, "source": "estimate"}]
        report = MODULE.summarize(payload(other_costs=other))
        self.assertEqual(report["other_costs"]["estimated_total"], 2000)
        self.assertEqual(report["totals"]["cash_max"], 26000)
        flag = next(flag for flag in report["flags"] if flag["code"] == "other_costs_estimated")
        self.assertEqual(flag["items"], ["交通費"])


class CompanyHoursTest(unittest.TestCase):
    def test_does_not_cost_staff_time_when_a_role_has_no_rate(self):
        hours = [{"role": "受け入れ担当", "hours": 4, "hourly_cost": 4000}, {"role": "レビュー", "hours": 2}]
        report = MODULE.summarize(payload(company_hours=hours))
        self.assertEqual(report["company_hours"]["total_hours"], 6.0)
        self.assertIsNone(report["company_hours"]["internal_cost"])
        self.assertIsNone(report["totals"]["with_internal_cost_max"])
        flag = next(flag for flag in report["flags"] if flag["code"] == "company_hours_not_costed")
        self.assertEqual(flag["items"], ["レビュー"])

    def test_flags_missing_staff_hours(self):
        report = MODULE.summarize(payload(company_hours=[]))
        self.assertIsNone(report["company_hours"]["total_hours"])
        self.assertIn("company_hours_missing", codes(report))

    def test_lists_roles_without_an_estimate(self):
        report = MODULE.summarize(payload(company_hours=[{"role": "説明"}]))
        self.assertEqual(report["company_hours"]["unestimated_roles"], ["説明"])

    def test_an_unestimated_role_keeps_the_internal_cost_and_comparison_open(self):
        hours = [{"role": "受け入れ担当", "hours": 4, "hourly_cost": 4000}, {"role": "レビュー", "hourly_cost": 4000}]
        report = MODULE.summarize(payload(company_hours=hours, budget={"amount": 30000, "includes_company_hours": True}))
        self.assertIsNone(report["company_hours"]["internal_cost"])
        self.assertIsNone(report["totals"]["budget"]["over"])
        self.assertFalse(report["totals"]["budget"]["decidable"])
        self.assertEqual(flag(report, "company_hours_incomplete")["items"], ["レビュー"])

    def test_an_unspecified_budget_scope_is_not_decided(self):
        report = MODULE.summarize(payload(budget={"amount": 30000}))
        self.assertIsNone(report["totals"]["budget"]["compared_on"])
        self.assertIsNone(report["totals"]["budget"]["over"])
        self.assertIn("budget_scope_unknown", codes(report))


class CandidatePayTest(unittest.TestCase):
    def test_does_not_invent_a_rate(self):
        report = MODULE.summarize(payload(candidate_pay={"basis": "hourly", "hours": 12}))
        self.assertIsNone(report["candidate_pay"]["pay_max"])
        self.assertIsNone(report["totals"]["cash_max"])
        self.assertIn("candidate_pay_incomplete", codes(report))

    def test_unknown_basis_is_reported(self):
        report = MODULE.summarize(payload(candidate_pay={}))
        self.assertIn("candidate_pay_unknown", codes(report))

    def test_paid_work_without_pay_is_flagged(self):
        report = MODULE.summarize(payload(candidate_pay={"basis": "none"}))
        self.assertEqual(report["totals"]["cash_max"], 0)
        self.assertIn("paid_work_without_pay", codes(report))

    def test_a_learning_visit_may_be_unpaid(self):
        report = MODULE.summarize(payload(trial={"kind": "learning_visit"}, candidate_pay={"basis": "none"}))
        self.assertNotIn("paid_work_without_pay", codes(report))


class AlternativesTest(unittest.TestCase):
    def test_only_verified_amounts_are_comparable(self):
        alternatives = [
            {"label": "人材紹介", "amount": 900000, "source": "estimate"},
            {"label": "求人媒体", "amount": 200000, "source": "quote"},
            {"label": "リファラル", "source": "unknown"},
        ]
        report = MODULE.summarize(payload(alternatives=alternatives))
        by_label = {alt["label"]: alt for alt in report["alternatives"]}
        self.assertFalse(by_label["人材紹介"]["comparable"])
        self.assertIsNone(by_label["人材紹介"]["amount"])
        self.assertTrue(by_label["求人媒体"]["comparable"])
        flag = next(flag for flag in report["flags"] if flag["code"] == "alternatives_unverified")
        self.assertEqual(flag["items"], ["人材紹介", "リファラル"])

    def test_says_so_when_no_budget_was_given(self):
        report = MODULE.summarize(payload(budget=None))
        self.assertIsNone(report["totals"]["budget"])
        self.assertIn("budget_not_set", codes(report))


class InputTest(unittest.TestCase):
    def test_rejects_an_unknown_source(self):
        with self.assertRaises(ValueError):
            MODULE.summarize(payload(other_costs=[{"label": "x", "amount": 1, "source": "guess"}]))

    def test_rejects_a_range_below_the_estimate(self):
        with self.assertRaises(ValueError):
            MODULE.summarize(payload(candidate_pay={"basis": "hourly", "hourly_rate": 2000, "hours": 12, "hours_max": 10}))

    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"totals"', completed.stdout)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, raw="{not json")
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
