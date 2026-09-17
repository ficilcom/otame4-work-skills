import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/employer/trial-feedback/scripts/review_trial.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def payload(**overrides):
    base = {
        "as_of": "2026-10-20",
        "trial": {"label": "架空の記事改善", "kind": "paid_work"},
        "expectations": [
            {"code": "a1", "label": "記事1の改善案", "agreed_before_start": True, "result": "met"},
            {"code": "a3", "label": "記事3の改善案", "agreed_before_start": True, "result": "partial"},
        ],
        "observations": [
            {"fact": "記事1に根拠と理由が付いていた", "expectation": "a1", "source": "artifact", "observer": "編集担当"},
            {"fact": "記事3は根拠が1件欠けていた", "expectation": "a3", "source": "artifact", "observer": "編集担当"},
        ],
        "support": [{"item": "記事3の元資料", "status": "provided"}],
        "settlement": {
            "basis": "hourly",
            "hourly_rate": 2000,
            "hours_worked": 12,
            "hours_planned": 12,
            "acceptance_criteria_in_writing": True,
            "unpaid_rework_requested": False,
        },
        "feedback": {"next_step": "more_checks", "next_step_decided": True, "includes": ["facts"]},
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def flag(report, code):
    return next(item for item in report["flags"] if item["code"] == code)


class ExpectationsTest(unittest.TestCase):
    def test_a_clean_debrief_is_ready_for_the_owner(self):
        report = MODULE.review(payload())
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")
        self.assertEqual(report["summary"]["met"], 1)
        self.assertEqual(report["summary"]["partial"], 1)
        self.assertTrue(report["readiness"]["sending_is_user_action"])

    def test_expectations_added_later_are_counted_apart(self):
        expectations = payload()["expectations"] + [{"code": "speed", "label": "速さ", "result": "not_met"}]
        report = MODULE.review(payload(expectations=expectations))
        self.assertEqual(report["summary"]["expectations_added_later"], 1)
        self.assertEqual(report["summary"]["not_met"], 0)
        self.assertEqual(flag(report, "expectations_added_later")["items"], ["speed"])

    def test_unverified_is_not_not_met(self):
        expectations = [{"code": "a1", "label": "x", "agreed_before_start": True, "result": "unverified"}]
        report = MODULE.review(payload(expectations=expectations, observations=[]))
        self.assertEqual(report["summary"]["unverified"], 1)
        self.assertEqual(report["summary"]["not_met"], 0)
        self.assertIn("expectations_unverified", codes(report))

    def test_a_shortfall_with_a_support_gap_is_flagged(self):
        support = [{"item": "記事3の元資料", "status": "late", "delay_days": 5, "affected": ["a3"]}]
        report = MODULE.review(payload(support=support))
        a3 = next(item for item in report["expectations"] if item["code"] == "a3")
        self.assertEqual(a3["support_gaps"], ["記事3の元資料"])
        self.assertEqual(flag(report, "shortfall_with_support_gap")["items"], ["a3"])
        self.assertEqual(report["summary"]["support_late_or_missing"], 1)

    def test_no_expectations_blocks(self):
        report = MODULE.review(payload(expectations=[], observations=[]))
        self.assertIn("no_expectations", report["readiness"]["blockers"])


class ObservationsTest(unittest.TestCase):
    def test_second_hand_observations_are_flagged(self):
        observations = [{"fact": "遅刻したと聞いた", "expectation": "a1", "source": "hearsay"}]
        report = MODULE.review(payload(observations=observations))
        self.assertEqual(flag(report, "observations_second_hand")["items"], ["遅刻したと聞いた"])

    def test_an_observation_without_an_observer_is_flagged(self):
        observations = [{"fact": "質問が的確だった", "expectation": "a1", "source": "observed"}]
        report = MODULE.review(payload(observations=observations))
        self.assertIn("observer_missing", codes(report))

    def test_off_the_job_observations_block(self):
        observations = payload()["observations"] + [
            {"fact": "服装がラフだった", "source": "observed", "observer": "担当", "job_related": False}
        ]
        report = MODULE.review(payload(observations=observations))
        self.assertIn("observation_not_job_related", report["readiness"]["blockers"])

    def test_unlinked_job_observations_are_kept_but_noted(self):
        observations = payload()["observations"] + [
            {"fact": "レビューの指摘を翌日に反映した", "source": "observed", "observer": "編集担当"}
        ]
        report = MODULE.review(payload(observations=observations))
        self.assertEqual(flag(report, "observations_unlinked")["items"], ["レビューの指摘を翌日に反映した"])
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")

    def test_rejects_an_observation_linked_to_an_unknown_expectation(self):
        with self.assertRaises(ValueError):
            MODULE.review(payload(observations=[{"fact": "x", "expectation": "nope", "source": "observed"}]))


class SettlementTest(unittest.TestCase):
    def test_settles_the_hours_worked_apart_from_the_evaluation(self):
        report = MODULE.review(payload())
        self.assertEqual(report["settlement"]["amount_for_work_done"], 24000)
        self.assertTrue(report["settlement"]["separate_from_evaluation"])

    def test_a_reduction_without_written_criteria_blocks(self):
        settlement = payload()["settlement"] | {"proposed_reduction": 4000, "acceptance_criteria_in_writing": False}
        report = MODULE.review(payload(settlement=settlement))
        self.assertIn("reduction_without_written_criteria", report["readiness"]["blockers"])

    def test_a_reduction_without_an_amount_still_blocks(self):
        settlement = payload()["settlement"] | {"proposed_reduction": True, "acceptance_criteria_in_writing": False}
        report = MODULE.review(payload(settlement=settlement))
        self.assertEqual(report["settlement"]["proposed_reduction"], "unspecified")
        self.assertIn("reduction_without_written_criteria", report["readiness"]["blockers"])

    def test_a_reduction_with_written_criteria_is_a_note(self):
        settlement = payload()["settlement"] | {"proposed_reduction": 4000}
        report = MODULE.review(payload(settlement=settlement))
        self.assertIn("reduction_proposed", codes(report))
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")

    def test_unpaid_rework_blocks(self):
        settlement = payload()["settlement"] | {"unpaid_rework_requested": True}
        report = MODULE.review(payload(settlement=settlement))
        self.assertIn("unpaid_rework", report["readiness"]["blockers"])

    def test_does_not_invent_a_rate(self):
        settlement = {"basis": "hourly", "hours_worked": 12}
        report = MODULE.review(payload(settlement=settlement))
        self.assertIsNone(report["settlement"]["amount_for_work_done"])
        self.assertIn("settlement_incomplete", codes(report))

    def test_a_learning_visit_is_not_settled_or_judged_on_output(self):
        report = MODULE.review(payload(trial={"kind": "learning_visit"}, settlement={"basis": "none"}))
        self.assertNotIn("settlement_basis_unknown", codes(report))
        self.assertEqual(flag(report, "learning_visit_judged_on_output")["items"], ["a3"])


class FeedbackTest(unittest.TestCase):
    def test_other_candidates_and_internal_notes_block(self):
        feedback = {"next_step": "close", "next_step_decided": True, "includes": ["other_candidates", "internal_notes"]}
        report = MODULE.review(payload(feedback=feedback))
        self.assertIn("feedback_mentions_other_candidates", report["readiness"]["blockers"])
        self.assertIn("feedback_includes_internal_notes", report["readiness"]["blockers"])

    def test_an_undecided_continuation_is_not_a_notice(self):
        feedback = {"next_step": "continue", "includes": ["facts"]}
        report = MODULE.review(payload(feedback=feedback))
        self.assertIn("next_step_not_decided", report["readiness"]["blockers"])

    def test_a_decided_continuation_is_allowed(self):
        feedback = {"next_step": "continue", "next_step_decided": True, "includes": ["facts", "continuation_promise"]}
        report = MODULE.review(payload(feedback=feedback))
        self.assertEqual(report["readiness"]["status"], "ready_for_owner_review")

    def test_a_promise_before_a_decision_blocks(self):
        feedback = {"next_step": "undecided", "includes": ["hire_promise"]}
        report = MODULE.review(payload(feedback=feedback))
        self.assertIn("promise_before_decision", report["readiness"]["blockers"])


class InputTest(unittest.TestCase):
    def test_rejects_a_duplicated_expectation(self):
        expectations = [{"code": "a1", "label": "x"}, {"code": "a1", "label": "y"}]
        with self.assertRaises(ValueError):
            MODULE.review(payload(expectations=expectations, observations=[]))

    def test_rejects_an_unknown_feedback_content(self):
        with self.assertRaises(ValueError):
            MODULE.review(payload(feedback={"includes": ["salary"]}))

    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"settlement"', completed.stdout)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, raw="{not json")
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
