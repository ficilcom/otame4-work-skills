# 発注側が着手前に明示する取引条件

## 前提

有償のおためし業務を業務委託で発注するとき、何を、いつまでに、いくらで、どこまでやってもらうのかを、着手前に書面か電子メール等で候補者に示す。日本では、発注者が受注者に取引条件を明示することや、支払期日の設定について定めがある。**この一覧は確認の起点であって、法的な当否の判定ではない。** 定めの範囲と内容は改正で変わるため、判断に使う前に公正取引委員会・中小企業庁・厚生労働省の公表資料で現在の内容を確認する。

書面の名称は問わない。「業務委託契約書」「発注書」「条件を書いたメール」のどれでも、中身にどの項目が書かれているかで判断する。「後で契約書を送ります」と言っている段階では、条件はまだ確定していない。サービス上の契約画面や求人条件が書面に準じるかは、[公式情報の確認](source-checks.md) で確かめる。

**雇用として受け入れる場合はこの一覧の対象外である。** アルバイト、パート、契約社員として雇う場合は労働条件の明示が論点になる。「業務委託」という名称でも、時間で拘束し指揮命令する働き方は扱いが変わりうるため、`trial-work-design` の計画で実態を確かめ、疑いがあるときは確認先を示すところまでにする。

求職者側は `sidework-terms-check` で同じ項目を受注者の目で確認する。ここでは同じ項目を発注する側から埋める。候補者に「これは書いてありますか」と聞かれる前に書く。

## 区分

| group | 意味 | 確認の重み |
| --- | --- | --- |
| `transaction` | 取引の骨格。何を、いつまでに、いくらで、誰が払うか | **着手前に書面で確定させる** |
| `scope` | どこまでが仕事か。範囲、回数、企業の支援 | 開いたままだと、後から無償の作業が増える |
| `money` | 金銭の周辺。経費、税、手数料 | 提示額と候補者の手取りが変わる |
| `rights` | 成果物と情報の扱い | 後から変えられない |
| `exit` | 終わり方と、うまくいかなかったとき | 起きてから決めると候補者に不利になりやすい |

## 項目一覧

| code | 項目 | group | いつ対象になるか |
| --- | --- | --- | --- |
| `parties` | 発注者（企業）と受注者（候補者）の名称 | `transaction` | 常に |
| `order_date` | 業務を委託する日 | `transaction` | 常に |
| `deliverable` | 給付の内容（何を、いくつ、どの品質で） | `transaction` | 常に |
| `delivery_date` | 給付を受領する期日 | `transaction` | 常に |
| `delivery_place` | 給付を受領する場所・方法 | `transaction` | 常に |
| `inspection` | 検査を行う場合の検査完了日と担当 | `transaction` | 検査があるとき |
| `payment_amount` | 報酬の額と算定方法 | `transaction` | 常に |
| `payment_due` | 支払期日 | `transaction` | 常に |
| `payer` | 支払主体（企業が直接か、サービス経由か） | `transaction` | 常に |
| `payment_method` | 支払方法と振込手数料の負担 | `money` | 常に |
| `scope_out` | 範囲外とみなす作業 | `scope` | 常に |
| `revision_limit` | 修正の回数と1回あたりの範囲 | `scope` | 成果物を納めてもらうとき |
| `estimated_hours` | 想定される実働時間 | `scope` | 常に |
| `company_support` | 企業が提供する説明、資料、権限、レビュー | `scope` | 常に |
| `response_expectation` | 連絡手段と応答を求める時間帯 | `scope` | 常に |
| `expenses` | 経費の負担 | `money` | 常に |
| `withholding` | 源泉徴収の有無 | `money` | 常に |
| `consumption_tax` | 消費税の扱い | `money` | 常に |
| `ip_ownership` | 成果物の権利の帰属と移転の時期 | `rights` | 成果物を納めてもらうとき |
| `credit_disclosure` | 候補者が実績として公開できる範囲 | `rights` | 常に |
| `confidentiality` | 秘密保持の対象と期間 | `rights` | 常に |
| `late_or_defect` | 遅延・不備があったときの取扱い | `exit` | 常に |
| `termination` | 中途解除・中止のときの報酬と予告（双方） | `exit` | 常に |
| `after_trial` | 体験後の扱い（採用や継続を保証しないこと） | `exit` | 常に |

## 着手前に確定させる項目

次の項目は、着手してからでは条件を戻しにくい。**未確定のまま着手日を迎えないことを前提に扱う。**

`deliverable` / `delivery_date` / `payment_amount` / `payment_due` / `payer` / `scope_out` / `revision_limit` / `company_support` / `ip_ownership` / `confidentiality` / `termination`

残りの項目は、進めながら決めても取り返しがつくことが多い。ただし `expenses` と `withholding` と `consumption_tax` は、候補者が手取りを見積もるのに要るため、聞かれる前に書く。

## 発注する側が詰まりやすいところ

