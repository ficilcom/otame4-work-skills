import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/offer/offer-decline/scripts/check_decline_plan.py"
SPEC = importlib.util.spec_from_file_location("check_decline_plan", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def declining(**overrides):
    base = {
        "id": "d1",
        "company": "架空B社",
        "stage": "offered_not_accepted",
        "route": "direct",
        "deadline": "2026-09-10",
        "notice_sent": False,
    }
    base.update(overrides)
    return base


def plan(*entries, **overrides):
    base = {
        "as_of": "2026-09-01",
        "accepting": {"company": "架空A社", "accepted": True, "terms_in_writing": True},
        "declining": list(entries) or [declining()],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def entry(report, decline_id):
    return next(item for item in report["declining"] if item["id"] == decline_id)


class OrderingTest(unittest.TestCase):
    def test_a_settled_acceptance_clears_the_ordering_flags(self):
        report = MODULE.check(plan())
        self.assertNotIn("not_accepted_elsewhere", codes(report))
        self.assertNotIn("accepting_terms_not_in_writing", codes(report))

    def test_declining_before_accepting_elsewhere_is_flagged(self):
        report = MODULE.check(plan(accepting={"company": "架空A社", "accepted": False}))
        self.assertIn("not_accepted_elsewhere", codes(report))

    def test_acceptance_without_written_terms_is_flagged(self):
        report = MODULE.check(
            plan(accepting={"company": "架空A社", "accepted": True, "terms_in_writing": False})
        )
        self.assertIn("accepting_terms_not_in_writing", codes(report))

    def test_withdrawing_mid_selection_does_not_require_an_acceptance(self):
        report = MODULE.check(plan(declining(stage="in_selection"), accepting=None))
        self.assertNotIn("not_accepted_elsewhere", codes(report))
        self.assertNotIn("accepting_terms_not_in_writing", codes(report))

    def test_declining_after_acceptance_is_separated(self):
        report = MODULE.check(plan(declining(stage="offered_accepted")))
        self.assertIn("declining_after_acceptance", codes(report))
        self.assertEqual(report["summary"]["offered_accepted"], 1)

    def test_unknown_stage_is_flagged(self):
        report = MODULE.check(plan(declining(stage="unknown")))
        self.assertIn("stage_unknown", codes(report))


class RouteTest(unittest.TestCase):
    def test_an_agent_route_names_the_agent_as_the_contact(self):
        report = MODULE.check(plan(declining(route="agent")))
        self.assertIn("route_agent", codes(report))
        self.assertIn("エージェント", entry(report, "d1")["extra_contact"])

    def test_a_school_recommendation_pulls_in_the_school(self):
        report = MODULE.check(plan(declining(route="school_recommendation")))
        self.assertIn("route_school_recommendation", codes(report))
        self.assertIn("就職課", entry(report, "d1")["extra_contact"])

    def test_a_referral_pulls_in_the_referrer(self):
        report = MODULE.check(plan(declining(route="referral")))
        self.assertIn("route_referral", codes(report))

    def test_a_direct_application_needs_no_extra_contact(self):
        report = MODULE.check(plan())
        self.assertIsNone(entry(report, "d1")["extra_contact"])

    def test_unknown_route_is_flagged(self):
        report = MODULE.check(plan(declining(route="unknown")))
        self.assertIn("route_unknown", codes(report))


class DeadlineTest(unittest.TestCase):
    def test_a_passed_deadline_is_flagged(self):
        report = MODULE.check(plan(declining(deadline="2026-08-25")))
        self.assertIn("deadline_passed", codes(report))
        self.assertEqual(entry(report, "d1")["days_to_deadline"], -7)

    def test_an_imminent_deadline_is_flagged(self):
        report = MODULE.check(plan(declining(deadline="2026-09-02")))
        self.assertIn("deadline_soon", codes(report))

    def test_a_distant_deadline_is_not_flagged(self):
        report = MODULE.check(plan())
        self.assertNotIn("deadline_soon", codes(report))
        self.assertNotIn("deadline_passed", codes(report))

    def test_deadlines_are_ignored_without_as_of(self):
        report = MODULE.check(plan(declining(deadline="2026-08-25"), as_of=None))
        self.assertNotIn("deadline_passed", codes(report))


class LooseEndTest(unittest.TestCase):
    def test_held_documents_are_flagged(self):
        report = MODULE.check(plan(declining(loose_ends={"documents_held": True})))
        self.assertIn("loose_end_documents_held", codes(report))
        self.assertEqual(entry(report, "d1")["loose_ends"], ["documents_held"])

    def test_unsettled_expenses_and_borrowed_items_are_flagged(self):
        report = MODULE.check(
            plan(declining(loose_ends={"expenses_unsettled": True, "items_borrowed": True}))
        )
        self.assertIn("loose_end_expenses_unsettled", codes(report))
        self.assertIn("loose_end_items_borrowed", codes(report))

    def test_no_loose_ends_raises_nothing(self):
        report = MODULE.check(plan())
        self.assertEqual(entry(report, "d1")["loose_ends"], [])

    def test_rejects_an_unknown_loose_end(self):
        with self.assertRaises(ValueError):
            MODULE.check(plan(declining(loose_ends={"parking_pass": True})))


class PressureTest(unittest.TestCase):
    def test_being_pressured_is_recorded_without_telling_the_user_what_to_do(self):
        report = MODULE.check(plan(declining(pressured_to_decline_others=True)))
        flag = next(f for f in report["flags"] if f["code"] == "pressured_to_decline_others")
        self.assertIn("応じる義務はない", flag["message"])
        self.assertIn("自分で決める", flag["message"])


class OutputContractTest(unittest.TestCase):
    def test_notice_still_pending_is_reported(self):
        report = MODULE.check(plan())
        self.assertIn("notice_not_sent", codes(report))

    def test_sent_notices_are_counted(self):
        report = MODULE.check(plan(declining(notice_sent=True)))
        self.assertEqual(report["summary"]["notice_sent"], 1)
        self.assertNotIn("notice_not_sent", codes(report))

    def test_output_reaches_no_legal_or_advisory_conclusion(self):
        serialized = json.dumps(MODULE.check(plan()), ensure_ascii=False)
        for forbidden in ("lawful", "illegal", "recommend", "should_decline", "score"):
            self.assertNotIn(forbidden, serialized)

    def test_notes_state_that_no_reason_is_owed(self):
        report = MODULE.check(plan())
        self.assertTrue(any("義務はない" in note for note in report["notes"]))

    def test_an_empty_plan_says_so(self):
        report = MODULE.check({"declining": []})
        self.assertEqual(codes(report), {"nothing_to_decline"})


class InputValidationTest(unittest.TestCase):
    def test_rejects_duplicate_ids(self):
        with self.assertRaises(ValueError):
            MODULE.check(plan(declining(), declining()))

    def test_rejects_unknown_stage(self):
        with self.assertRaises(ValueError):
            MODULE.check(plan(declining(stage="ghosted")))

    def test_rejects_unknown_route(self):
        with self.assertRaises(ValueError):
            MODULE.check(plan(declining(route="carrier_pigeon")))

    def test_rejects_missing_company(self):
        with self.assertRaises(ValueError):
            MODULE.check(plan(declining(company="  ")))

    def test_rejects_malformed_deadline(self):
        with self.assertRaises(ValueError):
            MODULE.check(plan(declining(deadline="2026/09/10")))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(plan(), ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["summary"]["declining"], 1)

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"declining": [{"id": "d1"}]}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
