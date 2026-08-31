import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/research/scout-message-triage/scripts/triage_scouts.py"
SPEC = importlib.util.spec_from_file_location("triage_scouts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def scout(**overrides):
    base = {
        "id": "s1",
        "from": "agent",
        "company": "架空システム株式会社",
        "role": "バックエンドエンジニア",
        "received": "2026-08-28",
        "conditions": {"pay": True, "location": True, "employment_type": True, "duties": True},
        "personalized": ["職務経歴書の在庫管理の記述に言及"],
        "pay_claim_type": "range",
        "user_interest": "yes",
    }
    base.update(overrides)
    return base


def payload(*scouts, as_of="2026-09-01"):
    return {"as_of": as_of, "scouts": list(scouts) or [scout()]}


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def described(report, scout_id):
    return next(entry for entry in report["scouts"] if entry["id"] == scout_id)


class RoutingTest(unittest.TestCase):
    def test_a_complete_scout_is_ready_for_posting_analysis(self):
        report = MODULE.triage(payload())
        self.assertEqual(described(report, "s1")["routing"], "ready_for_posting_analysis")

    def test_an_unnamed_employer_blocks_everything_else(self):
        entry = scout()
        del entry["company"]
        report = MODULE.triage(payload(entry))
        self.assertEqual(described(report, "s1")["routing"], "needs_company_name")
        self.assertIn("company_not_named", codes(report))

    def test_missing_conditions_route_to_confirmation(self):
        report = MODULE.triage(
            payload(
                scout(
                    conditions={
                        "pay": True,
                        "location": False,
                        "employment_type": True,
                        "duties": False,
                    }
                )
            )
        )
        self.assertEqual(described(report, "s1")["routing"], "needs_conditions")
        self.assertEqual(described(report, "s1")["missing_conditions"], ["location", "duties"])

    def test_unknown_interest_waits_on_the_user(self):
        report = MODULE.triage(payload(scout(user_interest="unknown")))
        self.assertEqual(described(report, "s1")["routing"], "user_decision_pending")
        self.assertIn("interest_unknown", codes(report))

    def test_a_declined_scout_is_not_routed_further(self):
        entry = scout(user_interest="no")
        del entry["company"]
        report = MODULE.triage(payload(entry))
        self.assertEqual(described(report, "s1")["routing"], "declined")


class DisclosureTest(unittest.TestCase):
    def test_a_template_send_is_recorded_without_being_downgraded(self):
        report = MODULE.triage(payload(scout(personalized=[])))
        self.assertIn("no_personalization", codes(report))
        self.assertEqual(described(report, "s1")["routing"], "ready_for_posting_analysis")

    def test_a_ceiling_salary_is_not_treated_as_an_offer(self):
        report = MODULE.triage(payload(scout(pay_claim_type="maximum")))
        self.assertIn("pay_claim_not_an_offer", codes(report))

    def test_a_possible_salary_is_not_treated_as_an_offer(self):
        report = MODULE.triage(payload(scout(pay_claim_type="possible")))
        self.assertIn("pay_claim_not_an_offer", codes(report))

    def test_a_stated_range_raises_no_pay_flag(self):
        report = MODULE.triage(payload())
        self.assertNotIn("pay_claim_not_an_offer", codes(report))

    def test_registration_before_details_is_flagged(self):
        report = MODULE.triage(payload(scout(requires_registration=True)))
        self.assertIn("registration_required_before_details", codes(report))


class DuplicateTest(unittest.TestCase):
    def test_the_same_employer_through_two_routes_is_flagged(self):
        report = MODULE.triage(
            payload(
                scout(id="s1", company="架空システム株式会社"),
                scout(id="s2", company="架空システム 株式会社", role="SRE"),
            )
        )
        flag = next(f for f in report["flags"] if f["code"] == "same_company_multiple_routes")
        self.assertEqual(sorted(flag["items"]), ["s1", "s2"])

    def test_different_employers_are_not_flagged(self):
        report = MODULE.triage(
            payload(
                scout(id="s1", company="架空システム株式会社"),
                scout(id="s2", company="架空メディア株式会社"),
            )
        )
        self.assertNotIn("same_company_multiple_routes", codes(report))

    def test_unnamed_employers_are_not_treated_as_duplicates(self):
        first, second = scout(id="s1"), scout(id="s2")
        del first["company"]
        del second["company"]
        report = MODULE.triage(payload(first, second))
        self.assertNotIn("same_company_multiple_routes", codes(report))


class DeadlineTest(unittest.TestCase):
    def test_a_passed_deadline_is_flagged(self):
        report = MODULE.triage(payload(scout(reply_deadline="2026-08-30")))
        self.assertIn("reply_deadline_passed", codes(report))

    def test_an_imminent_deadline_is_flagged_without_urging_a_reply(self):
        report = MODULE.triage(payload(scout(reply_deadline="2026-09-03")))
        flag = next(f for f in report["flags"] if f["code"] == "reply_deadline_soon")
        self.assertIn("条件の良さではない", flag["message"])

    def test_a_distant_deadline_is_not_flagged(self):
        report = MODULE.triage(payload(scout(reply_deadline="2026-09-30")))
        self.assertNotIn("reply_deadline_soon", codes(report))

    def test_deadlines_are_ignored_without_as_of(self):
        report = MODULE.triage(payload(scout(reply_deadline="2026-08-30"), as_of=None))
        self.assertNotIn("reply_deadline_passed", codes(report))


class OutputContractTest(unittest.TestCase):
    def test_output_carries_no_rating_of_the_opening(self):
        serialized = json.dumps(MODULE.triage(payload()), ensure_ascii=False)
        for forbidden in ("score", "rank", "promising", "recommend", "quality"):
            self.assertNotIn(forbidden, serialized)

    def test_notes_state_that_routing_is_not_a_recommendation(self):
        report = MODULE.triage(payload())
        self.assertTrue(any("応募すべきかどうかではない" in note for note in report["notes"]))

    def test_an_empty_backlog_says_so(self):
        report = MODULE.triage({"scouts": []})
        self.assertEqual(codes(report), {"scouts_not_captured"})


class InputValidationTest(unittest.TestCase):
    def test_rejects_duplicate_ids(self):
        with self.assertRaises(ValueError):
            MODULE.triage(payload(scout(), scout()))

    def test_rejects_unknown_sender(self):
        with self.assertRaises(ValueError):
            MODULE.triage(payload(scout(**{"from": "friend"})))

    def test_rejects_unknown_condition_field(self):
        with self.assertRaises(ValueError):
            MODULE.triage(payload(scout(conditions={"pay": True, "perks": True})))

    def test_rejects_unknown_pay_claim_type(self):
        with self.assertRaises(ValueError):
            MODULE.triage(payload(scout(pay_claim_type="great")))

    def test_rejects_malformed_date(self):
        with self.assertRaises(ValueError):
            MODULE.triage(payload(scout(reply_deadline="2026/09/03")))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload(), ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["summary"]["company_named"], 1)

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"scouts": [{"id": ""}]}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
