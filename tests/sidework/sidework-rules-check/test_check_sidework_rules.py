import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/sidework/sidework-rules-check/scripts/check_sidework_rules.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def payload(**overrides):
    base = {
        "as_of": "2026-09-17",
        "status": "private_employee",
        "engagement": "contract_work",
        "rules": {
            "source": "employment_rules",
            "reviewed": True,
            "regime": "notification",
            "clause_quoted": True,
        },
        "sidework": {
            "same_industry": "no",
            "counterparty_is_client": "no",
            "uses_employer_information": "no",
            "uses_employer_assets": "no",
            "during_work_hours": "no",
            "uses_employer_name": "no",
        },
        "hours": {
            "main_scheduled_weekly": 40,
            "main_overtime_weekly": 5,
            "sidework_weekly": 6,
            "rest_days_per_week": 1,
            "health_reference_monthly_hours": 45,
        },
        "items": [],
        "application": [],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def entry(report, code):
    return next(item for item in report["checklist"] if item["code"] == code)


class EvidenceTest(unittest.TestCase):
    def test_reading_the_rules_clears_the_evidence_flag(self):
        self.assertNotIn("rules_not_reviewed", codes(MODULE.check(payload())))

    def test_hearsay_is_not_evidence(self):
        report = MODULE.check(payload(rules={"source": "hearsay", "reviewed": True}))
        self.assertIn("rules_not_reviewed", codes(report))

    def test_unread_rules_are_flagged_even_with_a_document_source(self):
        report = MODULE.check(
            payload(rules={"source": "employment_rules", "reviewed": False, "regime": "permission"})
        )
        self.assertIn("rules_not_reviewed", codes(report))

    def test_a_clause_that_was_not_quoted_is_flagged(self):
        report = MODULE.check(
            payload(
                rules={
                    "source": "employment_rules",
                    "reviewed": True,
                    "regime": "permission",
                    "clause_quoted": False,
                }
            )
        )
        self.assertIn("clause_not_quoted", codes(report))

    def test_only_documented_sources_count_as_confirmed(self):
        report = MODULE.check(
            payload(
                items=[
                    {"code": "sidework_clause", "status": "stated", "source": "employment_rules"},
                    {"code": "regime_type", "status": "stated", "source": "hearsay"},
                ]
            )
        )
        self.assertEqual(report["summary"]["items_confirmed_in_documents"], 1)

    def test_silence_in_the_rules_is_not_permission(self):
        report = MODULE.check(payload(rules={"source": "employment_rules", "reviewed": True, "regime": "silent"}))
        self.assertIn("regime_silent", codes(report))

    def test_a_prohibition_is_reported_without_ruling_on_its_validity(self):
        report = MODULE.check(
            payload(rules={"source": "employment_rules", "reviewed": True, "regime": "prohibited"})
        )
        flag = next(item for item in report["flags"] if item["code"] == "regime_prohibited")
        self.assertIn("判定しない", flag["message"])


class ApplicabilityTest(unittest.TestCase):
    def test_public_servant_items_are_out_of_scope_for_a_private_employee(self):
        report = MODULE.check(payload())
        self.assertIs(entry(report, "public_servant_permission")["applicable"], False)

    def test_public_servants_are_separated_from_the_employer_rules(self):
        report = MODULE.check(payload(status="public_servant"))
        self.assertIs(entry(report, "public_servant_permission")["applicable"], True)
        self.assertIn("public_servant_rules_differ", codes(report))

    def test_hours_aggregation_applies_only_to_employment_side_work(self):
        self.assertIs(entry(MODULE.check(payload()), "hours_aggregation")["applicable"], False)
        employed = MODULE.check(payload(engagement="employment"))
        self.assertIs(entry(employed, "hours_aggregation")["applicable"], True)

    def test_an_unknown_engagement_leaves_applicability_undecided(self):
        report = MODULE.check(payload(engagement="unknown"))
        self.assertIsNone(entry(report, "hours_aggregation")["applicable"])
        self.assertIn("applicability_undecidable", codes(report))
        self.assertIn("engagement_unknown", codes(report))


class TouchpointTest(unittest.TestCase):
    def test_a_touched_duty_is_reported_without_calling_it_a_violation(self):
        report = MODULE.check(payload(sidework={"same_industry": "yes"}))
        flag = next(item for item in report["flags"] if item["code"] == "duties_possibly_touched")
        self.assertIn("副業先が勤務先と競合する", flag["items"])
        self.assertIn("確認する", flag["message"])

    def test_unknown_touchpoints_are_not_treated_as_cleared(self):
        report = MODULE.check(payload(sidework={}))
        self.assertIn("touchpoints_unknown", codes(report))
        self.assertEqual(report["summary"]["touchpoints_unknown"], 6)

    def test_unknown_touchpoint_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(sidework={"commute_time": "yes"}))


