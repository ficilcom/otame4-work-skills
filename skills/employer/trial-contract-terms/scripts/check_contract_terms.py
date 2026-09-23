#!/usr/bin/env python3
"""Check what the company has put in writing before a paid trial starts.

業務委託で有償のおためし業務を発注する企業の側から、給付の内容、報酬、支払期日など
着手前に明示する取引条件が書面や電子メールで示されているかを項目ごとに数え、
受領から支払期日までの日数を数え、成果や満足を支払いの条件にする定め、上限のない
修正、企業側だけの中途解除など、候補者に提示する前に直す点を返す。相場や慣行で
条件を補わず、適法性は判定しない。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_choice,
    optional_date,
    optional_number,
    optional_positive_int,
    optional_text,
    require_list,
    require_object,
    round_yen,
    run_cli,
)


ENGAGEMENTS = ("contract_work", "employment", "unknown")
# 条件をどの形で示すか。`none` はまだ候補者に何も伝えていない状態。チャットや口頭で
# 伝えた条件があるなら `chat` / `verbal` にし、書面でない扱いとして数える。
DOCUMENT_FORMS = ("contract", "purchase_order", "email", "platform", "chat", "verbal", "none", "unknown")
TERM_SOURCES = tuple(form for form in DOCUMENT_FORMS if form != "none")
# 書面、または書面に準じるものとして数える。チャットと口頭は含めない。
# `platform` はサービス上の契約画面や求人条件で、書面に準じるかは公式情報で確認する。
WRITTEN_SOURCES = ("contract", "purchase_order", "email")
ITEM_STATUSES = ("stated", "missing", "unclear", "unknown")
COMPENSATION_BASIS = ("hourly", "fixed", "unknown")

# (code, label, group, conditional, start_required)
# conditional は、業務によって対象外になりうる項目。対象外にするときは入力の
# `applicable` を false にする。start_required は、着手前に確定させる項目。
CHECKLIST: tuple[tuple[str, str, str, bool, bool], ...] = (
    ("parties", "発注者（企業）と受注者（候補者）の名称", "transaction", False, False),
    ("order_date", "業務を委託する日", "transaction", False, False),
    ("deliverable", "給付の内容（何を、いくつ、どの品質で）", "transaction", False, True),
    ("delivery_date", "給付を受領する期日", "transaction", False, True),
    ("delivery_place", "給付を受領する場所・方法", "transaction", False, False),
    ("inspection", "検査を行う場合の検査完了日と担当", "transaction", True, False),
    ("payment_amount", "報酬の額と算定方法", "transaction", False, True),
    ("payment_due", "支払期日", "transaction", False, True),
    ("payer", "支払主体（企業が直接か、サービス経由か）", "transaction", False, True),
    ("payment_method", "支払方法と振込手数料の負担", "money", False, False),
    ("scope_out", "範囲外とみなす作業", "scope", False, True),
    ("revision_limit", "修正の回数と1回あたりの範囲", "scope", True, True),
    ("estimated_hours", "想定される実働時間", "scope", False, False),
    ("company_support", "企業が提供する説明、資料、権限、レビュー", "scope", False, True),
    ("response_expectation", "連絡手段と応答を求める時間帯", "scope", False, False),
    ("expenses", "経費の負担", "money", False, False),
    ("withholding", "源泉徴収の有無", "money", False, False),
    ("consumption_tax", "消費税の扱い", "money", False, False),
    ("ip_ownership", "成果物の権利の帰属と移転の時期", "rights", True, True),
    ("credit_disclosure", "候補者が実績として公開できる範囲", "rights", False, False),
    ("confidentiality", "秘密保持の対象と期間", "rights", False, True),
    ("late_or_defect", "遅延・不備があったときの取扱い", "exit", False, False),
    ("termination", "中途解除・中止のときの報酬と予告（双方）", "exit", False, True),
    ("after_trial", "体験後の扱い（採用や継続を保証しないこと）", "exit", False, False),
)
CHECKLIST_CODES = {code for code, _, _, _, _ in CHECKLIST}


def parse_document(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "document")
    form = optional_choice(block.get("form"), "document.form", DOCUMENT_FORMS, "unknown")
    return {
        "form": form,
        "in_writing": form in WRITTEN_SOURCES,
        "planned_start": optional_date(block.get("planned_start"), "document.planned_start"),
    }


def parse_items(raw: object) -> dict[str, dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "items")
    parsed: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        path = f"items[{index}]"
        item = require_object(entry, path)
        code = item.get("code")
        if code not in CHECKLIST_CODES:
            raise ValueError(f"{path}.code is not a known checklist code: {code!r}")
        if code in parsed:
            raise ValueError(f"{path}.code is duplicated: {code!r}")
        source = item.get("source")
        if source is not None and source not in TERM_SOURCES:
            raise ValueError(f"{path}.source must be one of {list(TERM_SOURCES)}")
        parsed[str(code)] = {
            "status": optional_choice(item.get("status"), f"{path}.status", ITEM_STATUSES, "unknown"),
            "source": source,
            "applicable": optional_bool(item.get("applicable"), f"{path}.applicable"),
            "note": optional_text(item.get("note"), f"{path}.note"),
        }
    return parsed


def parse_compensation(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "compensation")
    return {
        "basis": optional_choice(block.get("basis"), "compensation.basis", COMPENSATION_BASIS, "unknown"),
        "hourly_rate": optional_number(block.get("hourly_rate"), "compensation.hourly_rate", allow_zero=False),
        "fixed_amount": optional_number(block.get("fixed_amount"), "compensation.fixed_amount", allow_zero=False),
        "hours": optional_number(block.get("hours"), "compensation.hours"),
        # 成果への満足や採用の判断を支払いの条件にしているか。
        "conditional_on_outcome": optional_bool(
            block.get("conditional_on_outcome"), "compensation.conditional_on_outcome"
        ),
        # 中止したとき、実施済みの実働を支払うか。
        "pays_work_done_on_termination": optional_bool(
            block.get("pays_work_done_on_termination"), "compensation.pays_work_done_on_termination"
        ),
    }


def parse_payment(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "payment")
    delivery = optional_date(block.get("delivery_date"), "payment.delivery_date")
    acceptance = optional_date(block.get("acceptance_date"), "payment.acceptance_date")
    if delivery is not None and acceptance is not None and acceptance < delivery:
        raise ValueError("payment.acceptance_date must not precede payment.delivery_date")
    return {
        "delivery_date": delivery,
        "acceptance_date": acceptance,
        "due_date": optional_date(block.get("due_date"), "payment.due_date"),
        # 受領から支払期日までの日数として参照する上限。一次情報で確認した値だけを入れる。
        "reference_term_days": optional_positive_int(
            block.get("reference_term_days"), "payment.reference_term_days"
        ),
    }


def parse_revisions(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "revisions")
    rounds = block.get("rounds")
    hours = block.get("hours")
    # 0 は「修正なしで合意した」、null は「決めていない」。別物として扱う。
    return {
        "rounds": None if rounds is None else _non_negative_int(rounds, "revisions.rounds"),
        "hours": optional_number(hours, "revisions.hours"),
        "unpaid": optional_bool(block.get("unpaid"), "revisions.unpaid"),
    }


def _non_negative_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path} must be a non-negative integer or null")
    return value


def parse_termination(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "termination")
    return {
        "company_may_terminate": optional_bool(block.get("company_may_terminate"), "termination.company_may_terminate"),
        "candidate_may_terminate": optional_bool(
            block.get("candidate_may_terminate"), "termination.candidate_may_terminate"
        ),
    }


def build_checklist(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    checklist = []
    for code, label, group, conditional, start_required in CHECKLIST:
        entry = items.get(code)
        applicable = entry["applicable"] if entry else None
        if applicable is None:
            # 条件付きの項目は、対象かどうかが入力されるまで判定しない。ただし記載の
            # 有無を確認済み（stated / missing / unclear）なら、対象として扱っている。
            checked = bool(entry and entry["status"] != "unknown")
            applicable = True if (not conditional or checked) else None
        checklist.append(
            {
                "code": code,
                "label": label,
                "group": group,
                "conditional": conditional,
                "start_required": start_required,
                "applicable": applicable,
                "status": entry["status"] if entry else "unknown",
                "source": entry["source"] if entry else None,
                "in_writing": bool(entry and entry["source"] in WRITTEN_SOURCES),
                "note": entry["note"] if entry else None,
            }
        )
    return checklist


def build_money(compensation: dict[str, Any]) -> dict[str, Any]:
    planned = None
    if compensation["basis"] == "hourly" and compensation["hourly_rate"] is not None and compensation["hours"] is not None:
        planned = compensation["hourly_rate"] * compensation["hours"]
    elif compensation["basis"] == "fixed" and compensation["fixed_amount"] is not None:
        planned = compensation["fixed_amount"]
    return {
        "basis": compensation["basis"],
        "hourly_rate": round_yen(compensation["hourly_rate"]),
        "fixed_amount": round_yen(compensation["fixed_amount"]),
        "hours": float(compensation["hours"]) if compensation["hours"] is not None else None,
        "planned_total": round_yen(planned),
        "conditional_on_outcome": compensation["conditional_on_outcome"],
        "pays_work_done_on_termination": compensation["pays_work_done_on_termination"],
    }


def days_between(start: date | None, end: date | None) -> int | None:
    return None if start is None or end is None else (end - start).days


def build_payment(payment: dict[str, Any]) -> dict[str, Any]:
    from_delivery = days_between(payment["delivery_date"], payment["due_date"])
    from_acceptance = days_between(payment["acceptance_date"], payment["due_date"])
    reference = payment["reference_term_days"]
    exceeds = None
    if reference is not None and from_delivery is not None:
        exceeds = from_delivery > reference
    return {
        "delivery_date": payment["delivery_date"].isoformat() if payment["delivery_date"] else None,
        "acceptance_date": payment["acceptance_date"].isoformat() if payment["acceptance_date"] else None,
        "due_date": payment["due_date"].isoformat() if payment["due_date"] else None,
        "days_from_delivery": from_delivery,
        "days_from_acceptance": from_acceptance,
        "reference_term_days": reference,
        "exceeds_reference": exceeds,
    }


def collect_flags(
    engagement: str,
    document: dict[str, Any],
    checklist: list[dict[str, Any]],
    money: dict[str, Any],
    payment: dict[str, Any],
    revisions: dict[str, Any],
    termination: dict[str, Any],
) -> list[dict[str, Any]]:
    flags, add = flag_collector("items")

    if engagement == "employment":
        add(
            "employment_not_contract_work",
            "雇用として受け入れる計画である。労働条件の明示が論点になり、この確認表の対象外になる。"
            "指揮命令・拘束の実態と合わせて確認先を示す",
        )
    elif engagement == "unknown":
        add("engagement_unknown", "契約の型（業務委託か雇用か）が決まっていない。名称ではなく、指揮命令と拘束の実態で確かめる")

    if document["form"] == "none":
        add("nothing_in_writing_yet", "条件をまだ何にも書いていない。以降の項目はすべて未確定である")
    elif not document["in_writing"]:
        add(
            "document_not_in_writing",
            "条件がチャット・口頭・サービス画面どまりである。着手前に書面か電子メールで示す。"
            "サービス画面が書面に準じるかは公式情報で確認する",
        )

    applicable = [item for item in checklist if item["applicable"] is not False]
    start_items = [item for item in applicable if item["start_required"]]
    for status, code, message in (
        ("missing", "start_required_missing", "着手前に確定させる項目が書かれていない"),
        ("unclear", "start_required_unclear", "着手前に確定させる項目が、書いてはあるが読み取れない"),
        ("unknown", "start_required_unchecked", "着手前に確定させる項目を確認していない。未確認を「記載なし」に丸めない"),
    ):
        found = [item["code"] for item in start_items if item["status"] == status]
        if found:
            add(code, message, found)

    not_written = [item["code"] for item in start_items if item["status"] == "stated" and not item["in_writing"]]
    if not_written:
        add("start_required_not_in_writing", "着手前の項目が書面でない出所にしかない。書面か電子メールに載せる", not_written)

    undecided = [item["code"] for item in checklist if item["conditional"] and item["applicable"] is None]
    if undecided:
        add("applicability_undecided", "対象かどうかを決めていない条件付きの項目がある", undecided)

    if money["basis"] == "unknown":
        add("compensation_basis_unknown", "報酬の決め方が未定である。相場で埋めず、予定額を出していない")
    elif money["planned_total"] is None:
        add("compensation_incomplete", "単価・実働または固定額が入っていない。予定額を出していない")

    if money["conditional_on_outcome"] is True:
        add(
            "payment_conditional_on_outcome",
            "成果への満足や採用の判断を支払いの条件にしている。実施済みの実働と検収済みの給付に対する支払いを、"
            "評価や採用判断と分ける",
        )
    elif money["conditional_on_outcome"] is None:
        add("payment_condition_unchecked", "支払いが成果や採用判断に左右されないことを確認していない")

    if money["pays_work_done_on_termination"] is False:
        add("no_pay_on_termination", "中止したときに実施済みの実働を支払わない定めになっている。中止時の精算を決める")
    elif money["pays_work_done_on_termination"] is None:
        add("termination_settlement_unchecked", "中止時に実施済みの実働を支払うかを決めていない")

    if payment["due_date"] is None:
        add("payment_due_missing", "支払期日を決めていない。着手前に確定させる項目の先頭に置く")
    elif payment["days_from_delivery"] is None:
        add("delivery_date_missing", "受領日が入っていないため、支払期日までの日数を数えていない")
    elif payment["exceeds_reference"] is True:
        add(
            "payment_term_exceeds_reference",
            f"受領から支払期日まで{payment['days_from_delivery']}日で、確認した参照日数"
            f"（{payment['reference_term_days']}日）を超える。公表資料で現在の定めを確認し、支払期日を見直す",
        )
    elif payment["reference_term_days"] is None:
        add("payment_term_not_compared", "支払期日までの日数を出したが、参照する上限を一次情報で確認していないため比較していない")

    revision_item = next(item for item in checklist if item["code"] == "revision_limit")
    if revision_item["applicable"] is not False:
        # 回数0は「修正なしで合意した」であり、時間の上限がなくても範囲は閉じている。
        no_revisions = revisions["rounds"] == 0
        if not no_revisions and (revisions["rounds"] is None or revisions["hours"] is None):
            add(
                "revision_scope_open_ended",
                "修正の回数または時間の上限を決めていない。「納得するまで」を、確認できる品質と有限の修正範囲に具体化する",
            )
        if revisions["unpaid"] is True and not no_revisions:
            add("unpaid_revisions", "修正を無償にしている。合意した範囲の修正は実働として報酬に含めるか、範囲外として扱う")

    # 成果への満足で支払いや減額を判断するつもりなら、検収の基準と担当が書面にあることが前提になる。
    inspection = next(item for item in checklist if item["code"] == "inspection")
    if money["conditional_on_outcome"] is True and inspection["status"] != "stated":
        add(
            "inspection_missing_for_quality_judgement",
            "成果で支払いを判断しようとしているのに、検収の基準・担当・期日が書面にない。"
            "書面の検収基準がなければ減額の根拠にならない",
        )

    after_trial = next(item for item in checklist if item["code"] == "after_trial")
    if after_trial["status"] != "stated":
        add("after_trial_unstated", "体験後の扱い（採用や継続を保証しないこと）が書かれていないか未確認である")

    if termination["company_may_terminate"] is True and termination["candidate_may_terminate"] is False:
        add("termination_one_sided", "中途解除の定めが企業側だけにある。候補者側の解除と予告も定める")
    elif termination["company_may_terminate"] is None and termination["candidate_may_terminate"] is None:
        add("termination_unchecked", "中途解除を双方がどう扱うかを決めていない")

    return flags


def decide_readiness(flags: list[dict[str, Any]]) -> dict[str, Any]:
    blocking_codes = {
        "employment_not_contract_work",
        "nothing_in_writing_yet",
        "document_not_in_writing",
        "start_required_missing",
        "start_required_unclear",
        "start_required_unchecked",
        "start_required_not_in_writing",
        "compensation_basis_unknown",
        "payment_conditional_on_outcome",
        "no_pay_on_termination",
        "payment_due_missing",
        "payment_term_exceeds_reference",
        "revision_scope_open_ended",
        "termination_one_sided",
        "inspection_missing_for_quality_judgement",
    }
    blockers = [flag["code"] for flag in flags if flag["code"] in blocking_codes]
    return {
        "status": "needs_work" if blockers else "ready_for_owner_review",
        "blockers": blockers,
        # 契約の締結と候補者への提示は利用者が行う。
        "offering_is_user_action": True,
    }


def check(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    engagement = optional_choice(data.get("engagement"), "engagement", ENGAGEMENTS, "unknown")
    document = parse_document(data.get("document"))
    items = parse_items(data.get("items"))
    compensation = parse_compensation(data.get("compensation"))
    payment = parse_payment(data.get("payment"))
    revisions = parse_revisions(data.get("revisions"))
    termination = parse_termination(data.get("termination"))

    checklist = build_checklist(items)
    money = build_money(compensation)
    payment_view = build_payment(payment)
    flags = collect_flags(engagement, document, checklist, money, payment_view, revisions, termination)

    start_items = [item for item in checklist if item["start_required"] and item["applicable"] is not False]
    return {
        "as_of": optional_text(data.get("as_of"), "as_of"),
        "engagement": engagement,
        "document": {
            "form": document["form"],
            "in_writing": document["in_writing"],
            "planned_start": document["planned_start"].isoformat() if document["planned_start"] else None,
        },
        "summary": {
            "start_required_total": len(start_items),
            "start_required_stated_in_writing": sum(
                1 for item in start_items if item["status"] == "stated" and item["in_writing"]
            ),
            "start_required_open": sum(1 for item in start_items if item["status"] != "stated"),
        },
        "checklist": checklist,
        "money": money,
        "payment": payment_view,
        "revisions": {
            "rounds": revisions["rounds"],
            "hours": float(revisions["hours"]) if revisions["hours"] is not None else None,
            "unpaid": revisions["unpaid"],
        },
        "termination": termination,
        "readiness": decide_readiness(flags),
        "flags": flags,
    }


if __name__ == "__main__":
    raise SystemExit(run_cli(check, __doc__))
