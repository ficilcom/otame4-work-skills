import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/employer/applicant-reply/scripts/check_applicant_fit.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def payload(**overrides):
    base = {
        "as_of": "2026-09-17",
        "requirements": [
            {"code": "editing", "label": "記事編集の経験", "required": True},
            {"code": "cms", "label": "CMSの操作", "required": False},
        ],
        "evidence": [
            {"requirement": "editing", "status": "shown", "source": "application"},
            {"requirement": "cms", "status": "shown", "source": "portfolio"},
        ],
        "reply": {"purpose": "invite", "includes": ["next_step"]},
        "proposals": [],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def flag(report, code):
    return next(item for item in report["flags"] if item["code"] == code)


class CoverageTest(unittest.TestCase):
    def test_a_clean_invitation_is_ready_for_the_owner(self):
        report = MODULE.check(payload())
        self.assertEqual(report["summary"]["required_shown"], 1)
        self.assertEqual(report["summary"]["preferred_shown"], 1)
        self.assertEqual(report["questions"], [])
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")
        self.assertTrue(report["readiness"]["sending_is_user_action"])

    def test_an_assumption_is_not_evidence(self):
        evidence = [{"requirement": "editing", "status": "shown", "source": "assumed"}]
        report = MODULE.check(payload(evidence=evidence))
        editing = next(item for item in report["coverage"] if item["code"] == "editing")
        self.assertEqual(editing["status"], "unknown")
        self.assertTrue(editing["assumed"])
        self.assertFalse(editing["stated_by_candidate"])
        self.assertEqual(flag(report, "assumed_evidence")["items"], ["editing"])
        self.assertIn("assumed_evidence", report["readiness"]["blockers"])

    def test_a_requirement_without_evidence_is_unknown_not_missing(self):
        report = MODULE.check(payload(evidence=[]))
        statuses = {item["code"]: item["status"] for item in report["coverage"]}
        self.assertEqual(statuses, {"editing": "unknown", "cms": "unknown"})
        self.assertEqual(report["summary"]["required_unknown"], 1)

    def test_required_defaults_to_true(self):
        requirements = [{"code": "x", "label": "架空の要件"}]
        report = MODULE.check(payload(requirements=requirements, evidence=[]))
        self.assertTrue(report["coverage"][0]["required"])


class QuestionsTest(unittest.TestCase):
    def test_partial_and_unknown_requirements_become_questions(self):
        evidence = [
            {"requirement": "editing", "status": "partial", "source": "chat"},
            {"requirement": "cms", "status": "unknown"},
        ]
        report = MODULE.check(payload(evidence=evidence))
        asked = [question["requirement"] for question in report["questions"]]
        self.assertEqual(asked, ["editing", "cms"])

    def test_a_required_item_not_written_is_asked_about_not_assumed_absent(self):
        evidence = [{"requirement": "editing", "status": "not_shown", "source": "application"}]
        report = MODULE.check(payload(evidence=evidence))
        question = report["questions"][0]
        self.assertEqual(question["requirement"], "editing")
        self.assertIn("書いていないだけか", question["why"])

    def test_a_preferred_item_not_written_is_an_optional_question(self):
        evidence = [
            {"requirement": "editing", "status": "shown", "source": "application"},
            {"requirement": "cms", "status": "not_shown", "source": "application"},
        ]
        report = MODULE.check(payload(evidence=evidence))
        self.assertEqual(len(report["questions"]), 1)
        self.assertFalse(report["questions"][0]["required"])
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")

    def test_personal_attributes_in_the_reasoning_block(self):
        report = MODULE.check(payload(reasoning={"non_job_attributes": ["年齢"], "compares_other_candidates": True}))
        self.assertEqual(flag(report, "decision_uses_personal_attribute")["items"], ["年齢"])
        self.assertIn("decision_uses_personal_attribute", report["readiness"]["blockers"])
        self.assertIn("decision_compares_other_candidates", codes(report))
        self.assertNotIn("decision_compares_other_candidates", report["readiness"]["blockers"])

    def test_non_job_requirements_are_excluded_and_flagged(self):
        requirements = payload()["requirements"] + [{"code": "age", "label": "30代", "job_related": False}]
        report = MODULE.check(payload(requirements=requirements))
        self.assertEqual([q["requirement"] for q in report["questions"]], [])
        self.assertEqual(flag(report, "requirement_not_job_related")["items"], ["age"])
        self.assertEqual(report["summary"]["required_total"], 1)


class ReplyTest(unittest.TestCase):
    def test_declining_before_confirming_a_required_item_blocks(self):
        evidence = [{"requirement": "editing", "status": "unknown"}]
        report = MODULE.check(payload(evidence=evidence, reply={"purpose": "decline", "includes": ["reason_for_decline"]}))
        self.assertEqual(flag(report, "decline_before_confirming")["items"], ["editing"])
        self.assertEqual(report["readiness"]["status"], "needs_work")

    def test_declining_on_confirmed_facts_is_allowed(self):
        evidence = [{"requirement": "editing", "status": "not_shown", "source": "interview"}]
        report = MODULE.check(payload(evidence=evidence, reply={"purpose": "decline", "includes": ["reason_for_decline"]}))
        self.assertNotIn("decline_before_confirming", codes(report))
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")

    def test_a_decline_without_a_reason_is_the_users_choice(self):
        evidence = [{"requirement": "editing", "status": "not_shown", "source": "interview"}]
        report = MODULE.check(payload(evidence=evidence, reply={"purpose": "decline"}))
        self.assertNotIn("decline_without_reason", codes(report))
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")

    def test_a_decline_touching_a_non_job_attribute_blocks(self):
        requirements = payload()["requirements"] + [{"code": "age", "label": "30代", "job_related": False}]
        report = MODULE.check(payload(requirements=requirements, reply={"purpose": "decline", "includes": ["reason_for_decline"]}))
        self.assertIn("decline_reason_not_job_related", report["readiness"]["blockers"])

    def test_inviting_with_open_requirements_is_a_note_not_a_block(self):
        evidence = [{"requirement": "editing", "status": "partial", "source": "application"}]
        report = MODULE.check(payload(evidence=evidence))
        self.assertEqual(flag(report, "invite_with_open_requirements")["items"], ["editing"])
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")

    def test_other_candidates_and_internal_notes_block(self):
        report = MODULE.check(payload(reply={"purpose": "invite", "includes": ["other_candidates", "internal_notes"]}))
        self.assertIn("reply_mentions_other_candidates", report["readiness"]["blockers"])
        self.assertIn("reply_includes_internal_notes", report["readiness"]["blockers"])

    def test_new_terms_in_the_reply_are_noted(self):
        report = MODULE.check(payload(reply={"purpose": "invite", "includes": ["new_work"]}))
        self.assertIn("new_terms_in_reply", codes(report))

    def test_an_unknown_purpose_blocks(self):
        report = MODULE.check(payload(reply={}))
        self.assertIn("reply_purpose_unknown", report["readiness"]["blockers"])


class ProposalsAndAvailabilityTest(unittest.TestCase):
    def test_a_proposal_presented_as_agreed_blocks(self):
        proposals = [
            {"topic": "追加の記事1本", "agreed": False, "presented_as": "agreed"},
            {"topic": "水曜レビュー", "agreed": True, "presented_as": "agreed"},
            {"topic": "開始日", "presented_as": "proposal"},
        ]
        report = MODULE.check(payload(proposals=proposals))
        self.assertEqual(flag(report, "proposal_presented_as_agreed")["items"], ["追加の記事1本"])

    def test_short_availability_asks_for_an_adjustment_not_a_decline(self):
        report = MODULE.check(payload(availability={"candidate_weekly_hours": 4, "required_weekly_hours": 6}))
        self.assertIn("availability_short", codes(report))
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")

    def test_enough_availability_is_silent(self):
        report = MODULE.check(payload(availability={"candidate_weekly_hours": 6, "required_weekly_hours": 6}))
        self.assertNotIn("availability_short", codes(report))
        self.assertNotIn("availability_not_compared", codes(report))

    def test_half_known_availability_is_not_compared(self):
        report = MODULE.check(payload(availability={"candidate_weekly_hours": 4}))
        self.assertIn("availability_not_compared", codes(report))
        self.assertNotIn("availability_short", codes(report))


class InputTest(unittest.TestCase):
    def test_rejects_evidence_for_an_unknown_requirement(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(evidence=[{"requirement": "nope", "status": "shown"}]))

    def test_rejects_an_empty_requirement_list(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(requirements=[]))

    def test_rejects_an_unknown_reply_content(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(reply={"purpose": "invite", "includes": ["salary"]}))

    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"coverage"', completed.stdout)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, raw="{not json")
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
