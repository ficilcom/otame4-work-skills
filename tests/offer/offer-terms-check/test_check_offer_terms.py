import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/offer/offer-terms-check/scripts/check_offer_terms.py"
SPEC = importlib.util.spec_from_file_location("check_offer_terms", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def offer(**overrides):
    base = {
        "employer": "架空システム株式会社",
        "document": {
            "kind": "working_conditions_notice",
            "form": "written",
            "received_date": "2026-09-02",
        },
        "contract": {
            "type": "indefinite",
            "shift_work": False,
            "part_time_or_fixed_term": False,
        },
        "offer": {"offer_date": "2026-09-01", "acceptance_deadline": "2026-09-20"},
        "items": [{"code": "workplace", "status": "stated", "source": "notice"}],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def item(report, code):
    return next(entry for entry in report["items"] if entry["code"] == code)


def flag(report, code):
    return next(entry for entry in report["flags"] if entry["code"] == code)


class ChecklistTest(unittest.TestCase):
    def test_unlisted_items_count_as_unchecked_not_missing(self):
        report = MODULE.check(offer())
        self.assertEqual(item(report, "resignation")["status"], "unknown")
        self.assertIn("required_item_unchecked", codes(report))
        self.assertNotIn("required_item_missing", codes(report))

    def test_missing_is_reported_only_when_confirmed_absent(self):
        report = MODULE.check(
            offer(items=[{"code": "resignation", "status": "missing", "source": "notice"}])
        )
        self.assertIn("required_item_missing", codes(report))
        self.assertEqual(flag(report, "required_item_missing")["items"], ["resignation"])

    def test_verbal_statement_does_not_count_as_written(self):
        report = MODULE.check(
            offer(items=[{"code": "duties", "status": "stated", "source": "interview"}])
        )
        self.assertFalse(item(report, "duties")["in_writing"])
        self.assertIn("stated_outside_written_document", codes(report))

    def test_written_statement_counts_as_confirmed(self):
        report = MODULE.check(
            offer(items=[{"code": "duties", "status": "stated", "source": "notice"}])
        )
        self.assertTrue(item(report, "duties")["in_writing"])
        self.assertNotIn("stated_outside_written_document", codes(report))

    def test_change_scope_is_flagged_until_confirmed(self):
        report = MODULE.check(offer())
        self.assertIn("change_scope_unconfirmed", codes(report))

    def test_change_scope_clears_when_both_are_stated(self):
        report = MODULE.check(
            offer(
                items=[
                    {"code": "workplace_change_scope", "status": "stated", "source": "notice"},
                    {"code": "duties_change_scope", "status": "stated", "source": "notice"},
                ]
            )
        )
        self.assertNotIn("change_scope_unconfirmed", codes(report))


class ApplicabilityTest(unittest.TestCase):
    def test_renewal_items_are_not_required_for_indefinite_contracts(self):
        report = MODULE.check(offer())
        self.assertEqual(item(report, "renewal_criteria")["required"], "no")
        self.assertNotIn("fixed_term_renewal_unconfirmed", codes(report))

    def test_fixed_term_contract_requires_renewal_terms(self):
        report = MODULE.check(offer(contract={"type": "fixed_term", "shift_work": False}))
        self.assertEqual(item(report, "renewal_criteria")["required"], "yes")
        self.assertIn("fixed_term_renewal_unconfirmed", codes(report))

    def test_fixed_term_contract_pulls_in_part_time_disclosures(self):
        report = MODULE.check(offer(contract={"type": "fixed_term"}))
        self.assertEqual(item(report, "consultation_contact")["required"], "yes")

    def test_unknown_contract_type_is_flagged(self):
        report = MODULE.check(offer(contract={"type": "unknown"}))
        self.assertIn("contract_type_unknown", codes(report))
        self.assertEqual(item(report, "renewal_criteria")["required"], "depends")

    def test_conditional_item_is_out_of_scope_when_marked_not_applicable(self):
        report = MODULE.check(
            offer(
                items=[
                    {
                        "code": "retirement_allowance",
                        "status": "unknown",
                        "source": "unknown",
                        "applicable": False,
                    }
                ]
            )
        )
        self.assertEqual(item(report, "retirement_allowance")["required"], "no")

    def test_conditional_item_without_applicability_is_depends(self):
        report = MODULE.check(offer())
        self.assertEqual(item(report, "leave_of_absence")["required"], "depends")
        self.assertIn("applicability_unknown", codes(report))


class ComparisonTest(unittest.TestCase):
    def test_matching_text_is_consistent_across_whitespace(self):
        report = MODULE.check(
            offer(
                comparisons=[
                    {
                        "topic": "月額基本給",
                        "values": {"posting": "月給 28万円", "notice": "月給28万円"},
                    }
                ]
            )
        )
        self.assertEqual(report["comparisons"][0]["verdict"], "consistent")
        self.assertNotIn("source_conflict", codes(report))

    def test_differing_text_is_reported_as_conflict(self):
        report = MODULE.check(
            offer(
                comparisons=[
                    {
                        "topic": "月額基本給",
                        "values": {"posting": "月給28万円", "notice": "月給25万円"},
                    }
                ]
            )
        )
        self.assertEqual(report["comparisons"][0]["verdict"], "different")
        self.assertIn("source_conflict", codes(report))

    def test_condition_absent_from_written_document_is_reported(self):
        report = MODULE.check(
            offer(comparisons=[{"topic": "リモート勤務", "values": {"interview": "週3日在宅可"}}])
        )
        self.assertEqual(report["comparisons"][0]["verdict"], "not_in_written_document")
        self.assertIn("terms_not_in_written_document", codes(report))

    def test_lower_written_amount_is_reported_with_the_difference(self):
        report = MODULE.check(
            offer(
                comparisons=[
                    {
                        "topic": "月額基本給",
                        "values": {"posting": "月給28万円", "notice": "月給25万円"},
                        "amounts": {"posting": 280000, "notice": 250000},
                    }
                ]
            )
        )
        self.assertEqual(report["comparisons"][0]["amount_gap"]["difference"], -30000)
        self.assertIn("amount_lower_in_written_document", codes(report))

    def test_higher_written_amount_is_not_flagged(self):
        report = MODULE.check(
            offer(
                comparisons=[
                    {
                        "topic": "月額基本給",
                        "values": {"posting": "月給25万円", "notice": "月給28万円"},
                        "amounts": {"posting": 250000, "notice": 280000},
                    }
                ]
            )
        )
        self.assertNotIn("amount_lower_in_written_document", codes(report))


class AcceptanceWindowTest(unittest.TestCase):
    def test_window_days_are_counted(self):
        report = MODULE.check(offer())
        self.assertEqual(report["acceptance"]["window_days"], 19)
        self.assertNotIn("short_acceptance_window", codes(report))

    def test_short_window_is_flagged(self):
        report = MODULE.check(
            offer(offer={"offer_date": "2026-09-01", "acceptance_deadline": "2026-09-05"})
        )
        self.assertIn("short_acceptance_window", codes(report))

    def test_deadline_before_the_written_terms_arrive_is_flagged(self):
        report = MODULE.check(
            offer(
                document={
                    "kind": "working_conditions_notice",
                    "form": "written",
                    "received_date": "2026-09-25",
                }
            )
        )
        self.assertFalse(report["acceptance"]["written_terms_before_deadline"])
        self.assertIn("deadline_before_written_terms", codes(report))

    def test_no_written_document_is_flagged(self):
        report = MODULE.check(offer(document={"kind": "none", "form": "none"}))
        self.assertIn("no_written_terms", codes(report))
        self.assertIn("deadline_before_written_terms", codes(report))

    def test_electronic_delivery_counts_as_written(self):
        report = MODULE.check(
            offer(
                document={
                    "kind": "working_conditions_notice",
                    "form": "electronic",
                    "received_date": "2026-09-02",
                }
            )
        )
        self.assertTrue(report["document"]["is_written"])
        self.assertNotIn("no_written_terms", codes(report))


class InputValidationTest(unittest.TestCase):
    def test_rejects_unknown_item_code(self):
        with self.assertRaises(ValueError):
            MODULE.check(offer(items=[{"code": "salary", "status": "stated", "source": "notice"}]))

    def test_rejects_duplicate_item_code(self):
        with self.assertRaises(ValueError):
            MODULE.check(
                offer(
                    items=[
                        {"code": "workplace", "status": "stated", "source": "notice"},
                        {"code": "workplace", "status": "missing", "source": "notice"},
                    ]
                )
            )

    def test_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            MODULE.check(offer(items=[{"code": "workplace", "status": "probably", "source": "notice"}]))

    def test_rejects_deadline_before_offer_date(self):
        with self.assertRaises(ValueError):
            MODULE.check(
                offer(offer={"offer_date": "2026-09-10", "acceptance_deadline": "2026-09-01"})
            )

    def test_rejects_malformed_date(self):
        with self.assertRaises(ValueError):
            MODULE.check(offer(offer={"offer_date": "2026/09/01"}))

    def test_rejects_missing_employer(self):
        with self.assertRaises(ValueError):
            MODULE.check(offer(employer="  "))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(offer(), ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["summary"]["stated_in_writing"], 1)

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"employer": ""}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
