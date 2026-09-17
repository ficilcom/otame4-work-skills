import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/employer/trial-listing-draft/scripts/check_listing.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)

REQUIRED_FOR_PAID = (
    "work_content",
    "deliverable",
    "out_of_scope",
    "experience_required",
    "support",
    "hours",
    "schedule",
    "location",
    "compensation",
    "contract_form",
    "payment_timing",
)


def payload(**overrides):
    base = {
        "as_of": "2026-09-17",
        "listing": {
            "kind": "paid_work",
            "audience": "experienced",
            "stage": "internal_draft",
            "text": "既存記事3本の改善案を作成していただきます。公開操作は当社が行います。",
        },
        "items": [{"code": code, "status": "stated"} for code in REQUIRED_FOR_PAID],
        "plan": {
            "candidate_hours": 12,
            "weekly_hours": 6,
            "period_weeks": 2,
            "compensation": {"basis": "hourly", "hourly_rate": 2000},
            "budget": 24000,
        },
        "conditions": [],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def findings(report):
    return {finding["code"]: finding for finding in report["text_findings"]}


class ChecklistTest(unittest.TestCase):
    def test_a_complete_paid_listing_is_ready_for_the_owner_to_review(self):
        report = MODULE.check(payload())
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")
        self.assertEqual(report["readiness"]["blockers"], [])
        self.assertTrue(report["readiness"]["posting_is_user_action"])

    def test_unchecked_required_items_are_reported_separately_from_missing_ones(self):
        items = [{"code": "work_content", "status": "stated"}, {"code": "hours", "status": "missing"}]
        report = MODULE.check(payload(items=items))
        flags = {flag["code"]: flag for flag in report["flags"]}
        self.assertEqual(flags["required_items_missing"]["items"], ["hours"])
        self.assertIn("deliverable", flags["required_items_unchecked"]["items"])
        self.assertNotIn("hours", flags["required_items_unchecked"]["items"])

    def test_required_items_depend_on_the_listing_kind(self):
        report = MODULE.check(payload(listing={"kind": "learning_visit", "text": "見学60分"}, items=[]))
        required = {item["code"] for item in report["checklist"] if item["required"]}
        self.assertIn("expenses", required)
        self.assertNotIn("contract_form", required)
        self.assertNotIn("deliverable", required)

    def test_an_unknown_kind_requires_the_union_and_says_so(self):
        report = MODULE.check(payload(listing={"kind": "unknown", "text": "x"}, items=[]))
        required = {item["code"] for item in report["checklist"] if item["required"]}
        self.assertIn("expenses", required)
        self.assertIn("contract_form", required)
        self.assertIn("listing_kind_unknown", codes(report))

    def test_optional_items_never_block(self):
        items = [{"code": code, "status": "stated"} for code in REQUIRED_FOR_PAID]
        items.append({"code": "after_trial", "status": "missing"})
        report = MODULE.check(payload(items=items))
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")


class TextTest(unittest.TestCase):
    def test_open_ended_scope_blocks_and_returns_only_the_match(self):
        listing = {"kind": "paid_work", "text": "記事3本。納得いくまで修正します。その他付随する業務もお願いします。"}
        report = MODULE.check(payload(listing=listing))
        found = findings(report)["open_ended_scope"]
        self.assertEqual(found["severity"], "block")
        self.assertEqual(found["matched"], ["納得いくまで", "その他付随"])
        self.assertIn("text_needs_rewrite", codes(report))
        self.assertNotIn("text", report["listing"])

    def test_a_ceiling_expression_is_a_check_not_a_block(self):
        listing = {"kind": "paid_work", "text": "報酬は時給最大2,000円です。"}
        report = MODULE.check(payload(listing=listing))
        self.assertEqual(findings(report)["ceiling_expression"]["severity"], "check")
        self.assertNotIn("text_needs_rewrite", codes(report))

    def test_a_finite_revision_limit_is_not_flagged_as_a_ceiling(self):
        listing = {"kind": "paid_work", "text": "修正は1回、上限2時間までです。"}
        report = MODULE.check(payload(listing=listing))
        self.assertNotIn("ceiling_expression", findings(report))

    def test_unpaid_company_work_blocks(self):
        listing = {"kind": "paid_work", "text": "未経験のため無償で実務を担当していただきます。"}
        report = MODULE.check(payload(listing=listing))
        self.assertEqual(findings(report)["unpaid_company_work"]["severity"], "block")

    def test_a_hiring_guarantee_blocks(self):
        listing = {"kind": "paid_work", "text": "体験後は必ず採用します。"}
        report = MODULE.check(payload(listing=listing))
        self.assertIn("hiring_guarantee", findings(report))

    def test_personal_attributes_block(self):
        listing = {"kind": "paid_work", "text": "35歳以下の女性歓迎。"}
        report = MODULE.check(payload(listing=listing))
        self.assertEqual(
            findings(report)["personal_attribute"]["matched"], ["35歳以下", "女性歓迎"]
        )

    def test_company_work_inside_a_learning_visit_blocks(self):
        listing = {"kind": "learning_visit", "text": "見学のあと実際の注文を処理していただきます。"}
        report = MODULE.check(payload(listing=listing, items=[]))
        self.assertIn("learning_visit_does_company_work", findings(report))

    def test_the_same_words_are_fine_in_a_paid_listing(self):
        listing = {"kind": "paid_work", "text": "実際の注文を処理していただきます。"}
        report = MODULE.check(payload(listing=listing))
        self.assertNotIn("learning_visit_does_company_work", findings(report))

    def test_an_unpaid_prerequisite_blocks_a_paid_listing(self):
        listing = {"kind": "paid_work", "text": "まずは無償体験にご参加ください。"}
        report = MODULE.check(payload(listing=listing))
        self.assertIn("unpaid_as_prerequisite", findings(report))

    def test_missing_text_is_reported_not_scanned(self):
        report = MODULE.check(payload(listing={"kind": "paid_work"}))
        self.assertEqual(report["text_findings"], [])
        self.assertIn("text_missing", codes(report))
        self.assertIsNone(report["listing"]["text_length"])


class NumbersTest(unittest.TestCase):
    def test_costs_the_plan_and_compares_it_with_the_budget(self):
        report = MODULE.check(payload())
        numbers = report["numbers"]
        self.assertEqual(numbers["planned_cost_max"], 24000)
        self.assertEqual(numbers["period_capacity_hours"], 12.0)
        self.assertTrue(numbers["fits_period"])
        self.assertFalse(numbers["over_budget"])

    def test_flags_hours_that_do_not_fit_the_period(self):
        plan = payload()["plan"] | {"period_weeks": 1}
        report = MODULE.check(payload(plan=plan))
        self.assertFalse(report["numbers"]["fits_period"])
        self.assertIn("hours_exceed_period", codes(report))

    def test_flags_a_plan_over_budget_with_the_gap(self):
        plan = payload()["plan"] | {"budget": 18000}
        report = MODULE.check(payload(plan=plan))
        self.assertEqual(report["numbers"]["budget_gap"], 6000)
        self.assertIn("over_budget", codes(report))

    def test_uses_the_upper_estimate_against_the_budget(self):
        plan = payload()["plan"] | {"candidate_hours_max": 14}
        report = MODULE.check(payload(plan=plan))
        self.assertEqual(report["numbers"]["planned_cost_max"], 28000)
        self.assertIn("over_budget", codes(report))

    def test_does_not_invent_a_rate(self):
        plan = payload()["plan"] | {"compensation": {"basis": "hourly"}}
        report = MODULE.check(payload(plan=plan))
        self.assertIsNone(report["numbers"]["planned_cost_max"])
        self.assertIsNone(report["numbers"]["over_budget"])

    def test_an_unknown_basis_blocks(self):
        plan = payload()["plan"] | {"compensation": {}}
        report = MODULE.check(payload(plan=plan))
        self.assertIn("compensation_basis_unknown", codes(report))

    def test_paid_work_without_pay_blocks(self):
        plan = payload()["plan"] | {"compensation": {"basis": "none"}}
        report = MODULE.check(payload(plan=plan))
        self.assertIn("paid_work_without_pay", codes(report))

    def test_no_plan_means_no_numbers(self):
        report = MODULE.check(payload(plan=None))
        self.assertIsNone(report["numbers"])
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")


class ConditionsTest(unittest.TestCase):
    def test_internal_only_conditions_block(self):
        conditions = [{"topic": "支払主体", "agreement": "unconfirmed"}, {"topic": "単価", "agreement": "mutual"}]
        report = MODULE.check(payload(conditions=conditions))
        flag = next(flag for flag in report["flags"] if flag["code"] == "conditions_internal_only")
        self.assertEqual(flag["items"], ["支払主体"])

    def test_inexperienced_paid_work_is_kept_paid_and_noted(self):
        listing = payload()["listing"] | {"audience": "inexperienced"}
        report = MODULE.check(payload(listing=listing))
        self.assertIn("inexperienced_paid_work", codes(report))
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")


class InputTest(unittest.TestCase):
    def test_rejects_an_unknown_item_code(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(items=[{"code": "salary", "status": "stated"}]))

    def test_rejects_a_duplicated_item(self):
        items = [{"code": "hours", "status": "stated"}, {"code": "hours", "status": "missing"}]
        with self.assertRaises(ValueError):
            MODULE.check(payload(items=items))

    def test_rejects_an_unknown_kind(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(listing={"kind": "internship"}))

    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"readiness"', completed.stdout)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, raw="{not json")
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
