# 副業の規定と抵触しうる義務

## 前提

副業を始めてよいかは、ひとつの決まりで決まらない。勤務先が自分の規則でどう定めているか、雇用契約や誓約書で何を約束しているか、そして働き方の型によって外の制度（労働時間の通算、社会保険、税）でどう扱われるかが、それぞれ別に効く。**この一覧は確認の起点であって、法的な当否の判定ではない。**

厚生労働省はモデル就業規則と副業・兼業の促進に関するガイドラインを公表しており、多くの企業の規程はそれを下敷きにしている。ただし各社の規程は独自に定められ、内容も改定される。**手元の規程の本文を読むことが唯一の確認方法であり、一般論で代用しない。** 制度側の扱い（労働時間の通算、社会保険の適用、確定申告）は時点で変わるため、判断に使う前に厚生労働省・日本年金機構・国税庁の公表資料で現在の内容を確認する。

## 立場

| status | 誰か | 注意 |
| --- | --- | --- |
| `private_employee` | 民間企業に雇用されている | 就業規則と雇用契約が出発点 |
| `public_servant` | 国家公務員・地方公務員 | **法律に基づく制限がある。** 民間の就業規則の判断を当てはめない |
| `self_employed` | すでに個人事業主・フリーランス | 勤務先の規程は関係しないが、既存の取引先との競業・秘密保持は残る |
| `student` | 学生（アルバイトを含む） | 学則、奨学金、在留資格の条件が別に効くことがある |
| `unknown` | 未確認 | 適用される定めが決まらない |

**公務員は別枠にする。** 許可・承認の要否、根拠規定、届出の様式は所属先ごとに定めがあり、国家公務員と地方公務員、常勤と非常勤でも扱いが違いうる。所属先の公表資料と規程で確認し、民間の話と混ぜない。

## 副業の型

| engagement | 何をするか | 変わる論点 |
| --- | --- | --- |
| `employment` | 他社に雇われる（アルバイト、パート、契約社員） | 労働時間の通算、割増賃金、雇用保険、社会保険 |
| `contract_work` | 業務委託・請負で受注する | 賠償責任、経費、確定申告の所得区分 |
| `own_business` | 自分で事業を営む（開業、物販、教室） | 開業の届出、確定申告、屋号と勤務先の関係 |
| `investment` | 資産運用（株式、不動産など） | 規程が「副業」に含めているかどうかが先に問題になる |
| `unknown` | 未確定 | 論点を絞れない |

**名称だけで扱いを決めない。** 「業務委託」と書かれていても、時間で拘束され指揮命令を受ける働き方は、実態で判断が変わりうる。実態に疑いがあるときは、確認先を示すところまでにする。

## 規定の型

| regime | 規程の書きぶり | 次にすること |
| --- | --- | --- |
| `prohibited` | 副業を禁止している | 適用範囲、但し書き、例外の有無を読む。相談窓口を確認する |
| `permission` | 事前の許可・承認を要する | 申請の様式、提出先、判断の基準、所要期間を確認する |
| `notification` | 届出をすれば足りる | 届出の様式、提出先、時期、記載事項を確認する |
| `silent` | 副業についての定めが見当たらない | **許可されていることと同じに扱わない。** 競業・秘密保持・職務専念の定めを個別に読む |
| `unknown` | 未確認 | まず規程の本文を読む |

「原則禁止」「会社が認めた場合を除く」といった書きぶりは、禁止と許可制のどちらにも読める。**原文を写して、許可の条件が書かれているかで判断する。**

## 確認項目一覧

