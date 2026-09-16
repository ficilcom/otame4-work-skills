import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _loader import load_script, run_script, script_path  # noqa: E402


SCRIPT_PATH = "skills/documents/entry-sheet-review/scripts/check_entry_sheet.py"
SCRIPT = script_path(SCRIPT_PATH)
MODULE = load_script(SCRIPT_PATH)


def document(answer, **overrides):
    base = {
        "id": "q1",
        "question": "学生時代に力を入れたことを教えてください。",
        "limit_chars": 100,
        "answer": answer,
    }
    base.update(overrides)
    return base


def payload(*documents, **overrides):
    base = {"documents": list(documents)}
    base.update(overrides)
    return base


class CountCharactersTest(unittest.TestCase):
    def test_newlines_are_never_counted(self):
        counts = MODULE.count_characters("あい\nうえ\r\nお")
        self.assertEqual(counts["with_whitespace"], 5)

    def test_whitespace_rules_differ(self):
        counts = MODULE.count_characters("あ い　う")
        self.assertEqual(counts["with_whitespace"], 5)
        self.assertEqual(counts["without_whitespace"], 3)


class SentenceTest(unittest.TestCase):
    def test_splits_on_japanese_terminators_and_newlines(self):
        sentences = MODULE.split_sentences("一つ目です。二つ目ですか？\n三つ目")
        self.assertEqual(sentences, ["一つ目です。", "二つ目ですか？", "三つ目"])

    def test_long_sentence_is_reported(self):
        long_answer = "あ" * (MODULE.LONG_SENTENCE_CHARS + 1) + "。"
        result = MODULE.analyze_document(
            document(long_answer, limit_chars=None), 0, "with_whitespace"
        )
        self.assertEqual(len(result["sentences"]["long_sentences"]), 1)

    def test_sentence_at_threshold_is_not_reported(self):
        answer = "あ" * (MODULE.LONG_SENTENCE_CHARS - 1) + "。"
        result = MODULE.analyze_document(
            document(answer, limit_chars=None), 0, "with_whitespace"
        )
        self.assertEqual(result["sentences"]["long_sentences"], [])


class LengthStatusTest(unittest.TestCase):
    def test_over_limit_reports_negative_remaining(self):
        result = MODULE.analyze_document(document("あ" * 120), 0, "with_whitespace")
        self.assertEqual(result["length_status"], "over_limit")
        self.assertEqual(result["remaining_chars"], -20)

    def test_under_target_uses_default_ratio(self):
        result = MODULE.analyze_document(document("あ" * 50), 0, "with_whitespace")
        self.assertEqual(result["min_chars"], 80)
        self.assertEqual(result["length_status"], "under_target")

    def test_within_range_is_ok(self):
        result = MODULE.analyze_document(document("あ" * 90), 0, "with_whitespace")
        self.assertEqual(result["length_status"], "ok")

    def test_missing_limit_is_unknown_not_zero(self):
        result = MODULE.analyze_document(
            document("あ" * 90, limit_chars=None), 0, "with_whitespace"
        )
        self.assertEqual(result["length_status"], "unknown")
        self.assertIsNone(result["remaining_chars"])
        self.assertIsNone(result["min_chars"])

    def test_explicit_min_chars_overrides_default(self):
        result = MODULE.analyze_document(
            document("あ" * 50, min_chars=40), 0, "with_whitespace"
        )
        self.assertEqual(result["length_status"], "ok")


