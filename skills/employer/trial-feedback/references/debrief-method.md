# 企業の振り返りの整理の仕方

## 前提

体験後の振り返りは、事前に決めた業務範囲・完了基準と、実施メモ・成果物の確認結果を突き合わせる作業である。採用や継続の最終判断は担当者に残し、ここでは職務に関係する根拠を整理する。

短い体験や一度の失敗から性格・適性・将来の活躍を断定しない。職務と関係のない属性（服装、話し方の印象、年齢、私生活）で評価も順位付けもしない。

## 整理する4つの束

| 束 | 整理する内容 | 混ぜてはいけないもの |
| --- | --- | --- |
| 観察事実 | 実際の行動、実施内容、成果物。誰が何をどう確認したか | 伝聞、印象、職務と無関係な事柄 |
| 事前の期待 | 開始前に合意した完了基準と、それぞれの結果（達成・一部・未達・未確認） | 後から足した期待、社内で言語化していなかった基準 |
| 支援と制約 | 説明・資料・権限・レビューの提供状況、遅れや未提供が結果に与えた影響 | 候補者だけの責任にした説明 |
| 精算と次の対応 | 実施済みの実働に対する支払い、書面の検収基準に沿った扱い、担当者が決める事項と時期 | 成果の評価や採用判断を支払いに反映すること |

## 詰まりやすいところ

- **後から足した期待を事前の基準に混ぜない。** 「もっと速くやってほしかった」は、開始前に合意していなければ評価の根拠にならない。次回の計画の改善点として別に書く。
- **未確認を未達にしない。** 時間不足や今回の業務外で確認できなかった基準は「未確認」であり、「できなかった」ではない。追加で確かめる方法を書く。
- **観察には観察者を付ける。** 担当者自身が見たか、成果物で確認したか、伝聞かを分ける。伝聞は根拠にせず、誰に確認するかを書く。
- **企業の支援の遅れを結果から切り離さない。** 資料が5日遅れた記事の改善案が届いていないなら、その遅れを先に書く。候補者の責任と企業の責任を分ける。
- **無償の見学・学習は成果で評価しない。** 学んだこと、質問、理解を振り返る。企業の実務成果を基準にしない。
- **精算を評価と分ける。** 実施済みの実働は、成果への満足にかかわらず精算する。減額は、書面の検収基準に沿う場合にしか成り立たない。無償のやり直し、賃金ゼロ、無期限の延長を提案しない。精算の条件は `trial-contract-terms` で決めたものに従う。
- **成果不足は、実施済み・未完了・追加希望に分ける。** 「3本のうち1本が期待に届かない」なら、届かなかった部分が何か、それが事前の基準にあったか、企業の支援不足が関わっているかを書く。
- **担当者用のメモと候補者に伝える文面を分ける。** 内部の評価メモ、他候補者との比較、社内の判断過程をフィードバックに入れない。
- **企業が決めていない継続や採用を通知にしない。** 決めるまでは、事実のフィードバックと次の確認までにとどめる。

## フィードバック案の組み立て

1. 体験への礼と、何についてのフィードバックか（業務名、期間）
2. 具体的な作業事実（事前の基準ごとに、何が確認できたか）
3. よかった点（観察事実に基づくもの）
4. 改善・追加で確かめたい点（事前の基準に基づくもの。後から足した期待は「次回の計画で」として分ける）
5. 企業側の支援の状況と、遅れがあればその影響と詫び
6. 精算の扱い（実施済みの実働と、支払時期）
7. 担当者が選んだ次の対応（決まっていれば）と、決まっていなければいつまでに返すか

レビュー公開の依頼は、公式情報で公開範囲や変更可否を確認し、必要以上に候補者を特定しない下書きにする。返信・公開は本人が行う。

## スクリプト入力

`scripts/review_trial.py` は、事前の基準と観察事実、支援の状況、精算を分けて数えるだけで、候補者の適性も採用の成否も判定しない。

