import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/offer/offer-comparison/scripts/compare_offers.py"
SPEC = importlib.util.spec_from_file_location("compare_offers", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def components(**overrides):
    base = {
        "monthly_base": 300000,
        "fixed_allowances_monthly": 20000,
        "fixed_overtime": {"monthly_amount": 60000, "hours": 30, "included_in_annual": True},
        "bonus": {"annual_amount": 840000, "guaranteed": False, "included_in_annual": True},
    }
    base.update(overrides)
    return base


def one_offer(label="A社", **overrides):
    base = {
        "label": label,
        "employment_type": "正社員",
        "compensation": {
            "basis": "written_notice",
            "annual_total": 5400000,
            "components": components(),
        },
        "working_hours": {"daily_scheduled_hours": 8, "monthly_working_days": 20},
        "other": {"commute_allowance_monthly": 15000, "housing_support_monthly": 20000},
    }
    base.update(overrides)
    return base


def other_offer(label="B社", **overrides):
    base = {
        "label": label,
        "employment_type": "正社員",
        "compensation": {
            "basis": "offer_letter",
            "annual_total": 5200000,
            "components": components(
                monthly_base=380000,
                fixed_allowances_monthly=0,
                fixed_overtime={"monthly_amount": 0, "hours": 0, "included_in_annual": True},
                bonus={"annual_amount": 640000, "guaranteed": True, "included_in_annual": True},
            ),
        },
        "working_hours": {"monthly_scheduled_hours": 155},
        "other": {},
    }
    base.update(overrides)
    return base


def payload(*offers):
    return {"as_of": "2026-09-01", "offers": list(offers) or [one_offer(), other_offer()]}


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def figures(report, label):
    return next(entry for entry in report["offers"] if entry["label"] == label)


def metric(report, key):
    return next(entry for entry in report["metrics"] if entry["key"] == key)


class DecompositionTest(unittest.TestCase):
    def test_base_annual_excludes_fixed_overtime_and_bonus(self):
        report = MODULE.compare(payload())
        self.assertEqual(figures(report, "A社")["figures"]["base_annual"], 3840000)

    def test_guaranteed_annual_drops_an_unguaranteed_bonus(self):
        report = MODULE.compare(payload())
        self.assertEqual(figures(report, "A社")["figures"]["guaranteed_annual"], 4560000)

    def test_guaranteed_annual_keeps_a_guaranteed_bonus(self):
        report = MODULE.compare(payload())
        self.assertEqual(figures(report, "B社")["figures"]["guaranteed_annual"], 5200000)

    def test_guaranteed_annual_is_withheld_when_the_bonus_guarantee_is_unknown(self):
        offer = one_offer()
        offer["compensation"]["components"]["bonus"] = {
            "annual_amount": 840000,
            "included_in_annual": True,
        }
        report = MODULE.compare(payload(offer, other_offer()))
        self.assertIsNone(figures(report, "A社")["figures"]["guaranteed_annual"])
        self.assertIn("bonus_guarantee_unknown", codes(report))

    def test_hourly_rate_includes_deemed_overtime_hours(self):
        report = MODULE.compare(payload())
        self.assertEqual(figures(report, "A社")["assumed_annual_hours"], 2280.0)
        self.assertEqual(figures(report, "A社")["hourly_guaranteed"], 2000)

    def test_ranking_can_invert_once_components_are_separated(self):
        report = MODULE.compare(payload())
        stated = metric(report, "stated_annual")["values"]
        guaranteed = metric(report, "guaranteed_annual")["values"]
        self.assertGreater(stated["A社"], stated["B社"])
        self.assertLess(guaranteed["A社"], guaranteed["B社"])

    def test_report_carries_no_ranking_or_score(self):
        report = MODULE.compare(payload())
        serialized = json.dumps(report, ensure_ascii=False)
        for forbidden in ("score", "rank", "recommend", "winner", "best"):
            self.assertNotIn(forbidden, serialized)


class MissingDataTest(unittest.TestCase):
    def test_metric_is_not_comparable_when_an_offer_lacks_the_figure(self):
        offer = other_offer()
        offer["working_hours"] = {}
        report = MODULE.compare(payload(one_offer(), offer))
        self.assertFalse(metric(report, "hourly_stated")["comparable"])
        self.assertEqual(metric(report, "hourly_stated")["missing"], ["B社"])
        self.assertIn("working_hours_unknown", codes(report))

    def test_undisclosed_fixed_overtime_is_flagged_rather_than_assumed_zero(self):
        offer = other_offer()
        del offer["compensation"]["components"]["fixed_overtime"]
        report = MODULE.compare(payload(one_offer(), offer))
        self.assertIsNone(figures(report, "B社")["figures"]["fixed_overtime_annual"])
        self.assertIn("fixed_overtime_undisclosed", codes(report))

    def test_not_comparable_lists_the_dropped_metrics(self):
        offer = other_offer()
        offer["compensation"]["components"]["monthly_base"] = None
        report = MODULE.compare(payload(one_offer(), offer))
        dropped = {entry["key"] for entry in report["not_comparable"]}
        self.assertIn("base_annual", dropped)
        self.assertIn("guaranteed_annual", dropped)


class ReconciliationTest(unittest.TestCase):
    def test_components_matching_the_stated_annual_are_within_tolerance(self):
        report = MODULE.compare(payload())
        self.assertTrue(figures(report, "A社")["reconcile"]["within_tolerance"])
        self.assertNotIn("stated_annual_does_not_reconcile", codes(report))

    def test_components_that_do_not_add_up_are_flagged_with_the_difference(self):
        offer = one_offer()
        offer["compensation"]["annual_total"] = 6000000
        report = MODULE.compare(payload(offer, other_offer()))
        self.assertEqual(figures(report, "A社")["reconcile"]["difference"], -600000)
        self.assertIn("stated_annual_does_not_reconcile", codes(report))

    def test_reconciliation_is_skipped_when_inclusion_is_unknown(self):
        offer = one_offer()
        offer["compensation"]["components"]["fixed_overtime"] = {
            "monthly_amount": 60000,
            "hours": 30,
        }
        report = MODULE.compare(payload(offer, other_offer()))
        self.assertIsNone(figures(report, "A社")["reconcile"])


class FlagTest(unittest.TestCase):
    def test_unwritten_basis_is_flagged(self):
        offer = other_offer()
        offer["compensation"]["basis"] = "verbal"
        report = MODULE.compare(payload(one_offer(), offer))
        self.assertIn("basis_not_written", codes(report))
        self.assertFalse(figures(report, "B社")["basis_is_written"])

    def test_performance_bonus_inside_the_stated_annual_is_flagged(self):
        report = MODULE.compare(payload())
        self.assertIn("performance_bonus_in_stated_annual", codes(report))

    def test_long_deemed_overtime_is_flagged(self):
        offer = one_offer()
        offer["compensation"]["components"]["fixed_overtime"] = {
            "monthly_amount": 120000,
            "hours": 60,
            "included_in_annual": True,
        }
        report = MODULE.compare(payload(offer, other_offer()))
        self.assertIn("fixed_overtime_hours_high", codes(report))

    def test_mixed_employment_types_are_flagged(self):
        offer = other_offer()
        offer["employment_type"] = "契約社員"
        report = MODULE.compare(payload(one_offer(), offer))
        self.assertIn("employment_types_differ", codes(report))

    def test_a_single_offer_is_flagged_as_not_a_comparison(self):
        report = MODULE.compare(payload(one_offer()))
        self.assertIn("single_offer", codes(report))
        self.assertFalse(metric(report, "stated_annual")["comparable"])


class InputValidationTest(unittest.TestCase):
    def test_rejects_duplicate_labels(self):
        with self.assertRaises(ValueError):
            MODULE.compare(payload(one_offer(), one_offer()))

    def test_rejects_empty_offer_list(self):
        with self.assertRaises(ValueError):
            MODULE.compare({"offers": []})

    def test_rejects_unknown_basis(self):
        offer = one_offer()
        offer["compensation"]["basis"] = "hearsay"
        with self.assertRaises(ValueError):
            MODULE.compare(payload(offer, other_offer()))

    def test_rejects_negative_amounts(self):
        offer = one_offer()
        offer["compensation"]["components"]["monthly_base"] = -1
        with self.assertRaises(ValueError):
            MODULE.compare(payload(offer, other_offer()))

    def test_rejects_missing_label(self):
        with self.assertRaises(ValueError):
            MODULE.compare(payload(one_offer(label="  "), other_offer()))


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
        report = json.loads(completed.stdout)
        self.assertEqual(len(report["offers"]), 2)

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"offers": [{"label": ""}]}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
