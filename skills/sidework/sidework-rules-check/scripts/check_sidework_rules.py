#!/usr/bin/env python3
"""Check what an employer's own rules require before starting side work.

勤務先の規程について、確認できている項目と根拠のない項目を数え、計画している
副業が触れうる義務を並べ、本業と副業を合わせた週の稼働を合算し、申請・届出に
必要な材料の欠落を出す。副業の可否も、規定の適法性も判定しない。制度側の扱い
（労働時間の通算、社会保険、税）は時点で変わるため、一次情報で確認する。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_int,
    optional_number,
    optional_text,
    require_list,
    require_object,
    run_cli,
)


STATUSES = ("private_employee", "public_servant", "self_employed", "student", "unknown")
ENGAGEMENTS = ("employment", "contract_work", "own_business", "investment", "unknown")
REGIMES = ("prohibited", "permission", "notification", "silent", "unknown")
RULE_SOURCES = (
    "employment_rules",
    "sidework_policy",
    "contract",
    "pledge",
    "hearsay",
    "not_found",
    "unknown",
)
# 規程の本文にあたるもの。伝聞と未確認は根拠にしない。
DOCUMENTED_SOURCES = ("employment_rules", "sidework_policy", "contract", "pledge")
ITEM_STATUSES = ("stated", "missing", "unclear", "unknown")
TOUCH_VALUES = ("yes", "no", "unknown")
APPLICATION_STATUSES = ("ready", "draft", "missing")

# 申請・届出そのものが成り立つ規定の型。禁止と規定なしには手続きがない。
APPLICATION_REGIMES = ("permission", "notification")
# 許可の判断基準と取消の条件は、許可制のときだけ確認できる。
PERMISSION_REGIME = ("permission",)

# (code, label, group, requires)
# requires は None（常に対象）、または (基準, 対象になる値) の組で、基準は
# `status` / `engagement` / `regime` のいずれか。基準になる値が unknown のときは
# 対象かどうかを判定せず、対象として扱ったうえで注記する。
CHECKLIST: tuple[tuple[str, str, str, tuple[str, tuple[str, ...]] | None], ...] = (
    ("sidework_clause", "副業・兼業に関する定めの有無と本文", "rules", None),
    ("regime_type", "禁止・許可制・届出制の別と、その条件", "rules", None),
    ("scope_of_rule", "規定が対象にする範囲", "rules", None),
    ("sanctions", "定めに反したときの取扱い", "rules", None),
    ("public_servant_permission", "許可・承認の要否と根拠規定", "rules", ("status", ("public_servant",))),
    ("application_procedure", "申請・届出の様式、提出先、時期", "procedure", ("regime", APPLICATION_REGIMES)),
    ("approval_criteria", "許可・受理の判断基準", "procedure", ("regime", PERMISSION_REGIME)),
    ("revocation_conditions", "許可の取消・変更の条件", "procedure", ("regime", PERMISSION_REGIME)),
    ("ongoing_report", "開始後の報告義務", "procedure", ("regime", APPLICATION_REGIMES)),
    ("competition_clause", "競業避止に関する定め", "duty", None),
    ("confidentiality_clause", "秘密保持の対象と範囲", "duty", None),
    ("dedication_clause", "職務専念・勤務時間中の取扱い", "duty", None),
    ("asset_use_clause", "会社の設備、データ、アカウントの利用", "duty", None),
    ("reputation_clause", "会社の信用・名称・肩書の使用に関する定め", "duty", None),
    ("ip_clause", "職務に関する成果物・発明の取扱い", "duty", None),
    ("customer_clause", "取引先・顧客に関する制限", "duty", None),
    ("hours_aggregation", "労働時間の通算と割増賃金の扱い", "external", ("engagement", ("employment",))),
    ("employment_insurance", "雇用保険の扱い", "external", ("engagement", ("employment",))),
    ("social_insurance", "健康保険・厚生年金の適用と届出", "external", None),
    ("workers_accident", "労災、通勤災害の扱い", "external", None),
    ("tax_filing", "確定申告と住民税の扱い", "external", None),
    (
        "liability_insurance",
        "賠償責任を誰が負うか",
        "external",
        ("engagement", ("contract_work", "own_business")),
    ),
)
CHECKLIST_CODES = {code for code, _, _, _ in CHECKLIST}

# 副業の中身が触れうる論点。(key, label, 触れるときに確認する義務の項目)
TOUCHPOINTS: tuple[tuple[str, str, str], ...] = (
    ("same_industry", "副業先が勤務先と競合する", "competition_clause"),
    ("counterparty_is_client", "副業先が勤務先の取引先・顧客である", "customer_clause"),
    ("uses_employer_information", "本業で知った情報や資料を使う", "confidentiality_clause"),
    ("uses_employer_assets", "会社の設備、回線、アカウントを使う", "asset_use_clause"),
    ("during_work_hours", "勤務時間中に連絡や作業が発生する", "dedication_clause"),
    ("uses_employer_name", "勤務先の名前や在籍を出して活動する", "reputation_clause"),
)
TOUCHPOINT_KEYS = {key for key, _, _ in TOUCHPOINTS}

# 申請・届出で申告を求められることが多い記載事項。
APPLICATION_FACTS: tuple[tuple[str, str], ...] = (
    ("counterparty", "副業先の名称と事業内容"),
    ("work_content", "担当する業務の内容"),
    ("engagement_form", "契約の形態"),
    ("schedule", "稼働する曜日と時間帯"),
    ("weekly_hours", "週あたりの稼働時間"),
    ("period", "開始日と期間"),
    ("income", "見込みの報酬"),
    ("conflict_statement", "競業・秘密保持に触れないことの説明"),
    ("impact_plan", "本業への影響を避ける具体策"),
)
APPLICATION_CODES = {code for code, _ in APPLICATION_FACTS}

DEFAULT_REFERENCE_WEEKLY_HOURS = Decimal(40)
WEEKS_PER_MONTH = Decimal(52) / Decimal(12)
DAYS_PER_WEEK = 7
HOUR = Decimal("0.01")


def as_hours(value: Decimal | None) -> float | None:
    """時間を0.01単位に丸めて返す。None は None のままにする。"""
    if value is None:
        return None
    return float(value.quantize(HOUR))


def parse_choice(value: object, path: str, allowed: tuple[str, ...], default: str) -> str:
    if value is None:
        return default
    if value not in allowed:
        raise ValueError(f"{path} must be one of {list(allowed)}")
    return str(value)


def parse_rules(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "rules")
    return {
        "source": parse_choice(block.get("source"), "rules.source", RULE_SOURCES, "unknown"),
        "reviewed": optional_bool(block.get("reviewed"), "rules.reviewed"),
        "regime": parse_choice(block.get("regime"), "rules.regime", REGIMES, "unknown"),
        "clause_quoted": optional_bool(block.get("clause_quoted"), "rules.clause_quoted"),
    }


def parse_sidework(raw: object) -> dict[str, str]:
    block = require_object(raw if raw is not None else {}, "sidework")
    unknown_keys = sorted(set(block) - TOUCHPOINT_KEYS)
    if unknown_keys:
        raise ValueError(f"sidework has unknown keys: {unknown_keys}")
    return {
        key: parse_choice(block.get(key), f"sidework.{key}", TOUCH_VALUES, "unknown")
        for key in TOUCHPOINT_KEYS
    }


def parse_hours(raw: object) -> dict[str, Any]:
    block = require_object(raw if raw is not None else {}, "hours")
    rest_days = optional_int(block.get("rest_days_per_week"), "hours.rest_days_per_week")
    if rest_days is not None and rest_days > DAYS_PER_WEEK:
        raise ValueError("hours.rest_days_per_week must not exceed 7")
    reference = optional_number(
        block.get("reference_weekly_hours"), "hours.reference_weekly_hours", allow_zero=False
    )
    return {
        "main_scheduled_weekly": optional_number(
            block.get("main_scheduled_weekly"), "hours.main_scheduled_weekly"
        ),
        "main_overtime_weekly": optional_number(
            block.get("main_overtime_weekly"), "hours.main_overtime_weekly"
        ),
        "sidework_weekly": optional_number(block.get("sidework_weekly"), "hours.sidework_weekly"),
        "rest_days_per_week": rest_days,
        "reference_weekly_hours": reference if reference is not None else DEFAULT_REFERENCE_WEEKLY_HOURS,
        "reference_supplied": reference is not None,
        "health_reference_monthly_hours": optional_number(
            block.get("health_reference_monthly_hours"),
            "hours.health_reference_monthly_hours",
            allow_zero=False,
        ),
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
        if source is not None and source not in RULE_SOURCES:
            raise ValueError(f"{path}.source must be one of {list(RULE_SOURCES)}")
        parsed[str(code)] = {
            "status": parse_choice(item.get("status"), f"{path}.status", ITEM_STATUSES, "unknown"),
            "source": source,
            "note": optional_text(item.get("note"), f"{path}.note"),
        }
    return parsed


def parse_application(raw: object) -> dict[str, str]:
    entries = require_list(raw if raw is not None else [], "application")
    parsed: dict[str, str] = {}
    for index, entry in enumerate(entries):
        path = f"application[{index}]"
        item = require_object(entry, path)
        code = item.get("code")
        if code not in APPLICATION_CODES:
            raise ValueError(f"{path}.code is not a known application code: {code!r}")
        if code in parsed:
            raise ValueError(f"{path}.code is duplicated: {code!r}")
        parsed[str(code)] = parse_choice(
            item.get("status"), f"{path}.status", APPLICATION_STATUSES, "missing"
        )
    return parsed


def item_applies(
    requires: tuple[str, tuple[str, ...]] | None, status: str, engagement: str, regime: str
) -> bool | None:
    """項目が対象かどうか。基準になる値が未確認なら None（判定しない）を返す。"""
    if requires is None:
        return True
    kind, accepted = requires
    actual = {"status": status, "engagement": engagement, "regime": regime}[kind]
    if actual == "unknown":
        return None
    return actual in accepted


def build_checklist(
    items: dict[str, dict[str, Any]], status: str, engagement: str, regime: str
) -> list[dict[str, Any]]:
    checklist = []
    for code, label, group, requires in CHECKLIST:
        applies = item_applies(requires, status, engagement, regime)
        entry = items.get(code)
        checklist.append(
            {
                "code": code,
                "label": label,
                "group": group,
                # None は「対象かどうかを判定していない」。対象外と混同しない。
                "applicable": applies,
                "status": entry["status"] if entry else "unknown",
                "source": entry["source"] if entry else None,
                "note": entry["note"] if entry else None,
            }
        )
    return checklist


def build_hours(hours: dict[str, Any], engagement: str) -> dict[str, Any]:
    main = hours["main_scheduled_weekly"]
    overtime = hours["main_overtime_weekly"]
    side = hours["sidework_weekly"]
    reference = hours["reference_weekly_hours"]

    missing = [
        name
        for name, value in (
            ("main_scheduled_weekly", main),
            ("main_overtime_weekly", overtime),
            ("sidework_weekly", side),
        )
        if value is None
    ]
    total = None if missing else main + overtime + side
    over_weekly = None if total is None else max(Decimal(0), total - reference)
    over_monthly = None if over_weekly is None else over_weekly * WEEKS_PER_MONTH

    # 所定どうしの合計。残業を含めない。雇用型の副業では、ここが基準を超えると
    # 通算と割増賃金の負担が論点になる。
    scheduled_total = None if main is None or side is None else main + side

    health_reference = hours["health_reference_monthly_hours"]
    over_health_reference = None
    if health_reference is not None and over_monthly is not None:
        over_health_reference = over_monthly > health_reference

    return {
        "main_scheduled_weekly": as_hours(main),
        "main_overtime_weekly": as_hours(overtime),
        "sidework_weekly": as_hours(side),
        "missing_inputs": missing,
        "total_weekly": as_hours(total),
        "scheduled_total_weekly": as_hours(scheduled_total),
        "reference_weekly_hours": as_hours(reference),
        "reference_supplied": hours["reference_supplied"],
        "over_reference_weekly": as_hours(over_weekly),
        "over_reference_monthly": as_hours(over_monthly),
        "health_reference_monthly_hours": as_hours(health_reference),
        "over_health_reference": over_health_reference,
        "rest_days_per_week": hours["rest_days_per_week"],
        "aggregation_applies_to_engagement": engagement in ("employment", "unknown"),
    }


def build_application(
    application: dict[str, str], regime: str
) -> tuple[list[dict[str, Any]], bool | None]:
    """申請材料の一覧と、それが要るかどうかを返す。

    規定の型が未確認のときは要否も決まらないため None を返す。対象外（禁止・
    規定なし）と混同しない。
    """
    required = None if regime == "unknown" else regime in APPLICATION_REGIMES
    entries = [
        {
            "code": code,
            "label": label,
            "status": application.get(code, "missing"),
        }
        for code, label in APPLICATION_FACTS
    ]
    return entries, required


def collect_flags(
    status: str,
    engagement: str,
    rules: dict[str, Any],
    checklist: list[dict[str, Any]],
    touchpoints: list[dict[str, Any]],
    hours: dict[str, Any],
    application: list[dict[str, Any]],
    application_required: bool | None,
) -> list[dict[str, Any]]:
    flags, add = flag_collector()

    if rules["reviewed"] is not True or rules["source"] not in DOCUMENTED_SOURCES:
        add(
            "rules_not_reviewed",
            "規程の本文を読んだことが確認できていない。伝聞や前例は根拠にならず、"
            "この時点では規定の内容はすべて未確認である",
        )
    elif rules["clause_quoted"] is not True:
        add(
            "clause_not_quoted",
            "規程の原文を書き写していない。要約すると但し書きと許可の条件が落ちる",
        )

    if rules["source"] == "not_found":
        add(
            "rules_not_found",
            "探した範囲で副業の定めが見当たらなかった。定めがないことを許可と読み替えず、"
            "競業・秘密保持・職務専念の定めを個別に読む",
        )

    if rules["regime"] == "prohibited":
        add(
            "regime_prohibited",
            "規程の上では禁止と書かれている。適用範囲、但し書き、相談窓口を確認する。"
            "規定が有効かどうかはこのスキルでは判定しない",
        )
    elif rules["regime"] == "unknown":
        add("regime_unknown", "禁止・許可制・届出制の別が確定していない。手続きが決まらない")
    elif rules["regime"] == "silent":
        add(
            "regime_silent",
            "副業についての定めが見当たらない状態である。許可されていることと同じに扱わない",
        )

    if status == "public_servant":
        add(
            "public_servant_rules_differ",
            "公務員は法律に基づく制限がある。民間の就業規則の判断を当てはめず、"
            "所属先の根拠規定と許可・承認の要否を公表資料で確認する",
        )
    elif status == "unknown":
        add("status_unknown", "立場が未確認である。適用される定めが決まらない")

    if engagement == "unknown":
        add(
            "engagement_unknown",
            "副業の型が未確認である。労働時間の通算、社会保険、確定申告の論点を絞れない",
        )

    touching = [point["label"] for point in touchpoints if point["state"] == "yes"]
    if touching:
        add(
            "duties_possibly_touched",
            "計画している副業が、勤務先の定めに触れうる要素を含む。規程の文言に照らして確認する",
            touching,
        )
    undecided = [point["label"] for point in touchpoints if point["state"] == "unknown"]
    if undecided:
        add(
            "touchpoints_unknown",
            "該当するかどうかを確認していない要素がある。該当しないものとして扱わない",
            undecided,
        )

    unconfirmed = [
        entry["code"]
        for entry in checklist
        if entry["applicable"] is not False and entry["status"] == "unknown"
    ]
    if unconfirmed:
        add("items_unconfirmed", "確認していない項目がある", unconfirmed)

    unclear = [entry["code"] for entry in checklist if entry["status"] == "unclear"]
    if unclear:
        add("items_unclear", "記載はあるが読み取れない項目がある。質問に変える", unclear)

    undecidable = [entry["code"] for entry in checklist if entry["applicable"] is None]
    if undecidable:
        add(
            "applicability_undecidable",
            "立場または副業の型が未確認のため、対象かどうかを判定していない項目がある",
            undecidable,
        )

    if hours["missing_inputs"]:
        add(
            "combined_hours_missing",
            "週の稼働が揃っていない。合計を出していない",
            hours["missing_inputs"],
        )
    else:
        if hours["aggregation_applies_to_engagement"] and hours["scheduled_total_weekly"] is not None:
            if hours["scheduled_total_weekly"] > hours["reference_weekly_hours"]:
                add(
                    "scheduled_hours_over_reference",
                    f"本業と副業の所定を合わせると週{hours['scheduled_total_weekly']}時間で、"
                    f"基準の{hours['reference_weekly_hours']}時間を超える。雇用として働く場合は"
                    "労働時間の通算と割増賃金の負担が論点になる。両社に確認する",
                )
        if hours["over_health_reference"] is True:
            add(
                "over_health_reference",
                f"基準を超える分が月{hours['over_reference_monthly']}時間で、"
                f"入力した参照値{hours['health_reference_monthly_hours']}時間を上回る。"
                "健康と本業への影響を先に確認する",
            )
        elif hours["health_reference_monthly_hours"] is None:
            add(
                "health_reference_not_supplied",
                "健康確保のために参照する月あたりの時間を入力していない。"
                "判断に関わるなら一次情報で確認して入れ直す",
            )

    if hours["rest_days_per_week"] == 0:
        add(
            "no_rest_day",
            "本業も副業もしない日が週にない。計画として続くかを先に確認する",
        )
    elif hours["rest_days_per_week"] is None:
        add("rest_days_unknown", "本業も副業もしない日の数が入っていない")

    if application_required is not False:
        not_ready = [entry["code"] for entry in application if entry["status"] != "ready"]
        if not_ready:
            add(
                "application_facts_missing",
                "申請・届出に書く材料のうち、確定していないものがある。"
                "副業先に先に確認すべきものが含まれる",
                not_ready,
            )

    return flags


def check(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    status = parse_choice(data.get("status"), "status", STATUSES, "unknown")
    engagement = parse_choice(data.get("engagement"), "engagement", ENGAGEMENTS, "unknown")
    rules = parse_rules(data.get("rules"))
    sidework = parse_sidework(data.get("sidework"))
    hours_input = parse_hours(data.get("hours"))
    items = parse_items(data.get("items"))
    application_input = parse_application(data.get("application"))

    checklist = build_checklist(items, status, engagement, rules["regime"])
    touchpoints = [
        {"key": key, "label": label, "state": sidework[key], "clause": clause}
        for key, label, clause in TOUCHPOINTS
    ]
    hours = build_hours(hours_input, engagement)
    application, application_required = build_application(application_input, rules["regime"])

    in_scope = [entry for entry in checklist if entry["applicable"] is not False]
    documented = [
        entry
        for entry in in_scope
        if entry["status"] == "stated" and entry["source"] in DOCUMENTED_SOURCES
    ]

    return {
        "as_of": data.get("as_of"),
        "status": status,
        "engagement": engagement,
        "rules": rules,
        "checklist": checklist,
        "touchpoints": touchpoints,
        "hours": hours,
        "application": application,
        "application_required": application_required,
        "summary": {
            "items_in_scope": len(in_scope),
            "items_confirmed_in_documents": len(documented),
            "items_unknown": sum(1 for entry in in_scope if entry["status"] == "unknown"),
            "touchpoints_yes": sum(1 for point in touchpoints if point["state"] == "yes"),
            "touchpoints_unknown": sum(1 for point in touchpoints if point["state"] == "unknown"),
            "application_ready": sum(1 for entry in application if entry["status"] == "ready"),
            "application_total": len(application) if application_required is not False else 0,
        },
        "flags": collect_flags(
            status,
            engagement,
            rules,
            checklist,
            touchpoints,
            hours,
            application,
            application_required,
        ),
        "notes": [
            "この出力は確認の状況であって、副業の可否でも規定の適法性の判定でもない",
            "規程の本文で確認できた項目だけを確認済みとして数えている。伝聞は根拠に含めない",
            "労働時間の通算、社会保険、雇用保険、労災、税の扱いは時点で変わる。一次情報で確認する",
            "公務員は法律に基づく制限があり、民間の就業規則とは別に確認する",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(check, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
