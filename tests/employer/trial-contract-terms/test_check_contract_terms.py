import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/employer/trial-contract-terms/scripts/check_contract_terms.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)

START_REQUIRED = (
    "deliverable",
    "delivery_date",
    "payment_amount",
    "payment_due",
    "payer",
    "scope_out",
    "revision_limit",
    "company_support",
    "ip_ownership",
    "confidentiality",
    "termination",
)


def payload(**overrides):
    base = {
        "as_of": "2026-09-17",
        "engagement": "contract_work",
        "document": {"form": "email", "planned_start": "2026-10-01"},
        "items": [{"code": code, "status": "stated", "source": "email"} for code in START_REQUIRED]
        + [{"code": "inspection", "applicable": False}],
        "compensation": {
            "basis": "hourly",
            "hourly_rate": 2000,
            "hours": 12,
            "conditional_on_outcome": False,
            "pays_work_done_on_termination": True,
        },
        "payment": {"delivery_date": "2026-10-14", "due_date": "2026-11-30", "reference_term_days": 60},
        "revisions": {"rounds": 1, "hours": 2, "unpaid": False},
        "termination": {"company_may_terminate": True, "candidate_may_terminate": True},
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def flag(report, code):
    return next(item for item in report["flags"] if item["code"] == code)


class ChecklistTest(unittest.TestCase):
    def test_complete_terms_are_ready_for_the_owner(self):
        report = MODULE.check(payload())
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")
        self.assertEqual(report["summary"]["start_required_open"], 0)
        self.assertEqual(report["summary"]["start_required_stated_in_writing"], 11)
        self.assertTrue(report["readiness"]["offering_is_user_action"])

    def test_missing_unclear_and_unchecked_are_kept_apart(self):
        items = [
            {"code": "deliverable", "status": "stated", "source": "email"},
            {"code": "payment_due", "status": "missing", "source": "email"},
            {"code": "scope_out", "status": "unclear", "source": "email"},
        ]
        report = MODULE.check(payload(items=items))
        self.assertEqual(flag(report, "start_required_missing")["items"], ["payment_due"])
        self.assertEqual(flag(report, "start_required_unclear")["items"], ["scope_out"])
        unchecked = flag(report, "start_required_unchecked")["items"]
        self.assertIn("payer", unchecked)
        self.assertNotIn("deliverable", unchecked)

    def test_a_term_only_in_chat_is_not_in_writing(self):
        items = payload()["items"]
        items = [item for item in items if item["code"] != "payment_amount"]
        items.append({"code": "payment_amount", "status": "stated", "source": "chat"})
        report = MODULE.check(payload(items=items))
        self.assertEqual(flag(report, "start_required_not_in_writing")["items"], ["payment_amount"])
        self.assertEqual(report["summary"]["start_required_stated_in_writing"], 10)

    def test_a_non_applicable_item_is_not_counted(self):
        items = [item for item in payload()["items"] if item["code"] != "revision_limit"]
        items.append({"code": "revision_limit", "applicable": False})
        report = MODULE.check(payload(items=items, revisions={}))
        self.assertEqual(report["summary"]["start_required_total"], 10)
        self.assertNotIn("revision_scope_open_ended", codes(report))

    def test_undecided_applicability_is_reported(self):
        items = [item for item in payload()["items"] if item["code"] != "inspection"]
        report = MODULE.check(payload(items=items))
        self.assertEqual(flag(report, "applicability_undecided")["items"], ["inspection"])


class DocumentTest(unittest.TestCase):
    def test_nothing_in_writing_blocks_first(self):
        report = MODULE.check(payload(document={"form": "none"}, items=[]))
        self.assertIn("nothing_in_writing_yet", report["readiness"]["blockers"])

    def test_platform_screen_is_not_assumed_to_be_writing(self):
        report = MODULE.check(payload(document={"form": "platform"}))
        self.assertFalse(report["document"]["in_writing"])
        self.assertIn("document_not_in_writing", codes(report))

    def test_employment_is_out_of_scope(self):
        report = MODULE.check(payload(engagement="employment"))
        self.assertIn("employment_not_contract_work", report["readiness"]["blockers"])

    def test_unknown_engagement_is_noted(self):
        report = MODULE.check(payload(engagement=None))
        self.assertIn("engagement_unknown", codes(report))


class MoneyTest(unittest.TestCase):
    def test_costs_the_stated_hours(self):
        report = MODULE.check(payload())
        self.assertEqual(report["money"]["planned_total"], 24000)

    def test_does_not_invent_a_rate(self):
        compensation = payload()["compensation"] | {"hourly_rate": None}
        report = MODULE.check(payload(compensation=compensation))
        self.assertIsNone(report["money"]["planned_total"])
        self.assertIn("compensation_incomplete", codes(report))

    def test_pay_tied_to_outcome_blocks(self):
        compensation = payload()["compensation"] | {"conditional_on_outcome": True}
        report = MODULE.check(payload(compensation=compensation))
        self.assertIn("payment_conditional_on_outcome", report["readiness"]["blockers"])

    def test_an_unchecked_pay_condition_is_a_note(self):
        compensation = payload()["compensation"] | {"conditional_on_outcome": None}
        report = MODULE.check(payload(compensation=compensation))
        self.assertIn("payment_condition_unchecked", codes(report))
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")

    def test_no_pay_on_termination_blocks(self):
        compensation = payload()["compensation"] | {"pays_work_done_on_termination": False}
        report = MODULE.check(payload(compensation=compensation))
        self.assertIn("no_pay_on_termination", report["readiness"]["blockers"])


class PaymentTest(unittest.TestCase):
    def test_counts_days_from_delivery(self):
        report = MODULE.check(payload())
        self.assertEqual(report["payment"]["days_from_delivery"], 47)
        self.assertFalse(report["payment"]["exceeds_reference"])

    def test_exceeding_the_verified_reference_blocks(self):
        payment = payload()["payment"] | {"due_date": "2026-12-31"}
        report = MODULE.check(payload(payment=payment))
        self.assertEqual(report["payment"]["days_from_delivery"], 78)
        self.assertTrue(report["payment"]["exceeds_reference"])
        self.assertIn("payment_term_exceeds_reference", report["readiness"]["blockers"])

    def test_no_reference_means_no_comparison(self):
        payment = payload()["payment"] | {"reference_term_days": None}
        report = MODULE.check(payload(payment=payment))
        self.assertIsNone(report["payment"]["exceeds_reference"])
        self.assertIn("payment_term_not_compared", codes(report))

    def test_a_missing_due_date_blocks(self):
        report = MODULE.check(payload(payment={"delivery_date": "2026-10-14"}))
        self.assertIn("payment_due_missing", report["readiness"]["blockers"])

    def test_counts_from_acceptance_when_given(self):
        payment = payload()["payment"] | {"acceptance_date": "2026-10-21"}
        report = MODULE.check(payload(payment=payment))
        self.assertEqual(report["payment"]["days_from_acceptance"], 40)

    def test_rejects_acceptance_before_delivery(self):
        payment = payload()["payment"] | {"acceptance_date": "2026-10-01"}
        with self.assertRaises(ValueError):
            MODULE.check(payload(payment=payment))


class RevisionsAndTerminationTest(unittest.TestCase):
    def test_open_ended_revisions_block(self):
        report = MODULE.check(payload(revisions={"rounds": None, "hours": 2}))
        self.assertIn("revision_scope_open_ended", report["readiness"]["blockers"])

    def test_zero_revisions_is_an_agreement_not_an_omission(self):
        report = MODULE.check(payload(revisions={"rounds": 0, "hours": 0}))
        self.assertNotIn("revision_scope_open_ended", codes(report))

    def test_unpaid_revisions_are_flagged(self):
        report = MODULE.check(payload(revisions={"rounds": 1, "hours": 2, "unpaid": True}))
        self.assertIn("unpaid_revisions", codes(report))

    def test_one_sided_termination_blocks(self):
        report = MODULE.check(payload(termination={"company_may_terminate": True, "candidate_may_terminate": False}))
        self.assertIn("termination_one_sided", report["readiness"]["blockers"])

    def test_unchecked_termination_is_a_note(self):
        report = MODULE.check(payload(termination={}))
        self.assertIn("termination_unchecked", codes(report))
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")


class InputTest(unittest.TestCase):
    def test_rejects_an_unknown_code(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(items=[{"code": "salary", "status": "stated"}]))

    def test_rejects_a_negative_revision_count(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(revisions={"rounds": -1, "hours": 2}))

    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"checklist"', completed.stdout)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, raw="{not json")
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
