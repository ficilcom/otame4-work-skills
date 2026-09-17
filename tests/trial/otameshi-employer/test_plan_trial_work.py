import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/trial/otameshi-employer/scripts/plan_trial_work.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def task(label, **overrides):
    base = {"label": label, "kind": "company_work", "paid": True, "candidate_hours": 2}
    base.update(overrides)
    return base


def payload(**overrides):
    base = {
        "as_of": "2026-09-17",
        "plan": {
            "label": "架空のおためし業務",
            "candidate_weekly_hours": 6,
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
        },
        "budget": {"amount": 30000},
        "revisions": {"rounds": 1, "hours": 2},
        "conditions": [{"topic": "報酬", "value": "時間単価2000円", "agreement": "offered"}],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


class WorkloadTest(unittest.TestCase):
    def test_keeps_candidate_and_company_hours_apart(self):
        report = MODULE.plan(payload())
        self.assertEqual(report["workload"]["candidate_hours_min"], 12.0)
        self.assertEqual(report["workload"]["company_hours_total"], 4.0)

    def test_flags_a_plan_with_no_company_hours_at_all(self):
        tasks = [task("改善案の作成", candidate_hours=6)]
        report = MODULE.plan(payload(tasks=tasks))
        self.assertIsNone(report["workload"]["company_hours_total"])
        self.assertIn("company_hours_missing", codes(report))

    def test_does_not_treat_a_company_only_task_as_unestimated(self):
        tasks = payload()["tasks"] + [
            task("資料準備", candidate_hours=None, company_hours=2)
        ]
        report = MODULE.plan(payload(tasks=tasks))
        self.assertEqual(report["workload"]["candidate_hours_missing"], [])
        self.assertEqual(report["workload"]["company_hours_total"], 6.0)

    def test_flags_a_task_with_no_estimate_on_either_side(self):
        tasks = payload()["tasks"] + [task("未見積もりの作業", candidate_hours=None)]
        report = MODULE.plan(payload(tasks=tasks))
        self.assertEqual(report["workload"]["candidate_hours_missing"], ["未見積もりの作業"])
        self.assertIn("candidate_hours_missing", codes(report))

    def test_splits_paid_unpaid_and_undecided_hours(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=6, paid=False)
        tasks[3] = task("修正", candidate_hours=2, paid=None)
        workload = MODULE.plan(payload(tasks=tasks))["workload"]
        self.assertEqual(workload["paid_hours_min"], 4.0)
        self.assertEqual(workload["unpaid_hours"], 6.0)
        self.assertEqual(workload["pay_status_unknown_hours"], 2.0)


class CostTest(unittest.TestCase):
    def test_costs_the_paid_hours_at_the_stated_rate(self):
        report = MODULE.plan(payload())
        self.assertEqual(report["cost"]["planned_cost_min"], 24000)

    def test_excludes_unpaid_hours_from_the_cost_and_says_so(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=6, paid=False)
        report = MODULE.plan(payload(tasks=tasks))
        self.assertEqual(report["cost"]["planned_cost_min"], 12000)
        self.assertIn("unpaid_hours_in_paid_trial", codes(report))

    def test_converts_a_fixed_amount_for_comparison_only(self):
        report = MODULE.plan(
            payload(compensation={"basis": "fixed", "fixed_amount": 36000, "expenses_included": True,
                                  "tax_treatment": "源泉徴収あり", "payment_date": "2026-11-30"})
        )
        self.assertEqual(report["cost"]["effective_hourly_min"], 3000)
        self.assertIn("時間単価の契約や適法性を意味しない", " ".join(report["notes"]))

    def test_does_not_invent_a_rate(self):
        report = MODULE.plan(payload(compensation={"basis": "hourly"}))
        self.assertIsNone(report["cost"]["planned_cost_min"])
        self.assertIn("hourly_rate_missing", codes(report))


class BudgetTest(unittest.TestCase):
    def test_reports_the_difference_against_the_budget(self):
        report = MODULE.plan(payload())
        self.assertEqual(report["budget"]["difference_at_max"], 6000)
        self.assertFalse(report["budget"]["over"])

    def test_flags_a_plan_that_exceeds_the_budget(self):
        report = MODULE.plan(payload(budget={"amount": 20000}))
        self.assertEqual(report["budget"]["difference_at_max"], -4000)
        self.assertTrue(report["budget"]["over"])
        self.assertIn("over_budget", codes(report))

    def test_uses_the_upper_estimate_when_hours_are_a_range(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=6, candidate_hours_max=8)
        report = MODULE.plan(payload(tasks=tasks))
        self.assertEqual(report["cost"]["planned_cost_max"], 28000)
        self.assertEqual(report["budget"]["difference_at_max"], 2000)

    def test_says_so_when_no_budget_was_given(self):
        data = payload()
        del data["budget"]
        report = MODULE.plan(data)
        self.assertIsNone(report["budget"])
        self.assertIn("budget_not_set", codes(report))

    def test_extending_the_period_does_not_change_the_cost(self):
        plan = payload()["plan"]
        plan["period"] = {"start": "2026-10-01", "end": "2026-10-28", "checkpoint": "毎週末"}
        longer = MODULE.plan(payload(plan=plan))
        self.assertEqual(longer["cost"]["planned_cost_min"], MODULE.plan(payload())["cost"]["planned_cost_min"])
        self.assertEqual(longer["schedule"]["calendar_days"], 28)


class BoundaryRuleTest(unittest.TestCase):
    def test_flags_company_work_placed_in_the_unpaid_bucket(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=6, paid=False)
        self.assertIn("company_work_unpaid", codes(MODULE.plan(payload(tasks=tasks))))

    def test_accepts_an_unpaid_learning_visit(self):
        tasks = [task("見学", kind="learning", candidate_hours=2, paid=False, company_hours=2)]
        self.assertNotIn("company_work_unpaid", codes(MODULE.plan(payload(tasks=tasks))))

    def test_flags_an_open_ended_revision_scope(self):
        self.assertIn("revision_scope_open_ended", codes(MODULE.plan(payload(revisions={}))))

    def test_flags_conditions_the_candidate_has_not_been_shown(self):
        report = MODULE.plan(
            payload(conditions=[{"topic": "報酬", "value": "固定3万円", "agreement": "internal_draft"}])
        )
        self.assertEqual(report["not_offered_yet"], ["報酬"])
        self.assertIn("conditions_internal_only", codes(report))

    def test_flags_a_missing_checkpoint(self):
        plan = payload()["plan"]
        plan["period"] = {"start": "2026-10-01", "end": "2026-10-14"}
        self.assertIn("checkpoint_missing", codes(MODULE.plan(payload(plan=plan))))


class ScheduleTest(unittest.TestCase):
    def test_flags_a_plan_that_exceeds_the_candidate_weekly_hours(self):
        tasks = payload()["tasks"]
        tasks[1] = task("改善案の作成", candidate_hours=10)
        report = MODULE.plan(payload(tasks=tasks))
        self.assertFalse(report["schedule"]["fits_candidate_availability"])
        self.assertIn("weekly_hours_exceed_candidate", codes(report))


class InputTest(unittest.TestCase):
    def test_rejects_an_unknown_agreement_state(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(conditions=[{"topic": "報酬", "agreement": "agreed"}]))

    def test_rejects_an_empty_task_list(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(tasks=[]))

    def test_rejects_a_negative_estimate(self):
        with self.assertRaises(ValueError):
            MODULE.plan(payload(tasks=[task("作業", candidate_hours=-1)]))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["cost"]["planned_cost_min"], 24000)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, {"tasks": []})
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
