import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/interview/interview-debrief/scripts/review_interview.py"
SPEC = importlib.util.spec_from_file_location("review_interview", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def debrief(**overrides):
    base = {
        "company": "架空システム株式会社",
        "stage": "first",
        "date": "2026-09-10",
        "as_of": "2026-09-10",
        "questions": [{"text": "転職理由", "answered": "full", "prepared": True}],
        "questions_asked": [{"text": "評価はどの単位で決まるか", "result": "answered"}],
        "employer_statements": [],
        "next_steps": {
            "next_stage": "second",
            "result_promised_by": "2026-09-17",
            "who_contacts": "人事",
        },
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


class QuestionTest(unittest.TestCase):
    def test_a_fully_answered_prepared_question_raises_nothing(self):
        report = MODULE.review(debrief())
        self.assertEqual(codes(report), set())

    def test_prepared_but_unanswered_is_separated_from_unprepared(self):
        report = MODULE.review(
            debrief(
                questions=[
                    {"text": "担当範囲は", "answered": "partial", "prepared": True},
                    {"text": "揉めたときは", "answered": "none", "prepared": False},
                ]
            )
        )
        self.assertIn("prepared_but_not_answered", codes(report))
        self.assertIn("not_prepared", codes(report))
        prepared = next(f for f in report["flags"] if f["code"] == "prepared_but_not_answered")
        self.assertEqual(prepared["items"], ["担当範囲は"])

    def test_unchecked_preparation_falls_into_neither_bucket(self):
        report = MODULE.review(debrief(questions=[{"text": "担当範囲は", "answered": "none"}]))
        self.assertNotIn("prepared_but_not_answered", codes(report))
        self.assertNotIn("not_prepared", codes(report))

    def test_a_document_question_left_unanswered_is_called_out(self):
        report = MODULE.review(
            debrief(
                questions=[
                    {"text": "担当範囲は", "answered": "partial", "prepared": True, "from_documents": True}
                ]
            )
        )
        self.assertIn("documents_not_defensible", codes(report))
        self.assertEqual(report["carry_forward"]["to_document_review"], ["担当範囲は"])

    def test_partial_answers_are_counted_apart_from_unanswered(self):
        report = MODULE.review(
            debrief(
                questions=[
                    {"text": "a", "answered": "full"},
                    {"text": "b", "answered": "partial"},
                    {"text": "c", "answered": "none"},
                ]
            )
        )
        self.assertEqual(report["summary"]["answered_fully"], 1)
        self.assertEqual(report["summary"]["answered_partially"], 1)
        self.assertEqual(report["summary"]["not_answered"], 1)

    def test_an_empty_record_is_reported(self):
        report = MODULE.review(debrief(questions=[]))
        self.assertIn("questions_not_captured", codes(report))


class ReverseQuestionTest(unittest.TestCase):
    def test_deferred_answers_carry_forward(self):
        report = MODULE.review(
            debrief(questions_asked=[{"text": "残業実態", "result": "deferred"}])
        )
        self.assertIn("reverse_questions_unresolved", codes(report))
        self.assertIn("残業実態", report["carry_forward"]["to_next_interview"])

    def test_asking_nothing_is_reported(self):
        report = MODULE.review(debrief(questions_asked=[]))
        self.assertIn("no_reverse_questions_asked", codes(report))


class EmployerStatementTest(unittest.TestCase):
    def test_verbal_conditions_are_routed_to_the_terms_check(self):
        report = MODULE.review(
            debrief(
                employer_statements=[
                    {"topic": "残業", "statement": "月20時間程度", "affects_conditions": True}
                ]
            )
        )
        self.assertIn("conditions_stated_verbally", codes(report))
        self.assertEqual(report["carry_forward"]["to_terms_check"], ["残業"])

    def test_a_written_statement_is_not_routed(self):
        report = MODULE.review(
            debrief(
                employer_statements=[
                    {
                        "topic": "残業",
                        "statement": "月20時間程度",
                        "affects_conditions": True,
                        "in_writing": True,
                    }
                ]
            )
        )
        self.assertNotIn("conditions_stated_verbally", codes(report))
        self.assertEqual(report["carry_forward"]["to_terms_check"], [])

    def test_a_conflict_with_the_posting_is_flagged(self):
        report = MODULE.review(
            debrief(
                employer_statements=[
                    {
                        "topic": "勤務地",
                        "statement": "全国転勤あり",
                        "affects_conditions": True,
                        "conflicts_with_posting": True,
                    }
                ]
            )
        )
        self.assertIn("conflicts_with_posting", codes(report))

    def test_a_non_condition_statement_is_recorded_without_routing(self):
        report = MODULE.review(
            debrief(employer_statements=[{"topic": "チーム構成", "statement": "5名"}])
        )
        self.assertEqual(report["summary"]["employer_statements"], 1)
        self.assertEqual(report["carry_forward"]["to_terms_check"], [])


class TimingTest(unittest.TestCase):
    def test_a_same_day_record_is_not_flagged_as_late(self):
        report = MODULE.review(debrief())
        self.assertEqual(report["days_since_interview"], 0)
        self.assertNotIn("recorded_late", codes(report))

    def test_a_late_record_is_flagged(self):
        report = MODULE.review(debrief(as_of="2026-09-20"))
        self.assertIn("recorded_late", codes(report))

    def test_an_overdue_result_is_detected(self):
        report = MODULE.review(debrief(as_of="2026-09-20"))
        self.assertTrue(report["next_steps"]["result_overdue"])

    def test_missing_result_timing_is_reported(self):
        report = MODULE.review(debrief(next_steps={"next_stage": "second"}))
        self.assertIn("result_timing_unknown", codes(report))
        self.assertIn("contact_unknown", codes(report))
        self.assertIsNone(report["next_steps"]["result_overdue"])

    def test_rejects_an_as_of_before_the_interview(self):
        with self.assertRaises(ValueError):
            MODULE.review(debrief(as_of="2026-09-01"))


class OutputContractTest(unittest.TestCase):
    def test_output_holds_no_impression_or_prediction(self):
        serialized = json.dumps(MODULE.review(debrief()), ensure_ascii=False)
        for forbidden in ("impression", "likelihood", "pass_rate", "score", "confidence"):
            self.assertNotIn(forbidden, serialized)

    def test_notes_state_that_verbal_conditions_are_not_settled(self):
        report = MODULE.review(debrief())
        self.assertTrue(any("書面" in note for note in report["notes"]))


class InputValidationTest(unittest.TestCase):
    def test_rejects_unknown_answer_level(self):
        with self.assertRaises(ValueError):
            MODULE.review(debrief(questions=[{"text": "a", "answered": "well"}]))

    def test_rejects_unknown_reverse_result(self):
        with self.assertRaises(ValueError):
            MODULE.review(debrief(questions_asked=[{"text": "a", "result": "maybe"}]))

    def test_rejects_unknown_stage(self):
        with self.assertRaises(ValueError):
            MODULE.review(debrief(stage="third"))

    def test_rejects_missing_company(self):
        with self.assertRaises(ValueError):
            MODULE.review(debrief(company="  "))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(debrief(), ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["summary"]["answered_fully"], 1)

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"company": ""}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
