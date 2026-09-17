# 明示される取引条件の項目

## 前提

業務委託で仕事を受けるとき、何を、いつまでに、いくらで、どこまでやるのかは、着手前に書面や電子メール等で示されているのが望ましい。日本では、発注者が受注者に取引条件を明示することや、支払期日の設定について定めがある。**この一覧は確認の起点であって、法的な当否の判定ではない。** 定めの範囲と内容は改正で変わるため、判断に使う前に公正取引委員会・中小企業庁・厚生労働省の公表資料で現在の内容を確認する。

書面の名称は発注者によって違う。「業務委託契約書」「発注書」「注文書」「基本契約書と個別契約」「見積書の承認」など。**名称ではなく、中身にどの項目が書かれているかで判断する。** 「契約書は後で送ります」と言われた段階では、条件はまだ確定していない。

**雇用として働く副業はこの一覧の対象外である。** アルバイト、パート、契約社員として他社に雇われる場合は、労働条件の明示が論点になるため `offer-terms-check` を使う。「業務委託」という名称でも、時間で拘束され指揮命令を受ける働き方は扱いが変わりうるため、実態を聞き取り、疑いがあるときは確認先を示すところまでにする。

## 区分

| group | 意味 | 確認の重み |
| --- | --- | --- |
| `transaction` | 取引の骨格。何を、いつまでに、いくらで | **着手前に書面で確定させる** |
| `scope` | どこまでが仕事か。範囲と回数 | 開いたままだと、後から無償の作業が増える |
| `money` | 金銭の周辺。経費、税、手数料 | 提示額と手取りが変わる |
| `rights` | 成果物と情報の扱い | 後から変えられない |
| `exit` | 終わり方と、うまくいかなかったとき | 起きてから決めると不利になりやすい |
| `practical` | 進め方の取り決め | 書面になければ記録を残す |

## 項目一覧

| code | 項目 | group | いつ対象になるか |
| --- | --- | --- | --- |
| `parties` | 発注者と受注者の名称 | `transaction` | 常に |
| `order_date` | 業務を委託した日 | `transaction` | 常に |
| `deliverable` | 給付の内容（何を納めるか） | `transaction` | 常に |
| `delivery_date` | 給付を受領する期日 | `transaction` | 常に |
| `delivery_place` | 給付を受領する場所・方法 | `transaction` | 常に |
| `inspection` | 検査を行う場合の検査完了日 | `transaction` | 検査があるとき |
| `payment_amount` | 報酬の額と算定方法 | `transaction` | 常に |
| `payment_due` | 支払期日 | `transaction` | 常に |
| `payment_method` | 支払方法と振込手数料の負担 | `money` | 常に |
| `scope_out` | 範囲外とみなす作業（追加、打合せ、緊急対応） | `scope` | 常に |
| `revision_limit` | 修正の回数と1回あたりの範囲 | `scope` | 成果物を納めるとき |
| `estimated_hours` | 想定される稼働時間 | `scope` | 常に |
| `response_expectation` | 連絡手段と応答を求められる時間帯 | `scope` | 常に |
| `materials` | 提供される資料、アカウント、機材 | `scope` | 常に |
| `expenses` | 経費の負担（交通、通信、ツール、素材） | `money` | 常に |
| `withholding` | 源泉徴収の有無 | `money` | 常に |
| `consumption_tax` | 消費税の扱いとインボイスの求め | `money` | 常に |
| `ip_ownership` | 成果物の権利の帰属と移転の時期 | `rights` | 成果物を納めるとき |
| `secondary_use` | 二次利用・改変・転売の範囲 | `rights` | 成果物を納めるとき |
| `credit_disclosure` | 実績として公開できる範囲 | `rights` | 常に |
| `confidentiality` | 秘密保持の対象と期間 | `rights` | 常に |
| `competition_restriction` | 競業・専属の制限 | `rights` | 定めがあるとき |
| `subcontracting` | 再委託の可否 | `practical` | 常に |
| `late_or_defect` | 遅延・不備があったときの取扱い | `exit` | 常に |
| `liability` | 損害賠償の範囲と上限 | `exit` | 常に |
| `termination` | 中途解除・中止のときの報酬と予告 | `exit` | 常に |

## 着手前に確定させる項目

次の項目は、着手してからでは条件を戻しにくい。**未確定のまま作業を始めないことを前提に扱う。**

`deliverable` / `delivery_date` / `payment_amount` / `payment_due` / `scope_out` / `revision_limit` / `ip_ownership` / `confidentiality` / `termination`

残りの項目は、進めながら決めても取り返しがつくことが多い。ただし `expenses` と `withholding` と `consumption_tax` は、確定しないと手取りが分からないため、報酬の判断に使うなら着手前に聞く。

## 読むときに詰まりやすいところ