class HoursTest(unittest.TestCase):
    def test_the_three_inputs_are_added_without_filling_gaps(self):
        report = MODULE.check(payload())
        self.assertEqual(report["hours"]["total_weekly"], 51.0)
        self.assertEqual(report["hours"]["scheduled_total_weekly"], 46.0)

    def test_a_missing_input_suppresses_the_total(self):
        report = MODULE.check(payload(hours={"main_scheduled_weekly": 40, "sidework_weekly": 6}))
        self.assertIsNone(report["hours"]["total_weekly"])
        self.assertIn("combined_hours_missing", codes(report))

    def test_scheduled_hours_over_the_reference_are_flagged_for_employment(self):
        report = MODULE.check(payload(engagement="employment"))
        self.assertIn("scheduled_hours_over_reference", codes(report))

    def test_contract_work_does_not_get_the_aggregation_flag(self):
        self.assertNotIn("scheduled_hours_over_reference", codes(MODULE.check(payload())))

    def test_the_weekly_reference_can_be_replaced(self):
        report = MODULE.check(
            payload(
                engagement="employment",
                hours={
                    "main_scheduled_weekly": 40,
                    "main_overtime_weekly": 0,
                    "sidework_weekly": 4,
                    "reference_weekly_hours": 44,
                    "health_reference_monthly_hours": 45,
                },
            )
        )
        self.assertTrue(report["hours"]["reference_supplied"])
        self.assertNotIn("scheduled_hours_over_reference", codes(report))

    def test_the_health_reference_is_only_compared_when_supplied(self):
        report = MODULE.check(
            payload(
                hours={
                    "main_scheduled_weekly": 40,
                    "main_overtime_weekly": 5,
                    "sidework_weekly": 6,
                    "rest_days_per_week": 1,
                }
            )
        )
        self.assertIsNone(report["hours"]["over_health_reference"])
        self.assertIn("health_reference_not_supplied", codes(report))

    def test_exceeding_the_supplied_health_reference_is_flagged(self):
        report = MODULE.check(
            payload(
                hours={
                    "main_scheduled_weekly": 40,
                    "main_overtime_weekly": 20,
                    "sidework_weekly": 10,
                    "rest_days_per_week": 1,
                    "health_reference_monthly_hours": 45,
                }
            )
        )
        self.assertIs(report["hours"]["over_health_reference"], True)
        self.assertIn("over_health_reference", codes(report))

    def test_a_week_without_a_rest_day_is_flagged(self):
        report = MODULE.check(
            payload(
                hours={
                    "main_scheduled_weekly": 40,
                    "main_overtime_weekly": 5,
                    "sidework_weekly": 6,
                    "rest_days_per_week": 0,
                    "health_reference_monthly_hours": 45,
                }
            )
        )
        self.assertIn("no_rest_day", codes(report))

    def test_more_rest_days_than_a_week_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(hours={"rest_days_per_week": 8}))


class ItemsTest(unittest.TestCase):
    def test_items_that_were_not_supplied_count_as_unconfirmed(self):
        report = MODULE.check(payload())
        self.assertEqual(report["summary"]["items_unknown"], report["summary"]["items_in_scope"])
        self.assertIn("items_unconfirmed", codes(report))

    def test_an_unreadable_clause_becomes_a_question(self):
        report = MODULE.check(
            payload(items=[{"code": "scope_of_rule", "status": "unclear", "source": "employment_rules"}])
        )
        self.assertIn("items_unclear", codes(report))

    def test_an_unknown_code_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(items=[{"code": "salary", "status": "stated"}]))

    def test_a_duplicated_code_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.check(
                payload(
                    items=[
                        {"code": "sanctions", "status": "stated"},
                        {"code": "sanctions", "status": "missing"},
                    ]
                )
            )


class ApplicationTest(unittest.TestCase):
    def test_missing_application_facts_are_listed(self):
        report = MODULE.check(payload(application=[{"code": "counterparty", "status": "ready"}]))
        flag = next(item for item in report["flags"] if item["code"] == "application_facts_missing")
        self.assertIn("income", flag["items"])
        self.assertNotIn("counterparty", flag["items"])

    def test_a_prohibition_does_not_ask_for_application_material(self):
        report = MODULE.check(
            payload(rules={"source": "employment_rules", "reviewed": True, "regime": "prohibited"})
        )
        self.assertFalse(report["application_required"])
        self.assertNotIn("application_facts_missing", codes(report))
        self.assertEqual(report["summary"]["application_total"], 0)


class OutputContractTest(unittest.TestCase):
    def test_no_flag_declares_the_side_work_permitted_or_the_rule_invalid(self):
        """注意の文面が、可否や規定の有効性を結論として書いていないこと。"""
        report = MODULE.check(
            payload(rules={"source": "employment_rules", "reviewed": True, "regime": "prohibited"})
        )
        messages = " ".join(flag["message"] for flag in report["flags"])
        for forbidden in ("違法", "無効", "問題ない", "許可される", "始めてよい"):
            self.assertNotIn(forbidden, messages)

    def test_notes_disclaim_any_ruling_on_the_rules(self):
        report = MODULE.check(payload())
        self.assertTrue(any("判定でもない" in note for note in report["notes"]))

    def test_notes_send_time_sensitive_topics_to_primary_sources(self):
        report = MODULE.check(payload())
        self.assertTrue(any("一次情報" in note for note in report["notes"]))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["engagement"], "contract_work")

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, {"status": "freelancer"})
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
