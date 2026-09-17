import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/trial/otameshi-candidate/scripts/check_trial_terms.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def task(label, **overrides):
    base = {"label": label, "kind": "company_work", "paid": True, "candidate_hours": 2}
    base.update(overrides)
    return base


def payload(**overrides):
    base = {
        "as_of": "2026-09-17",
        "trial": {
            "label": "架空のおためし業務",
            "engagement_type": "contract",
            "weekly_available_hours": 6,
            "period": {"start": "2026-10-01", "end": "2026-10-14", "checkpoint": "第1週末"},
        },
        "tasks": [
            task("説明", kind="learning", candidate_hours=1, company_hours=1),
            task("改善案の作成", candidate_hours=6),
            task("合同レビュー", candidate_hours=2, company_hours=2),
            task("修正", candidate_hours=2),
            task("振り返り", kind="learning", candidate_hours=1, company_hours=1),
        ],
        "compensation": {
            "basis": "hourly",
            "hourly_rate": 2000,
            "expenses_included": False,
            "tax_treatment": "源泉徴収の有無を確認する",
            "payment_date": "2026-11-30",
            "payer": "架空商事",
        },
        "revisions": {"rounds": 1, "hours": 2},
        "conditions": [{"topic": "報酬", "value": "時間単価2000円", "agreement": "company_offer"}],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


class WorkloadTest(unittest.TestCase):
    def test_sums_candidate_hours_and_keeps_company_hours_separate(self):
        report = MODULE.check(payload())
        self.assertEqual(report["workload"]["candidate_hours_min"], 12.0)
        self.assertEqual(report["workload"]["company_hours_total"], 4.0)

    def test_reports_a_range_when_an_estimate_has_an_upper_bound(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=6, candidate_hours_max=8)
        report = MODULE.check(payload(tasks=tasks))
        self.assertEqual(report["workload"]["candidate_hours_min"], 12.0)
        self.assertEqual(report["workload"]["candidate_hours_max"], 14.0)

    def test_does_not_fill_a_missing_estimate_with_zero(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=None)
        report = MODULE.check(payload(tasks=tasks))
        self.assertEqual(report["workload"]["candidate_hours_min"], 6.0)
        self.assertEqual(report["workload"]["candidate_hours_missing"], ["改善案の作成"])
        self.assertIn("candidate_hours_missing", codes(report))

    def test_does_not_treat_a_company_only_task_as_unestimated(self):
        tasks = payload()["tasks"] + [
            task("企業の資料準備", candidate_hours=None, company_hours=2)
        ]
        report = MODULE.check(payload(tasks=tasks))
        self.assertEqual(report["workload"]["candidate_hours_missing"], [])
        self.assertEqual(report["workload"]["company_hours_total"], 6.0)
        self.assertNotIn("candidate_hours_missing", codes(report))

    def test_splits_paid_unpaid_and_undecided_hours(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=6, paid=False)
        tasks[3] = task("修正", candidate_hours=2, paid=None)
        report = MODULE.check(payload(tasks=tasks))
        workload = report["workload"]
        self.assertEqual(workload["paid_hours_min"], 4.0)
        self.assertEqual(workload["unpaid_hours"], 6.0)
        self.assertEqual(workload["pay_status_unknown_hours"], 2.0)


class ScheduleTest(unittest.TestCase):
    def test_converts_the_period_to_weeks_and_weekly_hours(self):
        report = MODULE.check(payload())
        schedule = report["schedule"]
        self.assertEqual(schedule["calendar_days"], 14)
        self.assertEqual(schedule["weeks"], 2.0)
        self.assertEqual(schedule["required_weekly_hours_max"], 6.0)
        self.assertTrue(schedule["fits_weekly_availability"])

    def test_flags_a_plan_that_does_not_fit_the_weekly_availability(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=6, candidate_hours_max=8)
        report = MODULE.check(payload(tasks=tasks))
        self.assertFalse(report["schedule"]["fits_weekly_availability"])
        self.assertIn("weekly_hours_exceed_availability", codes(report))

    def test_cannot_place_the_work_without_a_period(self):
        trial = payload()["trial"]
        trial["period"] = {}
        report = MODULE.check(payload(trial=trial))
        self.assertIsNone(report["schedule"]["weeks"])
        self.assertIsNone(report["schedule"]["required_weekly_hours_min"])
        self.assertIn("period_missing", codes(report))


class CompensationTest(unittest.TestCase):
    def test_multiplies_the_rate_by_the_paid_hours_only(self):
        tasks = payload()["tasks"]
        tasks[0] = task("説明", kind="learning", candidate_hours=1, paid=False)
        report = MODULE.check(payload(tasks=tasks))
        self.assertEqual(report["compensation"]["planned_total_min"], 22000)
        self.assertIn("unpaid_hours_in_paid_trial", codes(report))

    def test_converts_a_fixed_amount_to_an_hourly_figure(self):
        report = MODULE.check(
            payload(compensation={"basis": "fixed", "fixed_amount": 24000, "expenses_included": True,
                                  "tax_treatment": "源泉徴収あり", "payment_date": "2026-11-30", "payer": "架空商事"})
        )
        self.assertEqual(report["compensation"]["planned_total_min"], 24000)
        self.assertEqual(report["compensation"]["effective_hourly_min"], 2000)

    def test_does_not_invent_a_rate_when_none_is_offered(self):
        report = MODULE.check(payload(compensation={"basis": "hourly"}))
        self.assertIsNone(report["compensation"]["planned_total_min"])
        self.assertIsNone(report["compensation"]["effective_hourly_min"])
        self.assertIn("hourly_rate_missing", codes(report))

    def test_does_not_price_a_trial_whose_basis_is_unknown(self):
        report = MODULE.check(payload(compensation={"basis": "unknown", "hourly_rate": 2000}))
        self.assertIsNone(report["compensation"]["planned_total_min"])
        self.assertIn("compensation_basis_unknown", codes(report))


class BoundaryRuleTest(unittest.TestCase):
    def test_flags_company_work_placed_in_the_unpaid_bucket(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=6, paid=False)
        report = MODULE.check(payload(tasks=tasks))
        self.assertIn("company_work_unpaid", codes(report))

    def test_flags_company_work_whose_pay_status_is_undecided(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=6, paid=None)
        report = MODULE.check(payload(tasks=tasks))
        self.assertIn("company_work_pay_unknown", codes(report))

    def test_accepts_an_unpaid_learning_visit(self):
        tasks = [task("見学", kind="learning", candidate_hours=2, paid=False)]
        report = MODULE.check(payload(tasks=tasks))
        self.assertNotIn("company_work_unpaid", codes(report))


class MinimumWageTest(unittest.TestCase):
    def test_compares_against_the_supplied_figure_only(self):
        report = MODULE.check(
            payload(minimum_wage={"hourly": 2500, "source": "架空の告示", "as_of": "2026-10-01"})
        )
        self.assertTrue(report["minimum_wage"]["below"])
        self.assertIn("below_supplied_minimum_wage", codes(report))

    def test_says_so_when_no_figure_was_supplied(self):
        report = MODULE.check(payload())
        self.assertIsNone(report["minimum_wage"])
        self.assertIn("minimum_wage_not_supplied", codes(report))


class UnconfirmedTest(unittest.TestCase):
    def test_lists_conditions_that_are_still_unconfirmed(self):
        report = MODULE.check(
            payload(conditions=[{"topic": "成果物の利用範囲", "agreement": "unconfirmed"}])
        )
        self.assertEqual(report["unconfirmed_conditions"], ["成果物の利用範囲"])
        self.assertIn("conditions_unconfirmed", codes(report))

    def test_flags_an_open_ended_revision_scope(self):
        report = MODULE.check(payload(revisions={}))
        self.assertIn("revision_scope_open_ended", codes(report))


class InputTest(unittest.TestCase):
    def test_rejects_an_unknown_task_kind(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(tasks=[task("作業", kind="volunteer")]))

    def test_rejects_an_upper_bound_below_the_estimate(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(tasks=[task("作業", candidate_hours=6, candidate_hours_max=4)]))

    def test_rejects_an_end_before_the_start(self):
        trial = payload()["trial"]
        trial["period"] = {"start": "2026-10-14", "end": "2026-10-01"}
        with self.assertRaises(ValueError):
            MODULE.check(payload(trial=trial))

    def test_rejects_an_empty_task_list(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(tasks=[]))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0)
        report = json.loads(completed.stdout)
        self.assertEqual(report["workload"]["candidate_hours_min"], 12.0)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, {"tasks": []})
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