| code | 項目 | group | いつ対象になるか |
| --- | --- | --- | --- |
| `sidework_clause` | 副業・兼業に関する定めの有無と本文 | `rules` | 常に |
| `regime_type` | 禁止・許可制・届出制の別と、その条件 | `rules` | 常に |
| `scope_of_rule` | 規定が対象にする範囲（雇用のみか、業務委託・投資・無償の活動も含むか） | `rules` | 常に |
| `sanctions` | 定めに反したときの取扱い | `rules` | 常に |
| `application_procedure` | 申請・届出の様式、提出先、時期 | `procedure` | 禁止以外 |
| `approval_criteria` | 許可・受理の判断基準 | `procedure` | 許可制のとき |
| `revocation_conditions` | 許可の取消・変更の条件 | `procedure` | 許可制のとき |
| `ongoing_report` | 開始後の報告義務（稼働時間、収入、内容の変更） | `procedure` | 禁止以外 |
| `competition_clause` | 競業避止に関する定め（在職中の範囲） | `duty` | 常に |
| `confidentiality_clause` | 秘密保持の対象と範囲 | `duty` | 常に |
| `dedication_clause` | 職務専念・勤務時間中の取扱い | `duty` | 常に |
| `asset_use_clause` | 会社の設備、データ、アカウント、貸与端末の利用 | `duty` | 常に |
| `ip_clause` | 職務に関する成果物・発明の取扱い | `duty` | 常に |
| `customer_clause` | 取引先・顧客・取引情報に関する制限 | `duty` | 常に |
| `public_servant_permission` | 許可・承認の要否と根拠規定 | `rules` | 公務員のとき |
| `hours_aggregation` | 労働時間の通算と割増賃金の扱い | `external` | 副業が雇用のとき |
| `employment_insurance` | 雇用保険の扱い | `external` | 副業が雇用のとき |
| `social_insurance` | 健康保険・厚生年金の適用と届出 | `external` | 常に |
| `workers_accident` | 労災、通勤災害の扱い | `external` | 常に |
| `tax_filing` | 確定申告と住民税の扱い | `external` | 常に |
| `liability_insurance` | 賠償責任を誰が負うか | `external` | 業務委託・自分の事業のとき |

`group` の意味は次のとおり。`rules` は勤務先の定めそのもの、`procedure` は手続き、`duty` は副業の内容が触れうる義務、`external` は勤務先の外にある制度である。**勤務先に聞くのは `rules` と `procedure` と `duty`、一次情報で確かめるのは `external`** と分けると、質問の宛先を間違えない。

## 抵触しうる論点の見方

副業の中身が次のどれかに当たるとき、規程の文言に照らして確認する。**当たっているかどうかを推測で決めず、事実として分かっていることだけを入れる。**

| 論点 | 何を見るか |
| --- | --- |
| 競業 | 副業先が勤務先と同じ市場で競合するか、勤務先の取引先・顧客か |
| 秘密保持 | 本業で知った情報、資料、顧客名、単価、ノウハウを使うか |
| 職務専念 | 勤務時間中に連絡や作業が発生するか、本業の繁忙期と重なるか |
| 設備・情報 | 会社のPC、回線、アカウント、ライセンス、名刺、肩書を使うか |
| 信用 | 勤務先の名前や在籍を出して活動するか |
| 健康と安全 | 本業と合わせた稼働時間、休みの日、深夜の作業 |

肩書や在籍を出すかどうかは、本人が思っているより広く取られることがある。SNSの表示、登壇のプロフィール、請求書の記載も同じ論点に入る。

## 読むときに詰まりやすいところ

- **「会社の許可なく他に雇われてはならない」は、業務委託を含むとは限らない。** 規定が対象にする範囲（`scope_of_rule`）を、雇用・業務委託・自分の事業・投資・無償の活動に分けて読む。含むと書いていないものを含むと決めつけず、含まないと決めつけもしない。
- **競業避止の定めは、在職中と退職後で範囲が違う。** 副業で問題になるのは在職中の定めである。退職後の条項を読んで在職中の判断をしない。
- **「届出」と書いてあっても、受理されなければ始められない運用のことがある。** 様式に「承認欄」があるかで運用が読めることがある。書面と運用が違いそうなときは、そのまま質問にする。
- **稼働時間の申告は、開始時だけでなく継続的に求められることがある。** `ongoing_report` を確認しないと、始めた後で条件を満たせなくなる。
- **社会保険は、副業先での働き方によって適用の要否が変わる。** 複数の事業所で適用の要件を満たす場合の届出は本人が行うものがある。加入の要否を記憶で断定せず、日本年金機構の公表資料で確認する。
- **税は所得の区分で扱いが違う。** 金額の区切りだけで申告の要否を決めない。所得税と住民税は別であり、片方が不要でももう片方が必要なことがある。国税庁と居住する自治体の公表資料で確認する。

## 出典の扱い

| source | 何を指すか | 根拠になるか |
| --- | --- | --- |
| `employment_rules` | 就業規則の本文 | なる |
| `sidework_policy` | 副業・兼業に関する規程、運用ルール | なる |
| `contract` | 雇用契約書、労働条件通知書 | なる |
| `pledge` | 入社時の誓約書、秘密保持契約 | なる |
| `hearsay` | 上長や同僚から聞いた話、社内の噂 | **ならない** |
| `not_found` | 探したが見当たらなかった | 「規定なし」として扱えるのは、探した範囲まで |
| `unknown` | 未確認 | ならない |

