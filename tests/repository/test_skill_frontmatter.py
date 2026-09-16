"""Regression coverage for descriptions skipped by the skills CLI's YAML parser."""

import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _loader import load_script  # noqa: E402


MODULE = load_script("scripts/validate_skills.py")
ROOT = MODULE.ROOT


class DescriptionYamlTest(unittest.TestCase):
    def parse(self, description):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text(
                f"---\nname: sample-skill\ndescription: {description}\n---\n\n# 架空の検証用スキル\n",
                encoding="utf-8",
            )
            return MODULE.parse_frontmatter(path)

    def test_rejects_unquoted_colon_separator(self):
        for description in ("Review work: clarify scope.", "Review work:\tclarify scope.", "Review work:"):
            with self.subTest(description=description):
                _, problems = self.parse(description)
                self.assertTrue(problems)
                self.assertIn("must be quoted", " ".join(problems))

    def test_accepts_double_quoted_description_with_colon(self):
        fields, problems = self.parse('"Review work: clarify scope."')
        self.assertEqual(problems, [])
        self.assertEqual(fields["description"], "Review work: clarify scope.")

    def test_accepts_single_quoted_description_with_colon(self):
        fields, problems = self.parse("'Review work: clarify scope.'")
        self.assertEqual(problems, [])
        self.assertEqual(fields["description"], "Review work: clarify scope.")

    def test_accepts_plain_description_and_url(self):
        fields, problems = self.parse("Review work using https://example.com when planning a trial.")
        self.assertEqual(problems, [])
        self.assertIn("https://example.com", fields["description"])


if __name__ == "__main__":
    unittest.main()