- **「納得するまで修正」を条件にしない。** 品質は、誰が何を見て完了とするか（`deliverable` と `inspection`）で決め、修正は回数と時間の上限（`revision_limit`）で閉じる。上限を超える修正は追加の発注として扱う。
- **成果への満足や採用の判断を支払いの条件にしない。** 実施済みの実働と検収済みの給付に対する支払いは、評価や採用判断と分ける。「期待に届かなかったので減額」は、検収の基準が書面にあり、それに沿って行う場合しか成り立たない。
- **中止したときの精算を決める。** 企業の都合で中止しても、実施済みの実働は支払う。中途解除の定めを企業側だけに置かない。
- **支払期日は受領日から数える。** 「月末締め翌月末払い」は運用であって期日ではない。受領日と支払期日を書き、日数を数える。受領から支払期日までの上限は公表資料で確認し、超えるなら支払期日を見直す。
- **支払主体をサービスの一般像で決めない。** 企業が直接払うのか、サービス経由なのかは、企業向け規約と今回の契約資料で確認する。確認できるまで `payer` は未確認のまま残す。
- **修正を無償にしない。** 合意した範囲の修正は実働として報酬に含める。範囲外の修正は追加の発注にする。
- **企業の支援も条件である。** 説明、資料、権限、レビューをいつ提供するかを書く。提供が遅れたときに候補者の納期がどう動くかも `late_or_defect` に書く。
- **候補者が実績として公開できる範囲を書く。** 秘密保持とは別の項目である。書かないと、候補者は次の仕事に使えるかを判断できない。
- **源泉徴収と消費税の扱いを書く。** 「時給2,000円」が税込みか税抜きか、源泉徴収の対象かで候補者の手取りが変わる。税額の計算はしないが、扱いは書く。

## 出典の扱い

| source | 何を指すか | 書面か |
| --- | --- | --- |
| `contract` | 業務委託契約書、基本契約と個別契約 | 書面 |
| `purchase_order` | 発注書、注文書 | 書面 |
| `email` | 条件を書いた電子メール | 書面に準じる |
| `platform` | サービス上の契約画面、求人の条件欄 | 書面に準じるかを公式情報で確認する |
| `chat` | チャット、メッセージアプリ | 書面でない扱いにする |
| `verbal` | 面談、電話での口頭説明 | 書面でない |
| `unknown` | 出所が特定できない | 書面でない |

**書面でない出所にしかない条件は、明示済みとして扱わない。** チャットで合意した条件は、書面か電子メールに載せ直す。

## スクリプト入力

`scripts/check_contract_terms.py` は、明示の状況、予定額、支払期日までの日数、修正と解除の定めを数えるだけで、条件の妥当性も適法性も判定しない。

```json
{
  "as_of": "2026-09-17",
  "engagement": "contract_work",
  "document": {"form": "email", "planned_start": "2026-10-01"},
  "items": [
    {"code": "deliverable", "status": "stated", "source": "email", "note": "記事3本の改善案"},
    {"code": "delivery_date", "status": "stated", "source": "email"},
    {"code": "payment_amount", "status": "stated", "source": "chat"},
    {"code": "payment_due", "status": "missing", "source": "email"},
    {"code": "payer", "status": "unknown"},
    {"code": "inspection", "applicable": false},
    {"code": "revision_limit", "applicable": true, "status": "stated", "source": "email"}
  ],
  "compensation": {
    "basis": "hourly",
    "hourly_rate": 2000,
    "hours": 12,
    "conditional_on_outcome": false,
    "pays_work_done_on_termination": true
  },
  "payment": {
    "delivery_date": "2026-10-14",
    "acceptance_date": null,
    "due_date": "2026-11-30",
    "reference_term_days": null
  },
  "revisions": {"rounds": 1, "hours": 2, "unpaid": false},
  "termination": {"company_may_terminate": true, "candidate_may_terminate": true}
}
```

- `engagement` は `contract_work` / `employment` / `unknown`。`employment` を入れると、労働条件の明示が論点であり、この確認表の対象外であることを注意として返す。
- `document.form` は上の出典表の値、または `none`（まだ何も書いていない）。`platform` / `chat` / `verbal` / `none` は書面でない扱いになる。
- `items` は確認した項目だけを入れる。入れなかった項目は「未確認」として数えられる。`status` は `stated` / `missing`（書いていないことを確認した）/ `unclear`（書いてはあるが読み取れない）/ `unknown`（未確認）。**未確認を `missing` に丸めない。** 条件付きの項目は `applicable` で対象かどうかを入れる。
- `compensation.basis` は `hourly` / `fixed` / `unknown`。`conditional_on_outcome` は成果への満足や採用判断を支払いの条件にしているか、`pays_work_done_on_termination` は中止時に実施済みの実働を支払うか。**どちらも `null` は「決めていない」であり、問題なしではない。**
- `payment.reference_term_days` は、受領日から支払期日までの日数として参照する上限で、**一次情報で確認した値だけを入れる。** 入れなければ比較しない。
- `revisions` は修正の回数と時間の上限。`0` は「修正なしで合意した」、`null` は「決めていない」で別物である。`unpaid` は修正を無償にしているか。
- `termination` は中途解除を企業側・候補者側のそれぞれが行えるか。企業側だけなら注意が出る。

実行:

```bash
python3 scripts/check_contract_terms.py input.json
```

ファイルに残したくない場合は標準入力から渡す。

出力の `summary` は着手前に確定させる項目の明示状況の数、`checklist` は項目ごとの明示状況、`money` は予定額と支払条件、`payment` は受領から支払期日までの日数、`readiness` は候補者に提示できる状態かどうか、`flags` は提示前に直す点である。`readiness.status` が `ready_for_owner_review` でも、提示と契約の締結は利用者が行う。