class SignalTest(unittest.TestCase):
    def test_missing_numbers_becomes_a_review_point(self):
        result = MODULE.analyze_document(document("あ" * 90), 0, "with_whitespace")
        self.assertIn(
            "数値による裏づけがない。規模・期間・成果を数で示せるか確認する",
            result["review_points"],
        )

    def test_numbers_are_counted_in_both_widths(self):
        result = MODULE.analyze_document(
            document("参加者を30人から５２人に増やした。" + "あ" * 70), 0, "with_whitespace"
        )
        self.assertEqual(result["numeric_token_count"], 2)

    def test_redundant_phrases_are_candidates_with_counts(self):
        result = MODULE.analyze_document(
            document("とても頑張ったと思います。とても学びました。" + "あ" * 70),
            0,
            "with_whitespace",
        )
        candidates = {item["phrase"]: item["count"] for item in result["redundant_phrase_candidates"]}
        self.assertEqual(candidates["とても"], 2)
        self.assertEqual(candidates["と思います"], 1)

    def test_contact_details_in_body_are_flagged(self):
        result = MODULE.analyze_document(
            document("連絡先は taro@example.com と 03-1234-5678 です。" + "あ" * 60),
            0,
            "with_whitespace",
        )
        found = {item["kind"]: item["count"] for item in result["personal_data_in_body"]}
        self.assertEqual(found, {"email": 1, "phone": 1})
        self.assertIn(
            "本文に個人情報が含まれている（メールアドレス、電話番号）。設問が求めていなければ削除する",
            result["review_points"],
        )

    def test_my_number_in_body_is_flagged(self):
        """12桁の数字はリポジトリ側ガードだけでなく利用者への報告でも検出する。"""
        digits = "1234 5678 9012"
        result = MODULE.analyze_document(
            document(f"番号は{digits}です。" + "あ" * 60), 0, "with_whitespace"
        )
        found = {item["kind"] for item in result["personal_data_in_body"]}
        self.assertIn("my_number", found)
        self.assertTrue(
            any("マイナンバー" in point for point in result["review_points"]),
            result["review_points"],
        )

    def test_personal_data_is_never_echoed_into_the_report(self):
        """検出した値そのものは報告に載せない（個人情報を出力しない方針）。"""
        secrets = ("taro@example.com", "03-1234-5678", "1234 5678 9012")
        answer = "連絡先は {} と {}、番号は {} です。".format(*secrets) + "あ" * 60
        result = MODULE.analyze_document(document(answer), 0, "with_whitespace")
        self.assertEqual(len(result["personal_data_in_body"]), 3)
        serialized = json.dumps(result, ensure_ascii=False)
        for secret in secrets:
            self.assertNotIn(secret, serialized)

    def test_answer_whitespace_is_preserved_for_counting(self):
        """_require_text は strip しない。前後の空白も提出時の文字数に含まれる。"""
        result = MODULE.analyze_document(
            document("  あいうえお  ", limit_chars=None), 0, "with_whitespace"
        )
        self.assertEqual(result["counts"]["with_whitespace"], 9)
        self.assertEqual(result["counts"]["without_whitespace"], 5)

    def test_paragraphs_are_split_on_blank_lines(self):
        result = MODULE.analyze_document(
            document("一段落目。\n\n二段落目。", limit_chars=None), 0, "with_whitespace"
        )
        self.assertEqual(result["paragraph_count"], 2)


class AnalyzeTest(unittest.TestCase):
    def test_summary_counts_each_status(self):
        report = MODULE.analyze(
            payload(
                document("あ" * 120, id="over"),
                document("あ" * 50, id="under"),
                document("あ" * 90, id="ok"),
                document("あ" * 90, id="unknown", limit_chars=None),
            )
        )
        self.assertEqual(report["over_limit_count"], 1)
        self.assertEqual(report["under_target_count"], 1)
        self.assertEqual(report["unknown_limit_count"], 1)
        self.assertEqual(report["document_count"], 4)

    def test_unconfirmed_count_rule_adds_a_note(self):
        report = MODULE.analyze(payload(document("あ" * 90)))
        self.assertEqual(len(report["notes"]), 1)

    def test_confirmed_count_rule_drops_the_note(self):
        report = MODULE.analyze(payload(document("あ" * 90), count_rule_confirmed=True))
        self.assertEqual(report["notes"], [])

    def test_without_whitespace_rule_changes_the_count(self):
        report = MODULE.analyze(
            payload(document("あ　" * 45), count_rule="without_whitespace")
        )
        self.assertEqual(report["documents"][0]["counted_chars"], 45)

    def test_rejects_unknown_count_rule(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(document("あ"), count_rule="bytes"))

    def test_rejects_empty_documents(self):
        with self.assertRaises(ValueError):
            MODULE.analyze({"documents": []})

    def test_rejects_min_chars_above_limit(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(document("あ", limit_chars=100, min_chars=200)))

    def test_rejects_non_string_answer(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(document(None)))

    def test_rejects_zero_limit(self):
        with self.assertRaises(ValueError):
            MODULE.analyze(payload(document("あ", limit_chars=0)))


class CommandLineTest(unittest.TestCase):
    def test_reads_a_file_and_prints_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(
                json.dumps(payload(document("あ" * 90)), ensure_ascii=False), encoding="utf-8"
            )
            completed = run_script(SCRIPT, argv=(str(path),))
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout)["document_count"], 1)

    def test_reads_stdin(self):
        completed = run_script(SCRIPT, payload(document("あ" * 90)))
        self.assertEqual(completed.returncode, 0)

    def test_invalid_json_exits_with_two(self):
        completed = run_script(SCRIPT, raw="{not json")
        self.assertEqual(completed.returncode, 2)

    def test_invalid_payload_exits_with_two(self):
        completed = run_script(SCRIPT, {"documents": []})
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
