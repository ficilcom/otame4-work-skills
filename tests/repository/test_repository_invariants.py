"""Regression coverage for the repository-level checks in scripts/validate_skills.py."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _loader import load_script  # noqa: E402


MODULE = load_script("scripts/validate_skills.py")
ROOT = MODULE.ROOT


def skill_md(body):
    return f"---\nname: sample-skill\ndescription: Sample.\n---\n\n# 見出し\n\n{body}\n"


class BoundarySectionTest(unittest.TestCase):
    def test_accepts_a_section_that_promises_not_to_act(self):
        text = skill_md("## 個人情報と権限境界\n\nこのスキルは下書きのみを行う。応募の送信を自動実行しない。")
        self.assertEqual(MODULE.check_boundary_section(text), [])

    def test_accepts_the_trial_phrasing(self):
        text = skill_md("## 個人情報と権限境界\n\n掲載・応募・送信は利用者本人が行う。")
        self.assertEqual(MODULE.check_boundary_section(text), [])

    def test_rejects_a_missing_section(self):
        problems = MODULE.check_boundary_section(skill_md("## 判断上の制約\n\n順位は付けない。"))
        self.assertTrue(problems)
        self.assertIn("must contain", problems[0])

    def test_rejects_an_empty_section(self):
        problems = MODULE.check_boundary_section(skill_md("## 個人情報と権限境界\n"))
        self.assertTrue(problems)
        self.assertIn("must not be empty", problems[0])

    def test_rejects_a_section_without_the_promise(self):
        text = skill_md("## 個人情報と権限境界\n\n氏名や連絡先を必要以上に集めない。")
        problems = MODULE.check_boundary_section(text)
        self.assertTrue(problems)
        self.assertIn("does not act", problems[0])

    def test_every_shipped_skill_satisfies_the_invariant(self):
        for path in sorted((ROOT / "skills").glob("*/*/SKILL.md")):
            with self.subTest(skill=path.parent.name):
                problems = MODULE.check_boundary_section(path.read_text(encoding="utf-8"))
                self.assertEqual(problems, [], f"{path.parent.name}: {problems}")


class RegistryTest(unittest.TestCase):
    """スキル一覧を手で持っている場所が実体とズレたら落ちること。"""

    def run_with(self, readme=None, skills_sh=None, on_disk=(("career", "alpha"), ("career", "beta"))):
        original = (MODULE.README_FILE, MODULE.SKILLS_SH_FILE)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            if readme is not None:
                (base / "README.md").write_text(readme, encoding="utf-8")
                MODULE.README_FILE = base / "README.md"
            if skills_sh is not None:
                (base / "skills.sh.json").write_text(skills_sh, encoding="utf-8")
                MODULE.SKILLS_SH_FILE = base / "skills.sh.json"
            files = [base / category / name / "SKILL.md" for category, name in on_disk]
            try:
                return MODULE.validate_registries(files)
            finally:
                MODULE.README_FILE, MODULE.SKILLS_SH_FILE = original

    def test_accepts_a_listing_that_matches_disk(self):
        readme = "## 収録スキル\n\n| C | [`alpha`](skills/career/alpha/) | x |\n| C | [`beta`](skills/career/beta/) | y |\n\n## 次\n"
        config = json.dumps({"groupings": [{"skills": ["alpha", "beta"]}]})
        self.assertEqual(self.run_with(readme, config), [])

    def test_reports_a_skill_missing_from_the_readme(self):
        readme = "## 収録スキル\n\n| C | [`alpha`](skills/career/alpha/) | x |\n\n## 次\n"
        config = json.dumps({"groupings": [{"skills": ["alpha", "beta"]}]})
        problems = self.run_with(readme, config)
        self.assertEqual(len(problems), 1)
        self.assertIn("beta", problems[0])

    def test_reports_a_listing_that_points_at_nothing(self):
        readme = "## 収録スキル\n\n| C | [`alpha`](skills/career/alpha/) | x |\n| C | [`beta`](skills/career/beta/) | y |\n\n## 次\n"
        config = json.dumps({"groupings": [{"skills": ["alpha", "beta", "ghost"]}]})
        problems = self.run_with(readme, config)
        self.assertEqual(len(problems), 1)
        self.assertIn("ghost", problems[0])

    def test_reports_a_readme_link_pointing_at_the_wrong_category(self):
        """名前だけで比べると、スキルを別カテゴリへ移したときのリンク切れを見逃す。"""
        readme = "## 収録スキル\n\n| C | [`alpha`](skills/career/alpha/) | x |\n\n## 次\n"
        config = json.dumps({"groupings": [{"skills": ["alpha"]}]})
        problems = self.run_with(readme, config, on_disk=(("research", "alpha"),))
        self.assertEqual(len(problems), 1)
        self.assertIn("skills/research/alpha/", problems[0])

    def test_reports_a_missing_readme_section(self):
        readme = "# Title\n\nno listing here\n"
        config = json.dumps({"groupings": [{"skills": ["alpha", "beta"]}]})
        problems = self.run_with(readme, config)
        self.assertTrue(any("収録スキル" in p for p in problems))


class CategoryTest(unittest.TestCase):
    def test_categories_have_a_single_definition(self):
        new_skill = load_script("scripts/new_skill.py")
        self.assertEqual(MODULE.CATEGORIES, new_skill.CATEGORIES)

    def test_every_category_has_a_directory(self):
        for category in MODULE.CATEGORIES:
            with self.subTest(category=category):
                self.assertTrue((ROOT / "skills" / category).is_dir())


if __name__ == "__main__":
    unittest.main()
