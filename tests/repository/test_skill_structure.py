"""Coverage for the SKILL.md layout rules described in AGENTS.md「執筆」."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _loader import load_script  # noqa: E402


MODULE = load_script("scripts/validate_skills.py")

BODY = """# 架空の検証用スキル

架空の作業を整理する。合否の予測、経験の創作、応募の代行は行わない。

## 進め方

1. 架空の入力を確認する。
2. [まとめ方](references/report-format.md) に従って出す。

## 判断上の制約

- 架空の制約。

## 個人情報と権限境界

外部への連絡を自動実行しない。
"""


class SkillStructureTest(unittest.TestCase):
    def check(self, body, *, report_format=True, scripts=()):
        """組み立てたスキル一式を検査し、指摘の一覧を返す。"""
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory)
            path = skill / "SKILL.md"
            text = f"---\nname: sample-skill\ndescription: Sample.\n---\n\n{body}"
            path.write_text(text, encoding="utf-8")
            if report_format:
                references = skill / "references"
                references.mkdir()
                (references / "report-format.md").write_text("# まとめ方\n", encoding="utf-8")
            if scripts:
                script_dir = skill / "scripts"
                script_dir.mkdir()
                for name in scripts:
                    (script_dir / name).write_text("", encoding="utf-8")
            return MODULE.check_structure(path, text)

    def test_accepts_the_house_layout(self):
        self.assertEqual(self.check(BODY), [])

    def test_rejects_an_extra_section(self):
        body = BODY.replace("## 判断上の制約", "## 成果物\n\n表。\n\n## 判断上の制約")
        problems = self.check(body)
        self.assertTrue(problems)
        self.assertIn("exactly these sections in order", problems[0])

    def test_rejects_sections_out_of_order(self):
        body = BODY.replace(
            "## 進め方\n\n1. 架空の入力を確認する。\n2. [まとめ方](references/report-format.md) に従って出す。\n\n"
            "## 判断上の制約\n\n- 架空の制約。\n\n",
            "## 判断上の制約\n\n- 架空の制約。\n\n"
            "## 進め方\n\n1. 架空の入力を確認する。\n2. [まとめ方](references/report-format.md) に従って出す。\n\n",
        )
        problems = self.check(body)
        self.assertTrue(problems)
        self.assertIn("exactly these sections in order", problems[0])

    def test_rejects_an_opening_without_the_non_scope_sentence(self):
        body = BODY.replace(
            "架空の作業を整理する。合否の予測、経験の創作、応募の代行は行わない。",
            "架空の作業を整理する。利用者の判断材料を揃える。",
        )
        problems = self.check(body)
        self.assertTrue(problems)
        self.assertIn("what the skill does not do", problems[0])

    def test_accepts_an_opening_that_closes_with_dasanai(self):
        body = BODY.replace(
            "合否の予測、経験の創作、応募の代行は行わない。",
            "順位、総合点、推奨は出さない。",
        )
        self.assertEqual(self.check(body), [])

    def test_accepts_an_opening_whose_closing_sentence_is_emphasised(self):
        body = BODY.replace(
            "合否の予測、経験の創作、応募の代行は行わない。",
            "**合否の予測、経験の創作、応募の代行は行わない。**",
        )
        self.assertEqual(self.check(body), [])

    def test_requires_report_format_when_the_procedure_has_no_routing_table(self):
        problems = self.check(BODY, report_format=False)
        self.assertTrue(problems)
        self.assertIn("report-format.md is required", problems[0])

    def test_exempts_a_skill_that_routes_requests_to_per_stage_references(self):
        body = BODY.replace(
            "2. [まとめ方](references/report-format.md) に従って出す。",
            "2. 依頼に応じて必要な参照だけを読む。\n\n"
            "| 依頼 | 参照と成果物 |\n| --- | --- |\n"
            "| 架空の段階 | [架空の参照](references/stage.md)：成果物 |",
        )
        self.assertEqual(self.check(body, report_format=False), [])

    def test_requires_a_shipped_script_to_be_introduced_from_the_procedure(self):
        problems = self.check(BODY, scripts=("_common.py", "check_sample.py"))
        self.assertTrue(problems)
        self.assertIn("scripts/check_sample.py", problems[0])

    def test_ignores_the_vendored_common_module(self):
        self.assertEqual(self.check(BODY, scripts=("_common.py",)), [])

    def test_accepts_a_script_named_in_the_procedure(self):
        body = BODY.replace(
            "1. 架空の入力を確認する。",
            "1. `python3 scripts/check_sample.py <input.json>` で確認する。",
        )
        self.assertEqual(self.check(body, scripts=("_common.py", "check_sample.py")), [])


if __name__ == "__main__":
    unittest.main()
