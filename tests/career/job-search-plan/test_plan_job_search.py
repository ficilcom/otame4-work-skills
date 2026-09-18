import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/career/job-search-plan/scripts/plan_job_search.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def application(**overrides):
    base = {
        "id": "a1",
        "employer": "架空商事",
        "channel": "agent_a",
        "stage": "applied",
        "next_action": "一次面接の候補日を返す",
        "next_action_by": "2026-09-25",
    }
    base.update(overrides)
    return base


def payload(**overrides):
    base = {
        "as_of": "2026-09-18",
        "employed": True,
        "weekly_hours_available": 4,
        "weekday_daytime_available": True,
        "review_date": "2026-11-30",
        "stop_conditions": ["睡眠が削れる週が2週続く"],
        "activities": [
            {"label": "求人票を読む", "weekly_hours": 1},
            {"label": "面接", "weekly_hours": 1.5, "weekday_daytime": True},
        ],
        "channels": [
            {"id": "agent_a", "kind": "agent", "label": "エージェントA", "terms_confirmed": True},
            {
                "id": "scout_b",
                "kind": "scout_site",
                "label": "スカウトサイトB",
                "profile_public": True,
                "current_employer_blocked": "yes",
            },
        ],
        "applications": [application()],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def flag(report, code):
    return next(f for f in report["flags"] if f["code"] == code)


class TimeTest(unittest.TestCase):
    def test_planned_hours_are_summed_against_available(self):
        report = MODULE.plan_job_search(payload())
        self.assertEqual(report["summary"]["weekly_hours_planned"], 2.5)
        self.assertEqual(report["summary"]["weekly_hours_margin"], 1.5)
        self.assertNotIn("weekly_hours_exceeded", codes(report))

    def test_exceeding_available_hours_is_flagged_without_cutting_anything(self):
        report = MODULE.plan_job_search(payload(weekly_hours_available=2))
        self.assertIn("weekly_hours_exceeded", codes(report))
        self.assertEqual(report["summary"]["weekly_hours_planned"], 2.5)

    def test_missing_available_hours_is_flagged_and_margin_is_unknown(self):
        report = MODULE.plan_job_search(payload(weekly_hours_available=None))
        self.assertIn("weekly_hours_not_stated", codes(report))
        self.assertIsNone(report["summary"]["weekly_hours_margin"])

    def test_activities_without_hours_are_listed_and_left_out_of_the_sum(self):
        report = MODULE.plan_job_search(
            payload(activities=[{"label": "面談"}, {"label": "書類", "weekly_hours": 1}])
        )
        self.assertEqual(flag(report, "activity_hours_not_stated")["items"], ["面談"])
        self.assertEqual(report["summary"]["weekly_hours_planned"], 1.0)

    def test_weekday_daytime_is_flagged_when_employed_and_unconfirmed(self):
        report = MODULE.plan_job_search(payload(weekday_daytime_available=None))
        self.assertEqual(flag(report, "weekday_daytime_unconfirmed")["items"], ["面接"])

    def test_weekday_daytime_is_not_flagged_when_not_employed(self):
        report = MODULE.plan_job_search(payload(employed=False, weekday_daytime_available=None))
        self.assertNotIn("weekday_daytime_unconfirmed", codes(report))


class ChannelTest(unittest.TestCase):
    def test_public_profile_without_block_is_flagged(self):
        report = MODULE.plan_job_search(
            payload(
                channels=[
                    {"id": "scout_b", "kind": "scout_site", "label": "B", "profile_public": True},
                ],
                applications=[],
            )
        )
        self.assertEqual(flag(report, "profile_public_without_block")["items"], ["B"])

    def test_unknown_visibility_on_a_profile_channel_is_flagged(self):
        report = MODULE.plan_job_search(
            payload(channels=[{"id": "scout_b", "kind": "scout_site", "label": "B"}], applications=[])
        )
        self.assertEqual(flag(report, "profile_visibility_unknown")["items"], ["B"])
        self.assertNotIn("profile_public_without_block", codes(report))

    def test_unknown_visibility_is_not_flagged_when_employer_is_blocked(self):
        report = MODULE.plan_job_search(
            payload(
                channels=[
                    {"id": "b", "kind": "job_board", "label": "B", "current_employer_blocked": "yes"}
                ],
                applications=[],
            )
        )
        self.assertNotIn("profile_visibility_unknown", codes(report))

    def test_unknown_visibility_on_a_direct_channel_is_not_flagged(self):
        report = MODULE.plan_job_search(
            payload(channels=[{"id": "d", "kind": "direct"}], applications=[application(channel="d")])
        )
        self.assertNotIn("profile_visibility_unknown", codes(report))

    def test_blocked_public_profile_is_not_flagged(self):
        report = MODULE.plan_job_search(payload())
        self.assertNotIn("profile_public_without_block", codes(report))

    def test_intermediated_channel_without_confirmed_terms_is_flagged(self):
        report = MODULE.plan_job_search(
            payload(
                channels=[{"id": "agent_a", "kind": "agent", "label": "A"}],
            )
        )
        self.assertEqual(flag(report, "channel_terms_unconfirmed")["items"], ["A"])

    def test_direct_channel_does_not_need_terms(self):
        report = MODULE.plan_job_search(
            payload(
                channels=[{"id": "d", "kind": "direct"}],
                applications=[application(channel="d")],
            )
        )
        self.assertNotIn("channel_terms_unconfirmed", codes(report))

    def test_same_employer_through_two_channels_is_flagged_ignoring_spacing(self):
        report = MODULE.plan_job_search(
            payload(
                applications=[
                    application(id="a1", employer="架空商事", channel="agent_a"),
                    application(id="a2", employer="架空 商事", channel="scout_b", stage="considering"),
                ]
            )
        )
        self.assertEqual(flag(report, "same_employer_multiple_channels")["items"], ["架空商事"])

    def test_active_application_without_channel_is_flagged(self):
        report = MODULE.plan_job_search(payload(applications=[application(channel=None)]))
        self.assertEqual(flag(report, "application_channel_unknown")["items"], ["a1"])

    def test_closed_application_without_channel_is_not_flagged(self):
        report = MODULE.plan_job_search(
            payload(applications=[application(channel=None, stage="withdrawn", notified=True)])
        )
        self.assertNotIn("application_channel_unknown", codes(report))

    def test_closed_applications_do_not_count_as_duplicate_routes(self):
        report = MODULE.plan_job_search(
            payload(
                applications=[
                    application(id="a1", channel="agent_a"),
                    application(id="a2", channel="scout_b", stage="not_selected"),
                ]
            )
        )
        self.assertNotIn("same_employer_multiple_channels", codes(report))


class ApplicationTest(unittest.TestCase):
    def test_days_until_next_action_are_counted(self):
        report = MODULE.plan_job_search(payload())
        self.assertEqual(report["applications"][0]["days_until_next_action"], 7)
        self.assertEqual(report["due"][0]["set_by"], "self")

    def test_active_application_without_next_action_is_flagged(self):
        report = MODULE.plan_job_search(
            payload(applications=[application(next_action=None, next_action_by=None)])
        )
        self.assertEqual(flag(report, "application_without_next_action")["items"], ["a1"])

    def test_next_action_without_a_date_is_flagged_and_missing_from_due(self):
        report = MODULE.plan_job_search(payload(applications=[application(next_action_by=None)]))
        self.assertEqual(flag(report, "next_action_undated")["items"], ["a1"])
        self.assertNotIn("application_without_next_action", codes(report))
        self.assertEqual(report["due"], [])

    def test_closed_application_without_next_action_is_not_flagged(self):
        report = MODULE.plan_job_search(
            payload(applications=[application(stage="not_selected", next_action=None, next_action_by=None)])
        )
        self.assertNotIn("application_without_next_action", codes(report))

    def test_overdue_next_action_is_flagged(self):
        report = MODULE.plan_job_search(payload(applications=[application(next_action_by="2026-09-10")]))
        self.assertIn("next_action_overdue", codes(report))

    def test_counterpart_deadline_is_listed_and_flagged_when_passed(self):
        report = MODULE.plan_job_search(
            payload(applications=[application(reply_deadline="2026-09-01")])
        )
        self.assertIn("reply_deadline_passed", codes(report))
        self.assertEqual([item["set_by"] for item in report["due"]], ["counterpart", "self"])

    def test_offer_awaiting_reply_points_to_offer_skills(self):
        report = MODULE.plan_job_search(payload(applications=[application(stage="offer")]))
        self.assertIn("offer-terms-check", flag(report, "offer_awaiting_reply")["message"])

    def test_unnotified_withdrawal_is_flagged(self):
        report = MODULE.plan_job_search(
            payload(applications=[application(stage="withdrawn", notified=False)])
        )
        self.assertEqual(flag(report, "withdrawal_not_notified")["items"], ["a1"])

    def test_notified_withdrawal_is_not_flagged(self):
        report = MODULE.plan_job_search(
            payload(applications=[application(stage="withdrawn", notified=True)])
        )
        self.assertNotIn("withdrawal_not_notified", codes(report))
        self.assertNotIn("withdrawal_notification_unknown", codes(report))

    def test_withdrawal_with_unknown_notification_is_flagged_separately(self):
        report = MODULE.plan_job_search(payload(applications=[application(stage="withdrawn")]))
        self.assertEqual(flag(report, "withdrawal_notification_unknown")["items"], ["a1"])
        self.assertNotIn("withdrawal_not_notified", codes(report))


class ReviewTest(unittest.TestCase):
    def test_days_to_review_are_counted(self):
        report = MODULE.plan_job_search(payload())
        self.assertEqual(report["summary"]["days_to_review"], 73)

    def test_missing_review_date_is_flagged(self):
        report = MODULE.plan_job_search(payload(review_date=None))
        self.assertIn("review_date_not_set", codes(report))

    def test_passed_review_date_is_flagged(self):
        report = MODULE.plan_job_search(payload(review_date="2026-09-01"))
        self.assertIn("review_date_passed", codes(report))

    def test_missing_stop_conditions_are_flagged(self):
        report = MODULE.plan_job_search(payload(stop_conditions=[]))
        self.assertIn("stop_conditions_not_stated", codes(report))


class OutputContractTest(unittest.TestCase):
    def test_output_reaches_no_recommendation(self):
        serialized = json.dumps(MODULE.plan_job_search(payload()), ensure_ascii=False)
        for forbidden in ("recommend", "score", "rank", "verdict", "should_apply"):
            self.assertNotIn(forbidden, serialized)

    def test_notes_leave_external_actions_to_the_user(self):
        report = MODULE.plan_job_search(payload())
        self.assertTrue(any("本人が行う" in note for note in report["notes"]))

    def test_empty_input_is_reported_as_undecided(self):
        report = MODULE.plan_job_search({})
        self.assertIn("weekly_hours_not_stated", codes(report))
        self.assertIn("review_date_not_set", codes(report))
        self.assertEqual(report["summary"]["applications_active"], 0)


class InputValidationTest(unittest.TestCase):
    def test_rejects_unknown_stage(self):
        with self.assertRaises(ValueError):
            MODULE.plan_job_search(payload(applications=[application(stage="hired_for_sure")]))

    def test_rejects_unknown_channel_reference(self):
        with self.assertRaises(ValueError):
            MODULE.plan_job_search(payload(applications=[application(channel="nowhere")]))

    def test_rejects_duplicate_channel_ids(self):
        with self.assertRaises(ValueError):
            MODULE.plan_job_search(
                payload(channels=[{"id": "x", "kind": "direct"}, {"id": "x", "kind": "direct"}])
            )

    def test_rejects_unknown_channel_kind(self):
        with self.assertRaises(ValueError):
            MODULE.plan_job_search(payload(channels=[{"id": "x", "kind": "telepathy"}]))

    def test_rejects_negative_hours(self):
        with self.assertRaises(ValueError):
            MODULE.plan_job_search(payload(weekly_hours_available=-1))

    def test_rejects_malformed_date(self):
        with self.assertRaises(ValueError):
            MODULE.plan_job_search(payload(review_date="2026/11/30"))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["summary"]["applications_active"], 1)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, {"applications": [{"id": "", "employer": "x"}]})
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