- **「一式」「まるっとお願いします」は範囲ではない。** 何を納めたら完了かが書かれていないと、修正と追加が無限に続く。`deliverable` と `scope_out` と `revision_limit` の3つが揃って初めて範囲が閉じる。
- **打合せ、資料の読み込み、修正、待ち時間は稼働である。** 報酬の対象に入っていなくても、時間としては消える。総稼働に入れて換算時給を出す。
- **「まずはお試しで」「実績になるので」は報酬の代わりにならない。** 無償の作業がある場合は、その時間を総稼働に入れる。換算時給はその分下がる。
- **支払期日は「月末締め翌月末払い」のような運用で決まることが多い。** 納品日から実際の入金日まで何日あるかを数える。受領日と検査完了日のどちらを起点にするかも書かれているか確認する。
- **源泉徴収と消費税で、提示額と入金額が変わる。** 「10万円で」と言われた額が、税込みか税抜きか、源泉徴収の前か後かで手取りが変わる。どちらか分からないうちは手取りを計算しない。
- **権利の帰属は、納品時か、支払完了時かで違う。** 支払が滞ったときの扱いが変わる。二次利用、改変、転売の範囲も別の項目である。
- **実績として公開できるかは、秘密保持と別に書かれていることがある。** ポートフォリオに載せられない案件は、次の仕事につながる度合いが変わる。
- **中途解除の定めは、発注者側だけに置かれていることがある。** 中止になったときに、そこまでの作業分が支払われるかを確認する。

## 出典の扱い

| source | 何を指すか | 書面か |
| --- | --- | --- |
| `contract` | 業務委託契約書、基本契約と個別契約 | 書面 |
| `purchase_order` | 発注書、注文書 | 書面 |
| `email` | 条件が書かれたメール | 書面に準じる |
| `proposal` | 見積書、提案書のうち承認されたもの | 書面に準じる |
| `chat` | チャット、メッセージアプリでのやり取り | 書面でない扱いにする |
| `verbal` | 打合せ、電話での口頭説明 | 書面でない |
| `listing` | 案件サイトの募集文 | 書面でない |
| `unknown` | 出所が特定できない | 書面でない |

募集文は募集の条件であって、契約の条件ではない。**書面外でしか確認できていない条件は、確認済みとして扱わない。** チャットで合意した条件は、記録として残しておくと後の確認に使える。

## スクリプト入力

`scripts/check_sidework_terms.py` は、明示の状況、稼働の合計、換算時給、支払までの日数、範囲の開きを数えるだけで、条件の妥当性も適法性も判定しない。

```json
{
  "as_of": "2026-09-20",
  "engagement": "contract_work",
  "offer": {"form": "email", "received_date": "2026-09-18"},
  "items": [
    {"code": "deliverable", "status": "stated", "source": "email", "note": "記事3本"},
    {"code": "payment_amount", "status": "stated", "source": "email"},
    {"code": "payment_due", "status": "unclear", "source": "email"},
    {"code": "scope_out", "status": "missing", "source": "email"},
    {"code": "ip_ownership", "status": "unknown"}
  ],
  "work": [
    {"label": "取材と資料の読み込み", "hours": 4, "paid": false},
    {"label": "執筆", "hours": 9, "hours_max": 12, "paid": true},
    {"label": "打合せ", "hours": 2, "paid": false},
    {"label": "修正対応", "hours": 2, "hours_max": 4, "paid": true}
  ],
  "compensation": {
    "basis": "fixed",
    "fixed_amount": 90000,
    "expenses_borne_by_worker": 3000,
    "withholding": null,
    "consumption_tax": "unknown"
  },
  "payment": {
    "delivery_date": "2026-10-15",
    "acceptance_date": null,
    "due_date": "2026-12-31",
    "reference_term_days": null
  },
  "availability": {"weekly_hours": 6, "weeks": 4},
  "revisions": {"rounds": null, "hours": null}
}
```

- `engagement` は `contract_work` / `employment` / `unknown`。`employment` を入れると、労働条件の明示が論点であることを注意として返す。判定はこのスクリプトでは行わない。
- `offer.form` は上の出典表の値、または `none`（まだ何も来ていない）。`chat` / `verbal` / `listing` / `none` は書面でない扱いになる。
- `items` は確認した項目だけを入れる。入れなかった項目は「未確認」として数えられる。`status` は `stated` / `missing`（記載がないことを確認した）/ `unclear`（記載はあるが読み取れない）/ `unknown`（未確認）。**未確認を `missing` に丸めない。**
- `work` は作業ごとの見込み時間。`hours_max` を入れると幅で計算する。`paid` は支払いの対象かどうかで、**未記載は `null`（不明）であり、無償と決めつけない。** 打合せ、待ち時間、修正、移動、請求書の作成も作業として入れる。
- `compensation.basis` は `fixed` / `hourly` / `per_deliverable` / `unknown`。`hourly` なら `hourly_rate`、`per_deliverable` なら `unit_amount` と `units` を入れる。`expenses_borne_by_worker` は自分が負担する経費の見込み額。`withholding` は源泉徴収の有無（`true` / `false` / `null`）、`consumption_tax` は `included` / `excluded` / `unknown`。**税額と手取りは計算しない。**
- `payment.reference_term_days` は、受領日から支払期日までの日数として参照する上限で、**一次情報で確認した値だけを入れる。** 入れなければ比較しない。
- `availability` は、この案件に出せる週あたりの時間と、使える週数。
- `revisions` は修正の回数と時間の上限。どちらかが `null` なら範囲が開いているとして扱う。

実行:

```bash
python3 scripts/check_sidework_terms.py input.json
```

ファイルに残したくない場合は標準入力から渡す。

```bash
python3 scripts/check_sidework_terms.py <<'JSON'
{"engagement": "contract_work", "offer": {"form": "chat"}}
JSON
```

出力の `checklist` は項目ごとの明示の状況、`hours` は稼働の合計、`money` は予定額と換算時給、`payment` は受領から支払期日までの日数、`schedule` は週あたりの稼働、`flags` は未確定と範囲の開きである。`effective_hourly_all` は無償の作業も含めた総稼働で割った値で、無償の作業が多いほど下がる。