```json
{
  "as_of": "2026-10-20",
  "trial": {"label": "架空の記事改善おためし業務", "kind": "paid_work"},
  "expectations": [
    {"code": "a1", "label": "記事1の改善案（根拠・構成・理由）", "agreed_before_start": true, "result": "met"},
    {"code": "a2", "label": "記事2の改善案", "agreed_before_start": true, "result": "met"},
    {"code": "a3", "label": "記事3の改善案", "agreed_before_start": true, "result": "partial", "note": "根拠が1件欠けていた"},
    {"code": "speed", "label": "作業が速いこと", "agreed_before_start": false, "result": "not_met"}
  ],
  "observations": [
    {"fact": "記事1と2の改善案に根拠と理由が付いていた", "expectation": "a1", "source": "artifact", "observer": "編集担当"},
    {"fact": "記事3の改善案は構成案まで。根拠が1件欠けていた", "expectation": "a3", "source": "artifact", "observer": "編集担当"},
    {"fact": "合同レビューで質問を3件出し、翌日に反映した", "source": "observed", "observer": "編集担当"}
  ],
  "support": [
    {"item": "記事3の元資料", "status": "late", "delay_days": 5, "affected": ["a3"]}
  ],
  "settlement": {
    "basis": "hourly",
    "hourly_rate": 2000,
    "hours_worked": 12,
    "hours_planned": 12,
    "acceptance_criteria_in_writing": true,
    "proposed_reduction": null,
    "unpaid_rework_requested": false
  },
  "feedback": {"next_step": "more_checks", "next_step_decided": true, "includes": ["facts", "support_gaps"]}
}
```

- `trial.kind` は `paid_work` / `learning_visit` / `unknown`。`learning_visit` で基準を成果で評価していると注意が出る。
- `expectations` は完了基準。`agreed_before_start` を省略すると「事前に合意していない」として扱い、事前の基準と分けて数える。`result` は `met` / `partial` / `not_met` / `unverified`（確認しなかった）。**未確認を `not_met` にしない。**
- `observations` は観察事実。`expectation` で事前の基準に結びつける。`source` は `observed`（担当者自身が見た）/ `artifact`（成果物で確認）/ `hearsay`（伝聞）/ `unknown`。`job_related` を `false` にすると評価から外れ、注意が出る。
- `support` は企業の支援。`status` は `provided` / `late` / `not_provided` / `unknown`。`affected` に影響した基準のコードを入れると、その基準の未達を候補者だけの責任にしないよう注意が出る。
- `settlement` は精算。`basis` は `hourly` / `fixed` / `none` / `unknown`。`acceptance_criteria_in_writing` は書面の検収基準があるか。`proposed_reduction` は減額を考えている額で、額が決まっていなければ `true` を入れる。書面の基準がなければ注意が出る。`unpaid_rework_requested` は無償のやり直しを求めているか。支払時期・支払主体は `trial-contract-terms` で決めた条件に従い、契約条件がなければ報告に「未記載・要確認」と書く。
- `feedback.next_step` は企業が選ぼうとしている次の対応で、`continue` / `hire_offer` / `more_checks` / `close` / `undecided`。`next_step_decided` はそれが決定済みか。決まっていないのに `continue` や `hire_offer` を通知にしようとすると注意が出る。`includes` はフィードバック案の文面に入れようとしているもので、`facts` / `support_gaps` / `other_candidates` / `internal_notes` / `continuation_promise` / `hire_promise` から選ぶ。「次もお願いするかも」のような含みは `continuation_promise` にあたり、決定前なら別の注意が出る。次の対応の選択と文面の約束は別の問題なので、両方入れると注意も2つ出る。
- 基準に結びつかない職務上の観察は、`expectation` を省略して入れる。評価の根拠にはならないが、報告の第3節に基準外の事実として書く。

実行は標準入力から渡すのを既定にする。実施メモをファイルに残さないためである。ファイルに書いた場合は `python3 scripts/review_trial.py input.json` で読み、終わったら消す。

```bash
python3 scripts/review_trial.py <<'JSON'
{"trial": {"kind": "paid_work"}, "expectations": [], "observations": [], "settlement": {"basis": "hourly"}}
JSON
```

出力の `summary` は事前の基準と後から足した期待の数、結果の内訳、支援の遅れの数、`expectations` は基準ごとの観察数と支援の影響、`settlement` は実施済みの実働に対する精算額（評価とは別）、`readiness` はフィードバック案としてどこまで進められるか、`flags` は送る前に直す点である。`readiness.status` が `ready_for_owner_review` でも、送信・精算・採用の判断は利用者が行う。
