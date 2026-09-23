import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/documents/resume-draft/scripts/check_resume_plan.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def experience(**overrides):
    base = {
        "id": "e1",
        "title": "中堅製造業向けの新規開拓",
        "timeline_label": "架空A社",
        "kind": "sales",
        "role": "member",
        "evidence": "record",
        "metrics": [{"text": "新規受注18社", "evidence": "record"}],
        "confidential_risk": False,
        "include": True,
        "supports": ["r1"],
    }
    base.update(overrides)
    return base


def payload(**overrides):
    base = {
        "track": "chuto",
        "format": "reverse_chronological",
        "as_of": "2026-09",
        "target": {
            "label": "架空商事 法人営業",
            "requirements": [
                {"id": "r1", "text": "法人営業の経験3年以上", "level": "must"},
                {"id": "r2", "text": "SaaSの導入支援の経験", "level": "want"},
            ],
        },
        "timeline": [
            {"label": "架空A社", "start": "2018-04", "end": "2022-03"},
            {"label": "架空B社", "start": "2022-04", "end": None},
        ],
        "experiences": [
            experience(),
            experience(
                id="e2",
                title="既存顧客への管理ツールの導入支援",
                timeline_label="架空B社",
                kind="improvement",
                role="owner",
                supports=["r2"],
            ),
        ],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def flag(report, code):
    return next(entry for entry in report["flags"] if entry["code"] == code)


class RequirementTest(unittest.TestCase):
    def test_supported_requirements_are_counted(self):
        report = MODULE.check(payload())
        self.assertEqual(report["summary"]["must_supported"], 1)
        self.assertEqual(report["summary"]["want_supported"], 1)
        self.assertEqual(report["requirements"][0]["supported_by"], ["e1"])

    def test_unsupported_must_requirement_is_flagged(self):
        report = MODULE.check(payload(experiences=[experience(supports=["r2"])]))
        self.assertEqual(flag(report, "must_requirement_unsupported")["items"], ["r1"])

    def test_excluded_experience_does_not_support(self):
        report = MODULE.check(payload(experiences=[experience(include=False)]))
        self.assertIn("must_requirement_unsupported", codes(report))

    def test_requirement_backed_only_by_memory_is_flagged(self):
        report = MODULE.check(payload(experiences=[experience(evidence="memory")]))
        self.assertIn("r1", flag(report, "requirement_supported_without_record")["items"])

    def test_no_target_is_treated_as_general_version(self):
        report = MODULE.check(payload(target=None, experiences=[experience(supports=[])]))
        self.assertIn("no_target", codes(report))
        self.assertEqual(report["not_supporting_any_requirement"], [])

    def test_unknown_requirement_id_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(experiences=[experience(supports=["r9"])]))


class ExperienceTest(unittest.TestCase):
    def test_unconfirmed_metric_is_flagged(self):
        report = MODULE.check(
            payload(experiences=[experience(metrics=[{"text": "解約率を半減", "evidence": "memory"}])])
        )
        self.assertEqual(flag(report, "metric_not_confirmed")["items"], ["e1"])

    def test_team_and_unstated_roles_are_flagged_separately(self):
        report = MODULE.check(
            payload(
                experiences=[
                    experience(role="team"),
                    experience(id="e2", timeline_label="架空B社", role=None),
                ]
            )
        )
        self.assertEqual(flag(report, "team_outcome")["items"], ["e1"])
        self.assertEqual(flag(report, "role_unstated")["items"], ["e2"])

    def test_confidential_experience_must_be_abstracted(self):
        report = MODULE.check(payload(experiences=[experience(confidential_risk=True)]))
        self.assertIn("confidential_not_abstracted", codes(report))
        done = MODULE.check(payload(experiences=[experience(confidential_risk=True, abstracted=True)]))
        self.assertNotIn("confidential_not_abstracted", codes(done))

    def test_unchecked_confidentiality_is_flagged(self):
        report = MODULE.check(payload(experiences=[experience(confidential_risk=None)]))
        self.assertIn("confidential_unchecked", codes(report))

    def test_undecided_inclusion_is_not_treated_as_included(self):
        report = MODULE.check(payload(experiences=[experience(include=None)]))
        self.assertIn("include_undecided", codes(report))
        self.assertEqual(report["summary"]["included"], 0)


class TimelineTest(unittest.TestCase):
    def test_reverse_chronological_puts_latest_first(self):
        report = MODULE.check(payload())
        sections = report["outline"]["sections"]
        self.assertEqual([section["label"] for section in sections], ["架空B社", "架空A社"])
        self.assertEqual(sections[0]["end"], "現在")
        self.assertEqual(sections[1]["months"], 48)
        self.assertEqual(sections[0]["months"], 54)

    def test_chronological_puts_oldest_first(self):
        report = MODULE.check(payload(format="chronological"))
        self.assertEqual(report["outline"]["sections"][0]["label"], "架空A社")

    def test_functional_groups_by_kind_and_keeps_employment_list(self):
        report = MODULE.check(payload(format="functional"))
        outline = report["outline"]
        self.assertEqual({group["kind"] for group in outline["groups"]}, {"sales", "improvement"})
        self.assertEqual(outline["employment_list"], ["架空B社", "架空A社"])

    def test_gap_between_periods_is_reported(self):
        report = MODULE.check(
            payload(
                timeline=[
                    {"label": "架空A社", "start": "2018-04", "end": "2022-03"},
                    {"label": "架空B社", "start": "2022-09", "end": None},
                ]
            )
        )
        self.assertEqual(report["gaps"][0]["months"], 5)
        self.assertEqual(report["gaps"][0]["from"], "2022-04")
        self.assertIn("timeline_gap", codes(report))

    def test_overlap_is_reported(self):
        report = MODULE.check(
            payload(
                timeline=[
                    {"label": "架空A社", "start": "2018-04", "end": "2022-06"},
                    {"label": "架空B社", "start": "2022-04", "end": None},
                ]
            )
        )
        self.assertEqual(report["overlaps"][0]["months"], 3)
        self.assertIn("timeline_overlap", codes(report))

    def test_period_without_content_and_thin_latest_period(self):
        report = MODULE.check(payload(experiences=[experience()]))
        self.assertEqual(flag(report, "period_without_content")["items"], ["架空B社"])
        self.assertIn("latest_period_thin", codes(report))

    def test_shinsotsu_skips_period_checks(self):
        report = MODULE.check(payload(track="shinsotsu", experiences=[experience()]))
        self.assertIn("shinsotsu_track", codes(report))
        self.assertNotIn("latest_period_thin", codes(report))

    def test_current_period_needs_as_of(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(as_of=None))

    def test_unknown_timeline_label_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.check(payload(experiences=[experience(timeline_label="架空Z社")]))


class CliTest(unittest.TestCase):
    def test_cli_succeeds_on_valid_input(self):
        completed = run_script(SCRIPT, payload())
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_cli_reports_bad_input_with_exit_code_two(self):
        completed = run_script(SCRIPT, {"timeline": []})
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
