import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/career/job-change-decision/scripts/sort_decision_inputs.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def concern(**overrides):
    base = {
        "id": "c1",
        "text": "設計に関われず実装だけになっている",
        "cause": "role",
        "portable": "no",
        "tried_internally": "yes",
        "severity": "high",
    }
    base.update(overrides)
    return base


def payload(**overrides):
    base = {
        "as_of": "2026-09-01",
        "concerns": [concern()],
        "wants": [{"text": "設計から関わりたい", "must": True}],
        "keeps": [{"text": "通勤15分", "importance": "high"}],
        "options": [
            {"code": "internal_transfer", "status": "ruled_out", "note": "制度がない"},
            {"code": "job_change", "status": "considered"},
        ],
        "decision": {"deadline": "2026-11-30", "criteria_defined": True},
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def option(report, code):
    return next(entry for entry in report["options"] if entry["code"] == code)


class SortingTest(unittest.TestCase):
    def test_a_portable_concern_is_separated_out(self):
        report = MODULE.sort_inputs(
            payload(concerns=[concern(id="c1", portable="yes", cause="self")])
        )
        self.assertEqual(report["sorted_concerns"]["follows_you"], ["c1"])
        self.assertIn("concerns_that_follow_you", codes(report))

    def test_an_employer_specific_concern_is_separated_out(self):
        report = MODULE.sort_inputs(payload())
        self.assertEqual(report["sorted_concerns"]["changes_with_employer"], ["c1"])
        self.assertNotIn("concerns_that_follow_you", codes(report))

    def test_undecided_portability_is_kept_as_unknown(self):
        report = MODULE.sort_inputs(payload(concerns=[concern(portable="unknown")]))
        self.assertEqual(report["sorted_concerns"]["portability_unknown"], ["c1"])
        self.assertIn("portability_unknown", codes(report))

    def test_untried_internal_options_are_surfaced_only_for_addressable_causes(self):
        report = MODULE.sort_inputs(
            payload(
                concerns=[
                    concern(id="c1", cause="role", tried_internally="no"),
                    concern(id="c2", cause="industry", tried_internally="no", portable="unknown"),
                ]
            )
        )
        self.assertEqual(report["sorted_concerns"]["untried_internally"], ["c1"])

    def test_not_possible_is_not_counted_as_untried(self):
        report = MODULE.sort_inputs(payload(concerns=[concern(tried_internally="not_possible")]))
        self.assertEqual(report["sorted_concerns"]["untried_internally"], [])
        self.assertNotIn("not_tried_internally", codes(report))

    def test_industry_causes_are_surfaced(self):
        report = MODULE.sort_inputs(
            payload(concerns=[concern(cause="industry", portable="unknown")])
        )
        self.assertIn("industry_wide_concerns", codes(report))

    def test_unidentified_cause_stays_unknown(self):
        report = MODULE.sort_inputs(
            payload(concerns=[concern(cause="unknown", portable="unknown")])
        )
        self.assertIn("cause_unknown", codes(report))


class BothSidesTest(unittest.TestCase):
    def test_concerns_without_a_destination_are_reported_as_one_sided(self):
        report = MODULE.sort_inputs(payload(wants=[]))
        self.assertIn("no_destination_stated", codes(report))

    def test_nothing_recorded_as_kept_is_reported(self):
        report = MODULE.sort_inputs(payload(keeps=[]))
        self.assertIn("nothing_recorded_as_kept", codes(report))

    def test_both_sides_present_raises_neither(self):
        report = MODULE.sort_inputs(payload())
        self.assertNotIn("no_destination_stated", codes(report))
        self.assertNotIn("nothing_recorded_as_kept", codes(report))


class OptionsTest(unittest.TestCase):
    def test_every_option_appears_even_when_not_supplied(self):
        report = MODULE.sort_inputs(payload(options=[]))
        self.assertEqual(len(report["options"]), 10)
        self.assertEqual(option(report, "leave_of_absence")["status"], "not_considered")

    def test_ruling_an_option_out_counts_as_having_considered_it(self):
        report = MODULE.sort_inputs(payload())
        self.assertNotIn("staying_not_considered", codes(report))

    def test_considering_only_leaving_is_flagged(self):
        report = MODULE.sort_inputs(payload(options=[{"code": "job_change", "status": "considered"}]))
        self.assertIn("staying_not_considered", codes(report))

    def test_exploring_while_employed_counts_as_staying(self):
        report = MODULE.sort_inputs(
            payload(options=[{"code": "explore_while_employed", "status": "considered"}])
        )
        self.assertTrue(option(report, "explore_while_employed")["keeps_current_job"])
        self.assertNotIn("staying_not_considered", codes(report))

    def test_untouched_options_are_listed(self):
        report = MODULE.sort_inputs(payload())
        flag = next(f for f in report["flags"] if f["code"] == "options_not_considered")
        self.assertIn("leave_of_absence", flag["items"])


class DecisionTest(unittest.TestCase):
    def test_days_to_deadline_are_counted(self):
        report = MODULE.sort_inputs(payload())
        self.assertEqual(report["decision"]["days_to_deadline"], 90)

    def test_a_passed_deadline_is_flagged(self):
        report = MODULE.sort_inputs(
            payload(decision={"deadline": "2026-08-01", "criteria_defined": True})
        )
        self.assertIn("decision_deadline_passed", codes(report))

    def test_undefined_criteria_are_flagged(self):
        report = MODULE.sort_inputs(payload(decision={"deadline": "2026-11-30"}))
        self.assertIn("decision_criteria_undefined", codes(report))

    def test_defined_criteria_clear_the_flag(self):
        report = MODULE.sort_inputs(payload())
        self.assertNotIn("decision_criteria_undefined", codes(report))


class ConstraintsTest(unittest.TestCase):
    def test_days_until_each_constraint_are_counted(self):
        report = MODULE.sort_inputs(
            payload(constraints=[{"text": "賞与の支給日", "date": "2026-12-10"}])
        )
        self.assertEqual(report["constraints"][0]["days_until"], 100)
        self.assertFalse(report["constraints"][0]["before_deadline"])
        self.assertNotIn("constraints_before_deadline", codes(report))

    def test_a_constraint_before_the_deadline_is_flagged_as_ordering(self):
        report = MODULE.sort_inputs(
            payload(constraints=[{"text": "契約更新の通知", "date": "2026-10-15"}])
        )
        flag = next(f for f in report["flags"] if f["code"] == "constraints_before_deadline")
        self.assertEqual(flag["items"], ["契約更新の通知"])
        self.assertIn("決めるべきという意味ではない", flag["message"])

    def test_a_passed_constraint_is_flagged_and_not_reported_as_upcoming(self):
        report = MODULE.sort_inputs(
            payload(constraints=[{"text": "賞与の支給日", "date": "2026-07-10"}])
        )
        self.assertIn("constraints_passed", codes(report))
        self.assertNotIn("constraints_before_deadline", codes(report))

    def test_an_undated_constraint_is_kept_and_flagged(self):
        report = MODULE.sort_inputs(payload(constraints=[{"text": "育児休業の予定"}]))
        self.assertIsNone(report["constraints"][0]["days_until"])
        self.assertIn("constraints_undated", codes(report))

    def test_constraints_are_ordered_by_date_with_undated_last(self):
        report = MODULE.sort_inputs(
            payload(
                constraints=[
                    {"text": "後の期日", "date": "2026-12-10"},
                    {"text": "日付なし"},
                    {"text": "先の期日", "date": "2026-10-01"},
                ]
            )
        )
        self.assertEqual(
            [item["text"] for item in report["constraints"]], ["先の期日", "後の期日", "日付なし"]
        )

    def test_constraints_without_as_of_have_no_day_counts(self):
        report = MODULE.sort_inputs(
            payload(as_of=None, constraints=[{"text": "賞与の支給日", "date": "2026-12-10"}])
        )
        self.assertIsNone(report["constraints"][0]["days_until"])
        self.assertNotIn("constraints_passed", codes(report))


class OutputContractTest(unittest.TestCase):
    def test_output_reaches_no_conclusion(self):
        serialized = json.dumps(MODULE.sort_inputs(payload()), ensure_ascii=False)
        for forbidden in ("recommend", "should_leave", "should_stay", "score", "verdict"):
            self.assertNotIn(forbidden, serialized)

    def test_notes_state_that_portability_is_the_users_own_judgement(self):
        report = MODULE.sort_inputs(payload())
        self.assertTrue(any("利用者自身の判断" in note for note in report["notes"]))

    def test_an_empty_input_says_so(self):
        report = MODULE.sort_inputs({"concerns": [], "options": [], "decision": {}})
        self.assertIn("concerns_not_captured", codes(report))


class InputValidationTest(unittest.TestCase):
    def test_rejects_duplicate_concern_ids(self):
        with self.assertRaises(ValueError):
            MODULE.sort_inputs(payload(concerns=[concern(), concern()]))

    def test_rejects_unknown_cause(self):
        with self.assertRaises(ValueError):
            MODULE.sort_inputs(payload(concerns=[concern(cause="fate")]))

    def test_rejects_unknown_option_code(self):
        with self.assertRaises(ValueError):
            MODULE.sort_inputs(payload(options=[{"code": "win_lottery", "status": "considered"}]))

    def test_rejects_unknown_option_status(self):
        with self.assertRaises(ValueError):
            MODULE.sort_inputs(payload(options=[{"code": "job_change", "status": "maybe"}]))

    def test_rejects_malformed_deadline(self):
        with self.assertRaises(ValueError):
            MODULE.sort_inputs(payload(decision={"deadline": "2026/11/30"}))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["summary"]["options_total"], 10)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, {"concerns": [{"id": "", "text": "x"}]})
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
