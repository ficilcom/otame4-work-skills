# 明示される労働条件の項目

## 前提

日本では、労働契約を結ぶときに使用者が労働条件を労働者に明示する。項目の一部は書面（労働者が希望した場合の電子メール等を含む）で示される。**この一覧は確認の起点であって、法的な当否の判定ではない。** 明示事項の範囲は法改正で変わるため、判断に使う前に厚生労働省の公表資料で現在の内容を確認する。根拠は労働基準法15条と同法施行規則5条、短時間労働者・有期雇用労働者については別の法律に定めがある。

書面の名称は企業によって違う。「労働条件通知書」「雇用契約書」「労働条件通知書兼雇用契約書」「内定通知書」「採用条件通知書」など。**名称ではなく、中身にどの項目が書かれているかで判断する。** 内定通知書に条件が書かれていない場合、労働条件はまだ書面で確定していない。

## 区分

| group | 意味 | 確認の重み |
| --- | --- | --- |
| `required_written` | 書面等での明示が求められる事項 | 書面にないなら、書面での提示を求める |
| `required` | 明示事項だが書面交付の対象外 | 口頭でも明示され得る。記録は自分で残す |
| `part_time_document` | 短時間・有期雇用の労働者に文書で明示される事項 | 該当する雇用形態のときだけ確認する |
| `conditional` | その定めがある場合に明示される事項 | 定めの有無を先に確認する |
| `practical` | 法定の区分ではないが、入社前に確定させたい項目 | 書面になければ、書面化を求めるか記録を残す |

## 項目一覧

| code | 項目 | group | いつ対象になるか |
| --- | --- | --- | --- |
| `contract_period` | 労働契約の期間 | `required_written` | 常に |
| `renewal_criteria` | 有期契約を更新する場合の基準 | `required_written` | 有期契約 |
| `renewal_limit` | 更新上限の有無と内容 | `required_written` | 有期契約 |
| `workplace` | 就業の場所 | `required_written` | 常に |
| `workplace_change_scope` | 就業の場所の変更の範囲 | `required_written` | 常に |
| `duties` | 従事すべき業務の内容 | `required_written` | 常に |
| `duties_change_scope` | 業務の内容の変更の範囲 | `required_written` | 常に |
| `start_end_time` | 始業・終業の時刻 | `required_written` | 常に |
| `overtime_presence` | 所定労働時間を超える労働の有無 | `required_written` | 常に |
| `breaks_holidays_leave` | 休憩時間・休日・休暇 | `required_written` | 常に |
| `shift_rotation` | 交替制勤務の就業時転換 | `required_written` | 交替制のとき |
| `wage_determination` | 賃金の決定・計算・支払の方法 | `required_written` | 常に |
| `wage_closing_payment` | 賃金の締切・支払の時期 | `required_written` | 常に |
| `resignation` | 退職に関する事項（解雇の事由を含む） | `required_written` | 常に |
| `conversion_opportunity` | 無期転換申込みの機会 | `required_written` | 無期転換の申込権が生じる更新のとき |
| `conversion_conditions` | 無期転換後の労働条件 | `required_written` | 同上 |
| `pay_raise` | 昇給に関する事項 | `required` | 常に |
| `bonus_presence` | 賞与の有無 | `part_time_document` | 短時間・有期雇用 |
| `retirement_allowance_presence` | 退職手当の有無 | `part_time_document` | 短時間・有期雇用 |
| `consultation_contact` | 相談窓口 | `part_time_document` | 短時間・有期雇用 |
| `retirement_allowance` | 退職手当の定め | `conditional` | 定めがあるとき |
| `bonus` | 賞与・臨時の賃金の定め | `conditional` | 定めがあるとき |
| `cost_burden` | 労働者に負担させる食費・作業用品 | `conditional` | 定めがあるとき |
| `safety_health` | 安全衛生 | `conditional` | 定めがあるとき |
| `training` | 職業訓練 | `conditional` | 定めがあるとき |
| `accident_compensation` | 災害補償・業務外の傷病扶助 | `conditional` | 定めがあるとき |
| `awards_sanctions` | 表彰・制裁 | `conditional` | 定めがあるとき |
| `leave_of_absence` | 休職 | `conditional` | 定めがあるとき |
| `fixed_overtime_detail` | 固定残業代の時間数・金額・超過分の取扱い | `practical` | 固定残業代があるとき |
| `social_insurance` | 社会保険・雇用保険の加入 | `practical` | 常に |
| `probation_conditions` | 試用期間中の労働条件 | `practical` | 試用期間があるとき |
| `commute_allowance` | 通勤手当 | `practical` | 定めがあるとき |

## 読むときに詰まりやすいところ