**伝聞を根拠にしない。** 「前例がある」「黙認されている」は、規程の内容でも許可でもない。確認すべき質問として残す。

## スクリプト入力

`scripts/check_sidework_rules.py` は、確認の抜け、根拠のない項目、本業と副業を合わせた稼働、申請材料の欠落を数えるだけで、副業の可否も規定の適法性も判定しない。

```json
{
  "as_of": "2026-09-17",
  "status": "private_employee",
  "engagement": "contract_work",
  "rules": {
    "source": "employment_rules",
    "reviewed": true,
    "regime": "permission",
    "clause_quoted": true
  },
  "sidework": {
    "same_industry": "no",
    "counterparty_is_client": "unknown",
    "uses_employer_information": "no",
    "uses_employer_assets": "no",
    "during_work_hours": "no",
    "uses_employer_name": "unknown"
  },
  "hours": {
    "main_scheduled_weekly": 40,
    "main_overtime_weekly": 5,
    "sidework_weekly": 8,
    "rest_days_per_week": 1,
    "reference_weekly_hours": 40,
    "health_reference_monthly_hours": null
  },
  "items": [
    {"code": "sidework_clause", "status": "stated", "source": "employment_rules", "note": "第○条"},
    {"code": "regime_type", "status": "stated", "source": "employment_rules"},
    {"code": "scope_of_rule", "status": "unclear", "source": "employment_rules"},
    {"code": "competition_clause", "status": "stated", "source": "pledge"},
    {"code": "ongoing_report", "status": "missing", "source": "employment_rules"}
  ],
  "application": [
    {"code": "counterparty", "status": "ready"},
    {"code": "weekly_hours", "status": "draft"},
    {"code": "income", "status": "missing"}
  ]
}
```

- `status` は `private_employee` / `public_servant` / `self_employed` / `student` / `unknown`。`engagement` は `employment` / `contract_work` / `own_business` / `investment` / `unknown`。
- `rules.source` は上の出典表の値。`reviewed` は**本文を自分で読んだか**であり、聞いた話は `false` にする。`clause_quoted` は原文を書き写せているか。
- `sidework` の各項目は `yes` / `no` / `unknown`。**分からないものを `no` にしない。** 該当しないと確認できたものだけ `no` にする。
- `hours` は週あたりの時間。`main_overtime_weekly` は平均の実績を入れる。3つが揃わないと合計を出さない（未入力を0で埋めない）。`rest_days_per_week` は本業も副業もしない日の数。
- `reference_weekly_hours` は合計を比べる基準で、既定は週40時間。事業場の特例など異なる定めがあるときは入れ替える。`health_reference_monthly_hours` は、健康確保のために参照する月あたりの超過時間で、**一次情報で確認した値だけを入れる。** 入れなければ比較しない。
- `items` は確認した項目だけを入れる。入れなかった項目は「未確認」として数えられる。`status` は `stated`（記載あり）/ `missing`（記載がないことを確認した）/ `unclear`（記載はあるが読み取れない）/ `unknown`（未確認）。**未確認を `missing` に丸めない。**
- `application` の `code` は `counterparty`（副業先）、`work_content`（業務の内容）、`engagement_form`（契約の形態）、`schedule`（曜日と時間帯）、`weekly_hours`（週の稼働）、`period`（開始日と期間）、`income`（見込みの報酬）、`conflict_statement`（競業・秘密保持に触れない説明）、`impact_plan`（本業への影響を避ける具体策）。`status` は `ready` / `draft` / `missing`。

実行:

```bash
python3 scripts/check_sidework_rules.py input.json
```

ファイルに残したくない場合は標準入力から渡す。

```bash
python3 scripts/check_sidework_rules.py <<'JSON'
{"status": "private_employee", "rules": {"source": "hearsay", "reviewed": false}}
JSON
```

出力の `checklist` は項目ごとの確認状況、`hours` は合計の稼働、`application` は申請材料の準備状況、`flags` は確認の抜けと抵触しうる論点、`summary` は数である。`flags` は確認すべきことの一覧であって、違反の認定ではない。
