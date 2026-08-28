# Otame4 Work Skills

日本の就職活動と転職のための [Agent Skills](https://agentskills.io/) 集。自己分析、エントリーシート・履歴書・職務経歴書の添削、面接対策、企業研究、内定の判断までを扱う。

各スキルは単独でインストールでき、オープンな Agent Skills 仕様に従う。求職者本人が自分の Claude に入れて使うことを前提にしている。

> **English** — A collection of Agent Skills for the Japanese job market: entry sheets (ES), rirekisho and shokumu-keirekisho review, interview preparation, company research, and offer decisions. Skill bodies, references, and report templates are written in Japanese; only the `SKILL.md` frontmatter is English so agents can discover them.

## インストール

すべてのスキルを一覧してから選ぶ:

```bash
npx skills add ficilcom/otame4-work-skills --list
```

1つだけ入れる:

```bash
npx skills add ficilcom/otame4-work-skills --skill entry-sheet-review
```

Claude Code のプラグインとしてまとめて入れる:

```bash
claude plugin marketplace add ficilcom/otame4-work-skills
```

手で入れる場合は、スキルのディレクトリを `~/.claude/skills/<skill-name>/` にコピーする。

## 対象範囲

- 自己分析と就活・転職の軸づくり、転職するかどうかの意思決定
- エントリーシート、履歴書、職務経歴書の作成と添削
- 面接・面談の準備と振り返り
- 業界・企業研究、求人票の読み解き
- 内定・オファーの比較、条件確認、退職と入社の準備

一般論のキャリア論ではなく、具体的な判断と、そのまま使える成果物を出すことを優先する。

## 収録スキル

| カテゴリ | スキル | 概要 |
| --- | --- | --- |
| Documents | [`entry-sheet-review`](skills/documents/entry-sheet-review/) | ES・履歴書・職務経歴書を、設問適合・事実の裏づけ・文字数の3点に分けて確認し、利用者が選べる改稿案を出す。 |

## 共通の制約

どのスキルも次を守る。あなたの判断を代行しない。

- 経験、実績、数値、資格を創作しない。原稿とあなたの発言にないことは書かない。
- 合否、通過率、内定確率を予測しない。
- 応募の送信、企業・採用担当者への連絡、求人サイトや ATS の更新、面接日程の確定、退職の意思表示を自動実行しない。実行の直前に必ず承認を求める。
- 労働法・税務・社会保険の判断を専門家の確定判断として示さない。
- 作業に必要のない個人情報を収集・保存・出力しない。

## リポジトリ構成

```text
otame4-work-skills/
├── .claude-plugin/
│   └── marketplace.json      # スキル追加時に必ず更新する
├── skills/
│   ├── career/
│   ├── documents/
│   │   └── <skill-name>/
│   │       ├── SKILL.md      # 必須
│   │       ├── scripts/      # 決定的な補助スクリプト（任意）
│   │       ├── references/   # 必要時に読む詳細（任意）
│   │       └── assets/       # 出力雛形（任意）
│   ├── interview/
│   ├── research/
│   └── offer/
├── scripts/
│   ├── new_skill.py
│   ├── run_tests.py
│   └── validate_skills.py
└── tests/
    └── <category>/
        └── <skill-name>/
            └── test_*.py
```

スキルディレクトリはカテゴリの1階層下に置く。ディレクトリ名と `SKILL.md` の `name` は一致させる。

| カテゴリ | 範囲 |
| --- | --- |
| `career` | 自己分析、就活・転職の軸、キャリア設計、転職の意思決定 |
| `documents` | ES、履歴書、職務経歴書、ポートフォリオの作成と添削 |
| `interview` | 面接・面談対策、想定質問、逆質問、振り返り |
| `research` | 業界・企業研究、求人票の読み解き、応募先の選定 |
| `offer` | 内定・オファー比較、条件確認、退職と入社準備 |

## 開発

新しいスキルの雛形を作る:

```bash
python3 scripts/new_skill.py interview interview-question-prep
```

変更したら検証する:

```bash
python3 scripts/validate_skills.py && python3 scripts/run_tests.py
```

検証内容: フロントマターの必須項目、名前とディレクトリの一致、`PLACEHOLDER`/`TODO` の残留、`marketplace.json` との整合、そして**個人情報らしき文字列（メールアドレス、電話番号、12桁数字）の混入**。公開リポジトリなので、実在する求職者の応募書類やサンプルは絶対にコミットしない。

書き方の基準は [CONTRIBUTING.md](CONTRIBUTING.md)、リポジトリ運用は [AGENTS.md](AGENTS.md) を読む。

## ライセンス

[MIT](LICENSE)