- **変更の範囲** — 「就業の場所」「業務の内容」には、雇入れ直後の内容と、その後の変更の範囲が示される。「会社の定める場所」「会社の定める業務」とだけ書かれている場合、範囲を限定していない記載として扱い、実際にどこまで及ぶかを質問に変える。記載の当否は判定しない。
- **賃金の内訳** — 総額だけの記載では、基本給、固定残業代、諸手当の区別がつかない。固定残業代は時間数・金額・超過分が別途支給されるかの3点が揃って初めて分解できる。揃わない場合は `unclear` にする。求人票の提示年収との突き合わせは `job-posting-analysis` の分解結果を使う。
- **試用期間** — 期間中の賃金・雇用形態・待遇が本採用後と違うことがある。違わないと書かれていない限り、違う可能性を質問に残す。
- **有期契約** — 契約期間、更新の基準、更新上限は3つとも別の項目である。「原則更新」とだけ書かれている記載は基準を示していない。
- **退職に関する事項** — 退職の申出時期と解雇の事由を含む。就業規則を参照する形の記載になっていることが多く、その場合は就業規則をいつ閲覧できるかを確認する。
- **就業規則の参照** — 書面が「詳細は就業規則による」と書いている場合、就業規則を見るまで条件は確定しない。入社前に閲覧できるかを聞く。

## 出典の扱い

| source | 何を指すか | 書面か |
| --- | --- | --- |
| `notice` | 労働条件通知書、労働条件通知書兼雇用契約書 | 書面 |
| `contract` | 雇用契約書 | 書面 |
| `offer_letter` | 内定通知書、採用条件通知書 | 書面 |
| `verbal` | 面談・電話での口頭説明 | 書面でない |
| `posting` | 求人票、募集要項 | 書面でない |
| `interview` | 面接での説明 | 書面でない |
| `agent` | 転職エージェント経由で伝えられた条件 | 書面でない |
| `unknown` | 出所が特定できない | 書面でない |

求人票は募集の条件であって、契約の条件ではない。エージェントの説明も企業の書面ではない。**書面外でしか確認できていない条件は、確認済みとして扱わない。**

## スクリプト入力

`scripts/check_offer_terms.py` は、記載の有無、書面かどうか、出典間の食い違い、承諾期限までに書面が揃うかを数えるだけで、適法性も受諾の可否も判定しない。

```json
{
  "employer": "架空システム株式会社",
  "document": {
    "kind": "offer_letter",
    "form": "written",
    "received_date": "2026-09-10"
  },
  "contract": {
    "type": "indefinite",
    "shift_work": false,
    "part_time_or_fixed_term": false,
    "conversion_applicable": null
  },
  "offer": {
    "offer_date": "2026-09-01",
    "acceptance_deadline": "2026-09-05"
  },
  "items": [
    {"code": "workplace", "status": "stated", "source": "offer_letter", "note": "本社勤務"},
    {"code": "workplace_change_scope", "status": "missing", "source": "offer_letter"},
    {"code": "duties", "status": "stated", "source": "interview"},
    {"code": "fixed_overtime_detail", "status": "unclear", "source": "posting", "applicable": true}
  ],
  "comparisons": [
    {
      "topic": "月額基本給",
      "values": {"posting": "月給28万円", "offer_letter": "月給25万円"},
      "amounts": {"posting": 280000, "offer_letter": 250000}
    },
    {"topic": "リモート勤務", "values": {"interview": "週3日在宅可"}}
  ],
  "open_questions": ["固定残業代の超過分は別途支給されるか"]
}
```

- `document.kind` は `working_conditions_notice` / `employment_contract` / `offer_letter` / `none` / `unknown`。`form` は `written` / `electronic` / `verbal` / `none` / `unknown`。書面をまだ受け取っていない段階では `none` にする。憶測で `written` にしない。
- `items` は確認できた項目だけ入れる。入れなかった項目は「未確認」として数えられる。**未確認を「記載なし」に丸めない。** 記載がないことを確認した項目だけ `status` を `missing` にする。
- `status` は `stated`（記載あり）/ `missing`（記載がないことを確認した）/ `unclear`（記載はあるが読み取れない）/ `unknown`（未確認）。
- `applicable` は `conditional` と `practical` の項目に使う。制度の有無が不明なら省略する。`false` にすると対象外として扱われる。
- `comparisons` は同じ条件について出典ごとの**原文**を入れる。要約や言い換えを入れると食い違いの検出が意味を失う。金額は `amounts` に数値でも渡すと、書面の金額が他の出典より低い場合に注記が出る。

実行:

```bash
python3 scripts/check_offer_terms.py input.json
```

出力の `summary` は確認対象の項目のうち書面で確認できた数、`flags` は確認の抜けと食い違い、`acceptance` は承諾期限と書面の受領時期の関係。`written_terms_before_deadline` が `false` のとき、書面を見る前に承諾期限が来る状態を指す。
