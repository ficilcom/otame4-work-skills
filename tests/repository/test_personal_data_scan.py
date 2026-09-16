"""Regression coverage for the guard that keeps real personal data out of the repository."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _loader import load_script  # noqa: E402


MODULE = load_script("scripts/validate_skills.py")
ROOT = MODULE.ROOT


class PersonalDataScanTest(unittest.TestCase):
    def scan(self, text, name="__scan_probe__.md"):
        # scan_personal_data reports paths relative to ROOT, so the probe file has to
        # live inside the repository rather than in a temporary directory.
        target = ROOT / "skills" / name
        self.assertFalse(target.exists(), f"probe would overwrite {target}")
        try:
            target.write_text(text, encoding="utf-8")
            return MODULE.scan_personal_data(target)
        finally:
            target.unlink(missing_ok=True)

    def test_detects_phone_number_embedded_in_japanese_prose(self):
        """日本語の地の文に続く番号も検出する（\\b は日本語文字の境界にならない）。"""
        problems = self.scan("電話は03-1234-5678です。")
        self.assertTrue(problems)
        self.assertIn("phone number", problems[0])

    def test_detects_my_number_embedded_in_japanese_prose(self):
        problems = self.scan("番号は1234-5678-9012です。")
        self.assertTrue(problems)
        self.assertIn("12-digit number", problems[0])

    def test_detects_values_separated_by_ascii_whitespace(self):
        for text in ("call 03-1234-5678 now", "id 1234 5678 9012 end"):
            with self.subTest(text=text):
                self.assertTrue(self.scan(text))

    def test_allows_example_domain_addresses(self):
        self.assertEqual(self.scan("連絡先は taro@example.com です。"), [])

    def test_ignores_numbers_that_are_not_twelve_digits(self):
        for text in ("携帯は090-1234-5678です。", "売上は1200万円でした。", "連番は123456789012345です。"):
            with self.subTest(text=text):
                problems = [p for p in self.scan(text) if "12-digit" in p]
                self.assertEqual(problems, [])

    def test_skips_non_text_suffixes(self):
        self.assertEqual(self.scan("電話は03-1234-5678です。", name="__scan_probe__.png"), [])


if __name__ == "__main__":
    unittest.main()
