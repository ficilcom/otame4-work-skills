import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/career/job-hunting-axis/scripts/check_axis.py"
SPEC = importlib.util.spec_from_file_location("check_axis", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def criterion(**overrides):
    base = {
        "id": "a1",
        "text": "入社3年目までに顧客と直接やりとりする",
        "kind": "must",
        "basis": "experience",
        "observable": ["面接で若手の担当範囲を聞く"],
    }
    base.update(overrides)
    return base


def avoid(**overrides):
    base = {
        "id": "a9",
        "text": "転居を伴う異動がある",
        "kind": "avoid",
        "basis": "experience",
        "observable": ["就業場所の変更の範囲"],
    }
    base.update(overrides)
    return base


def axis(**overrides):
    base = {
        "track": "shinsotsu",
        "criteria": [criterion(), avoid()],
        "tradeoffs": [],
        "candidates": [
            {
                "label": "架空A社",
                "assessment": [
                    {"criterion": "a1", "status": "met"},
                    {"criterion": "a9", "status": "unmet"},
                ],
            }
        ],
    }
    base.update(overrides)
    return base


def codes(report):
    return {flag["code"] for flag in report["flags"]}


def candidate(report, label):
    return next(entry for entry in report["candidates"] if entry["label"] == label)


class CheckabilityTest(unittest.TestCase):
    def test_a_criterion_with_a_way_to_check_raises_nothing(self):
        report = MODULE.check(axis())
        self.assertNotIn("no_way_to_check", codes(report))
        self.assertEqual(report["summary"]["with_way_to_check"], 2)

    def test_a_criterion_without_a_way_to_check_is_surfaced(self):
        report = MODULE.check(
            axis(criteria=[criterion(observable=[]), avoid()])
        )
        self.assertIn("no_way_to_check", codes(report))
        flag = next(f for f in report["flags"] if f["code"] == "no_way_to_check")
        self.assertEqual(flag["items"], ["a1"])

    def test_the_message_treats_it_as_unfinished_not_wrong(self):
        report = MODULE.check(axis(criteria=[criterion(observable=[]), avoid()]))
        flag = next(f for f in report["flags"] if f["code"] == "no_way_to_check")
        self.assertIn("確認できない基準では候補を選べない", flag["message"])


class BasisTest(unittest.TestCase):
    def test_an_assumption_is_surfaced_without_being_rejected(self):
        report = MODULE.check(axis(criteria=[criterion(basis="assumption"), avoid()]))
        flag = next(f for f in report["flags"] if f["code"] == "based_on_assumption")
        self.assertIn("捨てる必要はないが", flag["message"])

    def test_an_unstated_basis_is_separated_from_an_assumption(self):
        report = MODULE.check(
            axis(
                criteria=[
                    criterion(id="a1", basis="assumption"),
                    criterion(id="a2", basis="unknown"),
                    avoid(),
                ]
            )
        )
        self.assertIn("based_on_assumption", codes(report))
        self.assertIn("basis_unstated", codes(report))

    def test_basis_strength_is_summarised(self):
        report = MODULE.check(
            axis(criteria=[criterion(basis="observed"), avoid(basis="assumption")])
        )
        self.assertEqual(
            report["summary"]["basis_strength"], {"secondhand": 1, "untested": 1}
        )


class KindTest(unittest.TestCase):
    def test_missing_avoid_criteria_are_reported(self):
        report = MODULE.check(axis(criteria=[criterion()], candidates=[]))
        self.assertIn("no_avoid_criteria", codes(report))

    def test_all_must_is_reported_as_having_no_order_to_relax(self):
        report = MODULE.check(
            axis(
                criteria=[criterion(id="a1"), criterion(id="a2")],
                candidates=[],
            )
        )
        flag = next(f for f in report["flags"] if f["code"] == "everything_is_must")
        self.assertIn("何を緩めるかが決まらない", flag["message"])

    def test_a_mix_of_kinds_is_not_flagged(self):
        report = MODULE.check(
            axis(criteria=[criterion(id="a1"), criterion(id="a2", kind="want"), avoid()])
        )
        self.assertNotIn("everything_is_must", codes(report))


class TradeoffTest(unittest.TestCase):
    def test_two_conflicting_musts_are_flagged(self):
        report = MODULE.check(
            axis(
                criteria=[criterion(id="a1"), criterion(id="a2"), avoid()],
                tradeoffs=[{"pair": ["a1", "a2"], "note": "両立しにくい"}],
                candidates=[],
            )
        )
        self.assertIn("conflicting_musts", codes(report))

    def test_a_tradeoff_with_a_want_is_not_flagged(self):
        report = MODULE.check(
            axis(
                criteria=[criterion(id="a1"), criterion(id="a2", kind="want"), avoid()],
                tradeoffs=[{"pair": ["a1", "a2"]}],
                candidates=[],
            )
        )
        self.assertNotIn("conflicting_musts", codes(report))

    def test_rejects_a_tradeoff_naming_an_unknown_criterion(self):
        with self.assertRaises(ValueError):
            MODULE.check(axis(tradeoffs=[{"pair": ["a1", "zz"]}]))

    def test_rejects_a_tradeoff_with_a_single_criterion(self):
        with self.assertRaises(ValueError):
            MODULE.check(axis(tradeoffs=[{"pair": ["a1", "a1"]}]))


class CandidateTest(unittest.TestCase):
    def test_unassessed_criteria_default_to_unknown(self):
        report = MODULE.check(
            axis(candidates=[{"label": "架空A社", "assessment": []}])
        )
        self.assertEqual(candidate(report, "架空A社")["unknown_ratio"], 1.0)
        self.assertIn("candidate_mostly_unchecked", codes(report))

    def test_unknown_is_not_counted_as_unmet(self):
        report = MODULE.check(
            axis(candidates=[{"label": "架空A社", "assessment": []}])
        )
        self.assertEqual(candidate(report, "架空A社")["unmet_must"], [])

    def test_an_unmet_must_is_listed(self):
        report = MODULE.check(
            axis(
                candidates=[
                    {"label": "架空A社", "assessment": [{"criterion": "a1", "status": "unmet"}]}
                ]
            )
        )
        self.assertEqual(candidate(report, "架空A社")["unmet_must"], ["a1"])

    def test_matching_an_avoid_criterion_is_surfaced_without_excluding(self):
        report = MODULE.check(
            axis(
                candidates=[
                    {"label": "架空A社", "assessment": [{"criterion": "a9", "status": "met"}]}
                ]
            )
        )
        self.assertEqual(candidate(report, "架空A社")["matches_avoid"], ["a9"])
        flag = next(f for f in report["flags"] if f["code"] == "candidate_matches_avoid")
        self.assertIn("自分で決める", flag["message"])

    def test_no_candidates_is_reported(self):
        report = MODULE.check(axis(candidates=[]))
        self.assertIn("no_candidates", codes(report))

    def test_rejects_an_assessment_of_an_unknown_criterion(self):
        with self.assertRaises(ValueError):
            MODULE.check(
                axis(candidates=[{"label": "架空A社", "assessment": [{"criterion": "zz"}]}])
            )


class OutputContractTest(unittest.TestCase):
    def test_output_carries_no_fit_score_or_ranking(self):
        serialized = json.dumps(MODULE.check(axis()), ensure_ascii=False)
        for forbidden in ("score", "rank", "fit", "recommend", "best_match"):
            self.assertNotIn(forbidden, serialized)

    def test_notes_state_that_unknown_is_not_a_mismatch(self):
        report = MODULE.check(axis())
        self.assertTrue(any("未確認は不適合ではない" in note for note in report["notes"]))

    def test_an_empty_axis_says_so(self):
        report = MODULE.check({"criteria": []})
        self.assertEqual(codes(report), {"criteria_not_captured"})


class InputValidationTest(unittest.TestCase):
    def test_rejects_duplicate_criterion_ids(self):
        with self.assertRaises(ValueError):
            MODULE.check(axis(criteria=[criterion(), criterion()]))

    def test_rejects_duplicate_candidate_labels(self):
        with self.assertRaises(ValueError):
            MODULE.check(
                axis(
                    candidates=[
                        {"label": "架空A社", "assessment": []},
                        {"label": "架空A社", "assessment": []},
                    ]
                )
            )

    def test_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            MODULE.check(axis(criteria=[criterion(kind="nice")]))

    def test_rejects_unknown_basis(self):
        with self.assertRaises(ValueError):
            MODULE.check(axis(criteria=[criterion(basis="intuition")]))

    def test_rejects_unknown_track(self):
        with self.assertRaises(ValueError):
            MODULE.check(axis(track="part_time"))


class CommandLineTest(unittest.TestCase):
    def test_stdin_round_trip(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(axis(), ensure_ascii=False),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["summary"]["criteria"], 2)

    def test_invalid_payload_exits_with_two(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps({"criteria": [{"id": "a1"}]}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
