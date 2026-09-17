# Otame4 Work Skills — 就活・転職・採用のAIスキル

日本の就職活動と転職のための [Agent Skills](https://agentskills.io/) 集。自己分析、エントリーシート・履歴書・職務経歴書の添削、面接対策、企業研究、内定の判断、おためし転職の体験準備、企業側の業務設計・募集文・社内説明・応募者対応・契約条件・振り返り、副業の可否と案件条件の確認までを扱う。

各スキルは単独でインストールでき、オープンな Agent Skills 仕様に従う。求職者本人が自分の Claude に入れて使うことを前提にしている。`employer` カテゴリは求人企業向けで、専任の採用担当者、現場のマネージャー、小規模企業の経営者のいずれからでも使える。立場ごとにカテゴリが分かれている。

> **English** — A collection of Agent Skills for the Japanese job market: entry sheets (ES), rirekisho and shokumu-keirekisho review, interview preparation, company research, offer decisions, Otameshi Tenshoku trial planning for candidates, the employer side of a trial (work design, listing, budget case, applicant replies, gyomu-itaku terms, feedback), and side-work checks covering an employer's own rules and the terms of a gyomu-itaku assignment. Skill bodies, references, and report templates are written in Japanese; only the `SKILL.md` frontmatter is English so agents can discover them.

**Claude Codeで、応募書類・面接・求人票・おためし転職・採用側の募集・副業の相談を具体的な原稿や計画に。** 求人や経験のメモから必要なところに着手でき、特別な入力形式は不要です。

| やりたいこと | 最初に使うSkill | 得られるもの |
| --- | --- | --- |
| ES・履歴書・職務経歴書を添削したい | [`entry-sheet-review`](skills/documents/entry-sheet-review/SKILL.md) | 事実と設問に沿った改稿案 |
| おためし転職に応募・参加したい | [`otameshi-candidate`](skills/trial/otameshi-candidate/SKILL.md) | 応募文、確認質問、体験計画 |
| 企業として任せる仕事と費用を決めたい | [`trial-work-design`](skills/employer/trial-work-design/SKILL.md) | 範囲、実働、期間、報酬、予算との差 |
| 企業として募集文を出したい・点検したい | [`trial-listing-draft`](skills/employer/trial-listing-draft/SKILL.md) | 必須項目の点検、表現の直し、掲載用の下書き |
| 副業を始めてよいか確認したい | [`sidework-rules-check`](skills/sidework/sidework-rules-check/SKILL.md) | 規定の確認表、会社への質問、申請材料 |

[インストールする](#install) · [全スキルを見る](#収録スキル) · [skills.shで探す](https://skills.sh/ficilcom/otame4-work-skills)

<a id="install"></a>

## インストール

Claude Codeでは、Node.jsの `npx` が使えるターミナルで実行します。以下の `-g` は自分の環境全体に、`-a claude-code` はClaude Codeを対象に入れる指定です。

**求職者：おためし転職の応募・体験準備**

```bash
npx skills add ficilcom/otame4-work-skills --skill otameshi-candidate -a claude-code -g
```

**企業：募集文の作成と掲載前の点検**

```bash
npx skills add ficilcom/otame4-work-skills --skill trial-listing-draft -a claude-code -g
```

**企業：任せる仕事の範囲・実働・報酬・予算の設計**

```bash
npx skills add ficilcom/otame4-work-skills --skill trial-work-design -a claude-code -g
```

**応募書類の作成・添削から始める**

```bash
npx skills add ficilcom/otame4-work-skills --skill entry-sheet-review -a claude-code -g
```

**副業：就業規則の確認から案件の条件確認まで**

```bash
npx skills add ficilcom/otame4-work-skills --skill sidework-rules-check -a claude-code -g
```

インストール後、Claude Codeで新しい会話を始め、「おためし転職の応募文を作って」「予算内に収まる体験業務を設計して」「この募集文で応募が来ない理由を見て」「このESを添削して」のように依頼します。名前で指定する場合は「otameshi-candidateを使って」のように伝えます。

すべてのスキルを一覧してから選ぶ:

```bash
npx skills add ficilcom/otame4-work-skills --list
```

1つだけ入れる:

```bash
npx skills add ficilcom/otame4-work-skills --skill company-research
```

Claude Codeのプラグインでは、まずカタログを追加し、続けて使いたいプラグインをインストールします。企業向けの6スキルをまとめて入れる場合:

```bash
claude plugin marketplace add ficilcom/otame4-work-skills
claude plugin install otame4-employer@otame4-work-skills
```

カタログ追加だけではスキルはインストールされません。求職者向けのおためし転職は `otame4-trial`、ほかのカテゴリは `otame4-career`、`otame4-documents`、`otame4-research`、`otame4-interview`、`otame4-offer`、`otame4-sidework` を選べます。

手で入れる場合は、スキルのディレクトリを `~/.claude/skills/<skill-name>/` にコピーする。

## 対象範囲

- 自己分析と就活・転職の軸づくり、転職するかどうかの相談、次の仕事・職種の探索
- エントリーシート、履歴書、職務経歴書の作成と添削
- 面接・面談の準備と振り返り
- 業界・企業研究、求人票の読み解き
- 内定・オファーの比較、条件確認、退職と入社の準備
- おためし転職の応募、見学・学習の無償体験と有償業務の準備、体験後の判断（求職者）
- おためし転職の受け入れ：任せる仕事の設計、募集文、社内の予算説明、応募者への返信、業務委託の条件明示、振り返りとフィードバック（企業）
- 副業の可否と申請・届出の確認、業務委託で受ける案件の取引条件と報酬の確認

一般論のキャリア論ではなく、具体的な判断と、そのまま使える成果物を出すことを優先する。

## 収録スキル

| カテゴリ | スキル | 概要 |
| --- | --- | --- |
| Career | [`job-hunting-axis`](skills/career/job-hunting-axis/) | 「成長できる環境」のような言葉を、何を見れば確認できるかが決まった基準に変える。想像に基づく軸と経験に基づく軸を分け、両立しにくい必須の組み合わせを出す。順位は付けない。 |
| Career | [`career-inventory`](skills/career/career-inventory/) | 書類を書く前に経験を事実として洗い出す。状況・自分の行動・結果・役割に分け、各主張が何に基づくか（公開情報・手元の資料・当時を知る人・記憶だけ）を記録する。強みや適性は判定しない。 |
| Career | [`job-change-decision`](skills/career/job-change-decision/) | 「辞めたい」「このままでいいのか」という迷いから対話し、変えたいこと・守りたいことを整理する。条件付きの見立てと小さな次の行動、見直す時期まで考え、最終判断は本人に残す。 |
| Career | [`career-options`](skills/career/career-options/) | 本人が実際にした作業から次の仕事の候補を作り、経験との接点・未確認の業務や要件・小さな試し方を示す。適職の診断や採用見込みの予測はしない。 |
| Documents | [`entry-sheet-review`](skills/documents/entry-sheet-review/) | ES・履歴書・職務経歴書を、設問適合・事実の裏づけ・文字数の3点に分けて確認し、利用者が選べる改稿案を出す。 |
| Research | [`company-research`](skills/research/company-research/) | 応募先を一次情報・公式情報から調べ、すべての事実に出典と時点を付ける。口コミやまとめ記事は事実にせず、面接で確認する論点として残す。 |
| Research | [`job-posting-analysis`](skills/research/job-posting-analysis/) | 求人票の提示年収から固定残業代を分離し、みなし残業込みの時給に換算する。要件の充足状況と、確認すべき曖昧な条件を出す。 |
| Research | [`scout-message-triage`](skills/research/scout-message-triage/) | スカウトを文面の熱意ではなく開示されている事実で仕分ける。企業名の有無、欠けている条件、「最大」「可能」の年収表現、同一企業の経路重複を出す。求人の評価はしない。 |
| Interview | [`interview-prep`](skills/interview/interview-prep/) | 提出済みの書類から深掘りされる箇所（裏づけのない主張、主語がチームの記述、職歴の空白、書類が答えていない必須要件）を洗い出し、示す事実を詰める。合否は予測しない。 |
| Interview | [`interview-debrief`](skills/interview/interview-debrief/) | 終わった面接を、答えきれなかった質問の原因別（書類のずれ・順序の問題・準備漏れ）、未解決の逆質問、口頭のみの条件に整理する。手応えも合否も評価しない。 |
| Offer | [`offer-terms-check`](skills/offer/offer-terms-check/) | 内定条件が書面で明示されているかを項目ごとに確認し、求人票・面接での説明との食い違いと、承諾期限までに確認すべきことを出す。 |
| Offer | [`offer-comparison`](skills/offer/offer-comparison/) | 複数の内定を同じ基準に揃える。提示年収から固定残業代と保証のない賞与を分離し、変動しない年額とみなし残業込みの時給で並べる。順位も総合点も出さない。 |
| Offer | [`offer-decline`](skills/offer/offer-decline/) | 受ける先が書面で確定しているかを確認したうえで、辞退の段階（選考途中・内定後・承諾後）と経路（エージェント・学校推薦・紹介）ごとに誰へ伝えるかを整理する。辞退の可否は判断しない。 |
| Offer | [`resignation-plan`](skills/offer/resignation-plan/) | 退職の申出日・退職日・入社日を就業規則の定めと突き合わせ、有給の消化、引き継ぎ、書類の受け渡し、空白期間に発生する手続きを整理する。退職の可否は判断しない。 |
| Trial | [`otameshi-candidate`](skills/trial/otameshi-candidate/) | 求職者向け。応募文、体験前の確認質問、学習体験・有償業務の計画、体験後の判断材料を作る。有償業務では実働・期間・予定額・換算時給を揃え、未経験でも企業の実務は有償枠を提案する。 |
| Employer | [`trial-work-design`](skills/employer/trial-work-design/) | 企業向け。課題を、候補者が期間内に完結できる有償業務か未経験者向けの無償の見学・学習に変え、範囲・完了基準・実働・企業の工数・期間・報酬・変更条件を揃える。予定費用を予算と突き合わせ、企業の実務は経験にかかわらず有償枠にする。 |
| Employer | [`trial-listing-draft`](skills/employer/trial-listing-draft/) | 企業向け。募集文を、候補者が応募を判断できる項目（作業、成果物、対象外、経験、支援、時間、場所、報酬、契約形態、支払時期）で点検し、範囲の閉じていない表現・無償の実務・採用の保証・職務と無関係な属性を直す。実働・期間・単価・予算が同時に成立するかを確かめ、内部検討用と掲載用の下書きを分ける。 |
| Employer | [`trial-budget-brief`](skills/employer/trial-budget-brief/) | 企業向け。受け入れの社内説明。候補者への支払い、担当者の工数、掲載料などを分けて合計し、現金の額と社内工数込みの額を予算と突き合わせる。採用に至らなかった場合に残るもの、止める条件、判断者と期限を揃える。採用の見込みや相場を根拠にしない。 |
| Employer | [`applicant-reply`](skills/employer/applicant-reply/) | 企業向け。募集の要件と応募内容を、応募者が述べたことで照合し、確認質問を出して、招待・質問・保留・辞退の返信を作る。推測を根拠にせず、職務と無関係な属性で選別せず、他候補者の情報と内部メモを混ぜず、募集文にない条件は提案として書く。 |
| Employer | [`trial-contract-terms`](skills/employer/trial-contract-terms/) | 企業向け。業務委託で有償業務を発注する前に、給付の内容、受領期日、報酬、支払期日、支払主体、範囲外、修正の上限、支援、権利、秘密保持、中途解除が書面で示されているかを項目ごとに確認し、受領から支払期日までの日数を出す。成果への満足を支払いの条件にする定めや企業側だけの解除を直す。適法性は判定しない。 |
| Employer | [`trial-feedback`](skills/employer/trial-feedback/) | 企業向け。終わった体験を、事前に合意した基準と観察事実、後から足した期待、企業の支援の遅れ、実施済みの実働に対する精算に分けて整理し、候補者へのフィードバック案と担当者用メモを分けて作る。適性の判定、満足度を理由にした減額、決めていない採用・継続の通知はしない。 |
| Sidework | [`sidework-rules-check`](skills/sidework/sidework-rules-check/) | 就業規則・雇用契約・誓約書のどこに何が書かれているかを根拠付きで確認し、禁止・許可制・届出制を区別する。競業、秘密保持、職務専念、設備の利用のうち触れうるものを出し、本業と合わせた週の稼働を合算する。可否の結論も規定の適法性も判定しない。 |
| Sidework | [`sidework-terms-check`](skills/sidework/sidework-terms-check/) | 業務委託で受ける案件の取引条件が書面で明示されているかを項目ごとに確認する。打合せ・修正・無償の作業を含めた総稼働で報酬を割った換算時給と、納品から支払期日までの日数を出す。相場の評価も受諾の判断もしない。 |

## おためし転職の使い方

求職者は `otameshi-candidate` を使います。企業側は段階ごとにスキルが分かれています。[インストール手順](#install)から、自分の立場と段階に合うものを選んでください。

| 企業の段階 | スキル |
| --- | --- |
| 任せる仕事と費用を決める | `trial-work-design` |
| 募集文を書く・掲載前に点検する | `trial-listing-draft` |
| 社内で予算・受け入れを通す | `trial-budget-brief` |
| 応募者に返信する | `applicant-reply` |
| 開始前に契約条件を書面で示す | `trial-contract-terms` |
| 体験後に振り返り、フィードバックを送る | `trial-feedback` |

- 求職者：「週末しか動けません。この求人に応募する前に確認することと、応募文を作って」
- 企業：「記事改善を経験者にお願いしたい。予算と週の稼働に収まる仕事量と期間を作って」
- 企業：「この募集文に2週間応募が来ない。候補者の目で足りないところを点検して」
- 企業：「部長に出す稟議用に、候補者への支払いと担当者の工数を分けた費用と、採用しなくても残るものをまとめて」

未経験の分野には見学・学習・模擬課題の無償体験を候補にし、経験を活かす仕事は有償枠を提案する。企業の実務を担う場合は未経験でも有償枠にする。無償体験の掲載可否と活動の扱いは必要時に公式情報で確認する。有償業務は説明・会議・修正まで見積もり、実働時間と実施期間を分ける。

どのスキルも相談・原稿作成・運用準備まで。掲載・応募・返信・日程確定・契約・支払いなどの操作は本人が行う。企業向けでは、成果への満足や採用判断を支払いの条件にする定めや、職務と無関係な属性による選別を作らない。入力や原稿は、利用者が明示的に求めない限りファイルに残さない。

## Web 検索・ページ取得について

`company-research` は公開情報を取りに行く。`career-options` も、候補の仕事内容や要件を具体的に確かめるときに公開情報を参照する。`trial` と `employer` のスキルは、判断に必要な料金・契約・支払い・キャンセル・無償掲載可否、募集の表現に関する規制、取引条件の明示や支払期日の定めなどを公式情報で確認する。`sidework` の2つは、労働時間の通算、社会保険、税、取引条件の明示など時点で変わる制度を、厚生労働省・日本年金機構・国税庁・公正取引委員会などの公表資料で確認する。説明に差がある場合は推測で統一せず、確認事項にする。スキル自体はツールを増やさないため、**利用者の環境で Web 検索やページ取得が使えるかどうか**で挙動が変わる。

| 環境 | Web 取得 |
| --- | --- |
| Claude Code | `WebSearch` / `WebFetch` が使える |
| claude.ai / デスクトップアプリ | ウェブ検索が有効なら使える |
| API 経由の自作クライアント | 実装次第 |

取得手段がない環境では、スキルは**記憶から企業情報やサービス条件を書かず**、利用者に該当部分の本文を貼ってもらう手動モードに切り替え、確認できない項目は `unknown` のまま報告に残す。URLだけでは内容を確認済みにしない。

また、利用規約で自動アクセスを禁止しているサイト（転職口コミサイトなど）を機械的に巡回しない。取得は公開ページの個別参照と検索にとどめる。

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
│   │       │   └── _common.py  # 生成物。直接編集しない
│   │       ├── references/   # 必要時に読む詳細（任意）
│   │       └── assets/       # 出力雛形（任意）
│   ├── interview/
│   ├── research/
│   ├── offer/
│   ├── trial/
│   ├── employer/
│   └── sidework/
├── scripts/
│   ├── _common_source.py     # 同梱 _common.py の唯一の編集点
│   ├── sync_common.py        # 各スキルへ配る／--check で同期を検証
│   ├── new_skill.py
│   ├── run_tests.py
│   └── validate_skills.py
└── tests/
    ├── _loader.py            # スクリプトを実行時と同じ条件で読む
    ├── repository/
    └── <category>/
        └── <skill-name>/
            └── test_*.py
```

スキルは `skills/<category>/<skill-name>/` を単位として単独でインストールされ、それより上の階層は利用者の環境に届かない。入力検証とCLIの定型はリポジトリ共通のモジュールにできないため、`scripts/_common_source.py` から各スキルへ同一の内容を配り、検証スクリプトが同期を確認する。

スキルディレクトリはカテゴリの1階層下に置く。ディレクトリ名と `SKILL.md` の `name` は一致させる。

| カテゴリ | 範囲 |
| --- | --- |
| `career` | 自己分析、就活・転職の軸、キャリア設計、転職の意思決定 |
| `documents` | ES、履歴書、職務経歴書、ポートフォリオの作成と添削 |
| `interview` | 面接・面談対策、想定質問、逆質問、振り返り |
| `research` | 業界・企業研究、求人票の読み解き、応募先の選定 |
| `offer` | 内定・オファー比較、条件確認、退職と入社準備 |
| `trial` | 求職者のおためし転職。応募、条件調整、無償体験と有償業務の準備、体験後の判断 |
| `employer` | 求人企業のおためし転職。業務設計、募集文、社内説明、応募者対応、業務委託の条件明示、振り返り |
| `sidework` | 本業と並行する副業の可否・申請、業務委託案件の取引条件と報酬の確認 |

## 開発

新しいスキルの雛形を作る:

```bash
python3 scripts/new_skill.py interview interview-question-prep
```

変更したら検証する:

```bash
python3 scripts/validate_skills.py && python3 scripts/run_tests.py
```

検証内容: フロントマターの必須項目、名前とディレクトリの一致、`PLACEHOLDER`/`TODO` の残留、`marketplace.json` との整合、同梱 `_common.py` の同期、そして**個人情報らしき文字列（メールアドレス、電話番号、12桁数字）の混入**。公開リポジトリなので、実在する求職者の応募書類やサンプルは絶対にコミットしない。

共通処理を変えたときは配り直す:

```bash
python3 scripts/sync_common.py
```

書き方の基準は [CONTRIBUTING.md](CONTRIBUTING.md)、リポジトリ運用は [AGENTS.md](AGENTS.md) を読む。

## ライセンス

[MIT](LICENSE)
