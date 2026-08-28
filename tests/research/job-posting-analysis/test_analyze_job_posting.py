import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/research/job-posting-analysis/scripts/analyze_job_posting.py"
SPEC = importlib.util.spec_from_file_location("analyze_job_posting", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def compensation(**overrides):
    base = {
        "basis": "posted",
        "annual_min": 4200000,
        "annual_max": 5400000,
        "bonus_included_in_range": True,
        "fixed_overtime": {"included_in_range": True, "hours": 20, "annual_amount": 600000},
    }
    base.update(overrides)
    return base


def working_hours(**overrides):
    base = {"system": "standard", "daily_scheduled_hours": 8, "monthly_working_days": 20}
    base.update(overrides)
    return base


def posting(**overrides):
    base = {
        "title": "Webアプリケーションエンジニア",
        "employment_type": "正社員",
        "compensation": compensation(),
        "working_hours": working_hours(),
        "requirements": [
            {"text": "開発経験3年以上", "kind": "must", "user_status": "met", "measurable": True}
        ],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


class PayBreakdownTest(unittest.TestCase):
    def test_fixed_overtime_is_removed_when_included(self):
        report = MODULE.analyze(posting())
        self.assertEqual(report["pay"]["base_annual_min_excluding_fixed_overtime"], 3600000)
        self.assertEqual(report["pay"]["base_annual_max_excluding_fixed_overtime"], 4800000)

    def test_fixed_overtime_is_kept_when_paid_on_top(self):
        report = MODULE.analyze(
            posting(
                compensation=compensation(
                    fixed_overtime={"included_in_range": False, "hours": 20, "annual_amount": 600000}
                )
            )
        )
        self.assertEqual(report["pay"]["base_annual_min_excluding_fixed_overtime"], 4200000)

    def test_hourly_rate_includes_deemed_overtime_hours(self):
        report = MODULE.analyze(posting())
        self.assertEqual(report["pay"]["assumed_annual_hours"], 2160.0)
        self.assertEqual(report["pay"]["hourly_min"], 1944)

    def test_missing_scheduled_hours_leaves_hourly_null(self):
        report = MODULE.analyze(posting(working_hours=None))
        self.assertIsNone(report["pay"]["hourly_min"])
        self.assertIsNone(report["pay"]["assumed_annual_hours"])
        self.assertIn("scheduled_hours_unknown", codes(report))

    def test_monthly_hours_can_be_given_directly(self):
        report = MODULE.analyze(
            posting(working_hours={"system": "flex", "monthly_scheduled_hours": 160})
        )
        self.assertEqual(report["pay"]["assumed_annual_hours"], 2160.0)

    def test_undisclosed_fixed_overtime_leaves_base_null(self):
        comp = compensation()
        del comp["fixed_overtime"]
        report = MODULE.analyze(posting(compensation=comp))
        self.assertIsNone(report["pay"]["base_annual_min_excluding_fixed_overtime"])
        self.assertIn("fixed_overtime_undisclosed", codes(report))

    def test_unknown_inclusion_leaves_base_null_not_zero(self):
        report = MODULE.analyze(
            posting(
                compensation=compensation(
                    fixed_overtime={"included_in_range": None, "hours": 20, "annual_amount": 600000}
                )
            )
        )
        self.assertIsNone(report["pay"]["base_annual_min_excluding_fixed_overtime"])
        self.assertIn("fixed_overtime_inclusion_unknown", codes(report))

    def test_range_ratio_is_reported(self):
        report = MODULE.analyze(posting())
        self.assertAlmostEqual(report["pay"]["range_ratio"], 1.29)


class FlagTest(unittest.TestCase):
    def test_clean_posting_has_no_flags(self):
        report = MODULE.analyze(posting())
        self.assertEqual(report["flags"], [])

    def test_high_deemed_overtime_is_flagged(self):
        report = MODULE.analyze(
            posting(
                compensation=compensation(
                    fixed_overtime={"included_in_range": True, "hours": 60, "annual_amount": 900000}
                )
            )
        )
        self.assertIn("fixed_overtime_hours_high", codes(report))

    def test_reference_hours_exactly_is_not_flagged(self):
        report = MODULE.analyze(
            posting(
                compensation=compensation(
                    fixed_overtime={"included_in_range": True, "hours": 45, "annual_amount": 700000}
                )
            )
        )
        self.assertNotIn("fixed_overtime_hours_high", codes(report))

    def test_wide_range_is_flagged(self):
        report = MODULE.analyze(posting(compensation=compensation(annual_max=7000000)))
        self.assertIn("pay_range_wide", codes(report))

    def test_discretionary_with_fixed_overtime_is_flagged(self):
        report = MODULE.analyze(
            posting(working_hours=working_hours(system="discretionary"))
        )
        self.assertIn("discretionary_with_fixed_overtime", codes(report))

    def test_estimated_pay_basis_is_flagged(self):
        report = MODULE.analyze(posting(compensation=compensation(basis="estimated")))
        self.assertIn("pay_basis_unconfirmed", codes(report))

    def test_incomplete_range_is_flagged(self):
        report = MODULE.analyze(posting(compensation=compensation(annual_max=None)))
        self.assertIn("pay_range_incomplete", codes(report))

    def test_unknown_bonus_treatment_is_flagged(self):
        report = MODULE.analyze(posting(compensation=compensation(bonus_included_in_range=None)))
        self.assertIn("bonus_treatment_unknown", codes(report))

    def test_missing_requirements_are_flagged(self):
        report = MODULE.analyze(posting(requirements=[]))
        self.assertIn("requirements_not_captured", codes(report))

    def test_all_vague_requirements_are_flagged(self):
        report = MODULE.analyze(
            posting(requirements=[{"text": "主体的に動ける方", "kind": "must", "user_status": "unknown"}])
        )
        self.assertIn("requirements_not_measurable", codes(report))


class RequirementTest(unittest.TestCase):
    def test_counts_are_split_by_kind_and_status(self):
        report = MODULE.analyze(
            posting(
                requirements=[
                    {"text": "A", "kind": "must", "user_status": "met", "measurable": True},
                    {"text": "B", "kind": "must", "user_status": "unmet"},
                    {"text": "C", "kind": "want", "user_status": "unknown"},
                ]
            )
        )
        self.assertEqual(report["requirement_counts"]["must"]["met"], 1)
        self.assertEqual(report["requirement_counts"]["must"]["unmet"], 1)
        self.assertEqual(report["requirement_counts"]["want"]["unknown"], 1)

    def test_unknown_is_not_folded_into_unmet(self):
        report = MODULE.analyze(
            posting(requirements=[{"text": "A", "kind": "must", "user_status": "unknown"}])
        )
        self.assertEqual(report["unmet_must_requirements"], [])
        self.assertEqual(report["unknown_requirement_count"], 1)

    def test_unmet_must_requirements_are_listed(self):
        report = MODULE.analyze(
            posting(requirements=[{"text": "AWS経験", "kind": "must", "user_status": "unmet"}])
        )
        self.assertEqual(report["unmet_must_requirements"], ["AWS経験"])


class ValidationTest(unittest.TestCase):
    def test_rejects_min_above_max(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(posting(compensation=compensation(annual_min=9000000)))

    def test_rejects_unknown_working_time_system(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(posting(working_hours=working_hours(system="whatever")))

    def test_rejects_unknown_requirement_kind(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(posting(requirements=[{"text": "A", "kind": "nice_to_have"}]))

    def test_rejects_unknown_user_status(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(posting(requirements=[{"text": "A", "user_status": "maybe"}]))

    def test_rejects_unknown_pay_basis(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(posting(compensation=compensation(basis="guessed")))

    def test_rejects_negative_pay(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(posting(compensation=compensation(annual_min=-1)))

    def test_rejects_missing_title(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(posting(title="  "))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(posting(), ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(
            json.loads(completed.stdout)["pay"]["base_annual_min_excluding_fixed_overtime"],
            3600000,
        )

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"title": ""}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
