#!/usr/bin/env python3
"""Lay out how a job search fits around a current job, without choosing where to apply.

週に使える時間と予定している活動を突き合わせ、平日日中の枠が要る活動を示し、
使う経路ごとに公開範囲と取り決めの確認状況を並べ、応募ごとの段階・次の行動・
期限を1つの表に揃える。応募先の推薦、求人の評価、合否の見込みは出さない。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from _common import (
    flag_collector,
    optional_bool,
    optional_choice,
    optional_date,
    optional_number,
    optional_text,
    require_list,
    require_object,
    require_text,
    run_cli,
    strip_whitespace,
)


# 応募の段階。`offer` までを進行中として扱い、次の行動の有無を見る。
STAGES = (
    "considering",
    "preparing",
    "applied",
    "interviewing",
    "offer",
    "accepted",
    "not_selected",
    "withdrawn",
)
ACTIVE_STAGES = ("considering", "preparing", "applied", "interviewing", "offer")

# 経路の種類。特定のサービスを推薦せず、開示範囲と取り決めの確認に使う。
CHANNEL_KINDS = (
    "direct",
    "job_board",
    "scout_site",
    "agent",
    "referral",
    "public_service",
    "other",
)
# 第三者が間に入る経路。同一企業への他経路の応募や辞退の連絡先に取り決めがありうる。
INTERMEDIATED_KINDS = ("agent", "referral")
# 経歴やプロフィールが閲覧される設定を持ちうる経路。公開かどうか未確認なら確認を促す。
PROFILE_CAPABLE_KINDS = ("job_board", "scout_site")
# 公開プロフィールが現職に見えないよう設定できているか。
BLOCK_STATES = ("yes", "no", "unknown", "not_applicable")

HOUR = Decimal("0.01")


def as_hours(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(HOUR))


def days_from(as_of: date | None, target: date | None) -> int | None:
    if as_of is None or target is None:
        return None
    return (target - as_of).days


def parse_activities(raw: object) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "activities")
    activities = []
    for index, entry in enumerate(entries):
        path = f"activities[{index}]"
        item = require_object(entry, path)
        activities.append(
            {
                "label": require_text(item.get("label"), f"{path}.label"),
                "weekly_hours": optional_number(item.get("weekly_hours"), f"{path}.weekly_hours"),
                # 平日の日中にしかできない活動か（対面の面接、平日のみの窓口など）。
                "weekday_daytime": optional_bool(item.get("weekday_daytime"), f"{path}.weekday_daytime"),
            }
        )
    return activities


def parse_channels(raw: object) -> dict[str, dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "channels")
    channels: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        path = f"channels[{index}]"
        item = require_object(entry, path)
        channel_id = require_text(item.get("id"), f"{path}.id")
        if channel_id in channels:
            raise ValueError(f"{path}.id is duplicated: {channel_id!r}")
        kind = optional_choice(item.get("kind"), f"{path}.kind", CHANNEL_KINDS, "other")
        blocked = optional_choice(
            item.get("current_employer_blocked"), f"{path}.current_employer_blocked", BLOCK_STATES, "unknown"
        )
        channels[channel_id] = {
            "id": channel_id,
            "kind": kind,
            "label": optional_text(item.get("label"), f"{path}.label") or channel_id,
            # 経歴やプロフィールが検索・閲覧される設定になっているか。
            "profile_public": optional_bool(item.get("profile_public"), f"{path}.profile_public"),
            "current_employer_blocked": blocked,
            # 同一企業への他経路の応募、辞退の連絡先などの取り決めを本人が確認したか。
            "terms_confirmed": optional_bool(item.get("terms_confirmed"), f"{path}.terms_confirmed"),
        }
    return channels


def parse_applications(raw: object, channels: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    entries = require_list(raw if raw is not None else [], "applications")
    applications = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        path = f"applications[{index}]"
        item = require_object(entry, path)
        application_id = require_text(item.get("id"), f"{path}.id")
        if application_id in seen:
            raise ValueError(f"{path}.id is duplicated: {application_id!r}")
        seen.add(application_id)
        stage = optional_choice(item.get("stage"), f"{path}.stage", STAGES, "considering")
        channel = optional_text(item.get("channel"), f"{path}.channel")
        if channel is not None and channel not in channels:
            raise ValueError(f"{path}.channel refers to an unknown channel: {channel!r}")
        applications.append(
            {
                "id": application_id,
                "employer": require_text(item.get("employer"), f"{path}.employer"),
                "channel": channel,
                "stage": stage,
                "next_action": optional_text(item.get("next_action"), f"{path}.next_action"),
                "next_action_by": optional_date(item.get("next_action_by"), f"{path}.next_action_by"),
                # 相手が示した回答・提出の期限。内定の回答期限もここに入れる。
                "reply_deadline": optional_date(item.get("reply_deadline"), f"{path}.reply_deadline"),
                # 辞退・取り下げを相手に伝えたか。`withdrawn` のときだけ意味を持つ。
                "notified": optional_bool(item.get("notified"), f"{path}.notified"),
            }
        )
    return applications


def parse_text_list(raw: object, path: str) -> list[str]:
    entries = require_list(raw if raw is not None else [], path)
    return [require_text(entry, f"{path}[{index}]") for index, entry in enumerate(entries)]


def sum_weekly_hours(activities: list[dict[str, Any]]) -> Decimal | None:
    hours = [item["weekly_hours"] for item in activities if item["weekly_hours"] is not None]
    if not hours:
        return None
    return sum(hours, Decimal(0))


def employers_via_multiple_channels(applications: list[dict[str, Any]]) -> list[str]:
    channels_by_employer: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for item in applications:
        if item["stage"] not in ACTIVE_STAGES or item["channel"] is None:
            continue
        key = strip_whitespace(item["employer"])
        labels.setdefault(key, item["employer"])
        channels_by_employer.setdefault(key, set()).add(item["channel"])
    return [labels[key] for key, used in channels_by_employer.items() if len(used) > 1]


def collect_flags(
    *,
    employed: bool | None,
    available: Decimal | None,
    planned: Decimal | None,
    weekday_daytime_available: bool | None,
    activities: list[dict[str, Any]],
    channels: dict[str, dict[str, Any]],
    applications: list[dict[str, Any]],
    days_to_review: int | None,
    review_date: date | None,
    stop_conditions: list[str],
) -> list[dict[str, Any]]:
    flags, add = flag_collector()

    if available is None:
        add("weekly_hours_not_stated", "週に使える時間が決まっていない。活動量を本人の時間から決められない")
    elif planned is not None and planned > available:
        add(
            "weekly_hours_exceeded",
            "予定している活動の合計が、週に使える時間を超えている。活動を減らすか時間を増やすかは本人が決める",
        )
    unpriced = [item["label"] for item in activities if item["weekly_hours"] is None]
    if unpriced:
        add("activity_hours_not_stated", "時間の見積もりがない活動がある。合計に入っていない", unpriced)

    weekday_needed = [item["label"] for item in activities if item["weekday_daytime"]]
    if weekday_needed and employed is not False and weekday_daytime_available is not True:
        add(
            "weekday_daytime_unconfirmed",
            "平日日中の枠が要る活動があるが、在職中にその枠を作れるかが未確認。有給・半休・時間休の扱いは就業規則で確認する",
            weekday_needed,
        )

    public_unblocked = [
        channel["label"]
        for channel in channels.values()
        if channel["profile_public"] and channel["current_employer_blocked"] != "yes"
    ]
    if public_unblocked:
        add(
            "profile_public_without_block",
            "経歴が公開される経路で、現職から見えない設定が未確認または未設定。公開範囲は本人が設定する",
            public_unblocked,
        )
    # 公開かどうか自体が未確認の経路。未確認を非公開と読み替えない。
    visibility_unknown = [
        channel["label"]
        for channel in channels.values()
        if channel["profile_public"] is None
        and channel["kind"] in PROFILE_CAPABLE_KINDS
        and channel["current_employer_blocked"] != "yes"
    ]
    if visibility_unknown:
        add(
            "profile_visibility_unknown",
            "経歴が閲覧されうる経路で、公開設定が未確認。公開されているか、現職から見えない設定かを本人が確認する",
            visibility_unknown,
        )
    terms_unconfirmed = [
        channel["label"]
        for channel in channels.values()
        if channel["kind"] in INTERMEDIATED_KINDS and channel["terms_confirmed"] is not True
    ]
    if terms_unconfirmed:
        add(
            "channel_terms_unconfirmed",
            "第三者が間に入る経路で、同一企業への他経路の応募や辞退の連絡先の取り決めが未確認",
            terms_unconfirmed,
        )

    channel_unknown = [
        item["id"]
        for item in applications
        if item["stage"] in ACTIVE_STAGES and item["channel"] is None
    ]
    if channel_unknown:
        add(
            "application_channel_unknown",
            "経路が記録されていない進行中の応募がある。同一企業の複数経路の検出に入らない",
            channel_unknown,
        )
    duplicated = employers_via_multiple_channels(applications)
    if duplicated:
        add(
            "same_employer_multiple_channels",
            "同じ企業に複数の経路で進んでいる。経路ごとの取り決めと、どちらで続けるかを確認できる",
            duplicated,
        )

    without_next = [
        item["id"]
        for item in applications
        if item["stage"] in ACTIVE_STAGES and item["next_action"] is None
    ]
    if without_next:
        add("application_without_next_action", "進行中だが次の行動が決まっていない応募がある", without_next)
    # 行動はあるが予定日がない応募は、日付順の一覧（due）に載らない。
    undated_next = [
        item["id"]
        for item in applications
        if item["stage"] in ACTIVE_STAGES
        and item["next_action"] is not None
        and item["next_action_by"] is None
    ]
    if undated_next:
        add(
            "next_action_undated",
            "次の行動はあるが予定日が決まっていない応募がある。日付順の一覧に載らない",
            undated_next,
        )
    overdue = [
        item["id"]
        for item in applications
        if item["stage"] in ACTIVE_STAGES
        and item["days_until_next_action"] is not None
        and item["days_until_next_action"] < 0
    ]
    if overdue:
        add("next_action_overdue", "次の行動の予定日を過ぎている応募がある", overdue)
    deadline_passed = [
        item["id"]
        for item in applications
        if item["stage"] in ACTIVE_STAGES
        and item["days_until_reply_deadline"] is not None
        and item["days_until_reply_deadline"] < 0
    ]
    if deadline_passed:
        add("reply_deadline_passed", "相手が示した期限を過ぎている応募がある。状況の確認は本人が行う", deadline_passed)

    offers = [item["id"] for item in applications if item["stage"] == "offer"]
    if offers:
        add(
            "offer_awaiting_reply",
            "回答していない内定がある。条件の確認は offer-terms-check、辞退が必要なら offer-decline の範囲",
            offers,
        )
    unnotified = [
        item["id"]
        for item in applications
        if item["stage"] == "withdrawn" and item["notified"] is False
    ]
    if unnotified:
        add("withdrawal_not_notified", "辞退・取り下げを決めたが相手に伝えていない応募がある。連絡は本人が行う", unnotified)
    # 伝えたかどうか未記録の辞退。未記録を連絡済みと読み替えない。
    notification_unknown = [
        item["id"]
        for item in applications
        if item["stage"] == "withdrawn" and item["notified"] is None
    ]
    if notification_unknown:
        add(
            "withdrawal_notification_unknown",
            "辞退・取り下げを相手に伝えたかが記録されていない応募がある。伝えていなければ連絡は本人が行う",
            notification_unknown,
        )

    if review_date is None:
        add("review_date_not_set", "活動を見直す日が決まっていない。続けるか、減らすか、止めるかを考える区切りがない")
    elif days_to_review is not None and days_to_review < 0:
        add("review_date_passed", "見直す日を過ぎている。続けるかどうかを本人が選び直せる")
    if not stop_conditions:
        add("stop_conditions_not_stated", "負担が増えたときに止める・減らす条件が決まっていない")

    return flags


def plan_job_search(payload: object) -> dict[str, Any]:
    data = require_object(payload, "input")
    as_of = optional_date(data.get("as_of"), "as_of")
    employed = optional_bool(data.get("employed"), "employed")
    available = optional_number(data.get("weekly_hours_available"), "weekly_hours_available")
    weekday_daytime_available = optional_bool(
        data.get("weekday_daytime_available"), "weekday_daytime_available"
    )
    review_date = optional_date(data.get("review_date"), "review_date")
    stop_conditions = parse_text_list(data.get("stop_conditions"), "stop_conditions")

    activities = parse_activities(data.get("activities"))
    channels = parse_channels(data.get("channels"))
    applications = parse_applications(data.get("applications"), channels)
    for item in applications:
        item["days_until_next_action"] = days_from(as_of, item["next_action_by"])
        item["days_until_reply_deadline"] = days_from(as_of, item["reply_deadline"])

    planned = sum_weekly_hours(activities)
    margin = available - planned if available is not None and planned is not None else None
    days_to_review = days_from(as_of, review_date)

    stage_counts = {stage: sum(1 for item in applications if item["stage"] == stage) for stage in STAGES}

    # 次の行動と相手の期限を、日付の近い順に1つの一覧にする。
    due_items = []
    for item in applications:
        if item["stage"] not in ACTIVE_STAGES:
            continue
        if item["next_action_by"] is not None:
            due_items.append(
                {
                    "date": item["next_action_by"].isoformat(),
                    "days_until": item["days_until_next_action"],
                    "application": item["id"],
                    "employer": item["employer"],
                    "what": item["next_action"] or "次の行動（未記入）",
                    "set_by": "self",
                }
            )
        if item["reply_deadline"] is not None:
            due_items.append(
                {
                    "date": item["reply_deadline"].isoformat(),
                    "days_until": item["days_until_reply_deadline"],
                    "application": item["id"],
                    "employer": item["employer"],
                    "what": "相手が示した回答・提出の期限",
                    "set_by": "counterpart",
                }
            )
    due_items.sort(key=lambda item: item["date"])

    return {
        "as_of": data.get("as_of"),
        "summary": {
            "employed": employed,
            "weekly_hours_available": as_hours(available),
            "weekly_hours_planned": as_hours(planned),
            "weekly_hours_margin": as_hours(margin),
            "applications_active": sum(stage_counts[stage] for stage in ACTIVE_STAGES),
            "applications_by_stage": stage_counts,
            "channels": len(channels),
            "days_to_review": days_to_review,
        },
        "time": {
            "weekly_hours_available": as_hours(available),
            "weekday_daytime_available": weekday_daytime_available,
            "activities": [
                {
                    "label": item["label"],
                    "weekly_hours": as_hours(item["weekly_hours"]),
                    "weekday_daytime": item["weekday_daytime"],
                }
                for item in activities
            ],
        },
        "channels": list(channels.values()),
        "applications": [
            {
                "id": item["id"],
                "employer": item["employer"],
                "channel": item["channel"],
                "stage": item["stage"],
                "next_action": item["next_action"],
                "next_action_by": item["next_action_by"].isoformat() if item["next_action_by"] else None,
                "days_until_next_action": item["days_until_next_action"],
                "reply_deadline": item["reply_deadline"].isoformat() if item["reply_deadline"] else None,
                "days_until_reply_deadline": item["days_until_reply_deadline"],
                "notified": item["notified"],
            }
            for item in applications
        ],
        "due": due_items,
        "review": {
            "review_date": review_date.isoformat() if review_date else None,
            "days_to_review": days_to_review,
            "stop_conditions": stop_conditions,
        },
        "flags": collect_flags(
            employed=employed,
            available=available,
            planned=planned,
            weekday_daytime_available=weekday_daytime_available,
            activities=activities,
            channels=channels,
            applications=applications,
            days_to_review=days_to_review,
            review_date=review_date,
            stop_conditions=stop_conditions,
        ),
        "notes": [
            "この出力は活動の段取りの点検であり、応募先の推薦、求人の評価、合否の見込みではない",
            "応募の本数や経路の良し悪しは判定しない。時間と負担の範囲で本人が決める",
            "応募の送信、プロフィールの公開設定、エージェントへの連絡、辞退の連絡は本人が行う",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    return run_cli(plan_job_search, __doc__, argv)


if __name__ == "__main__":
    raise SystemExit(main())
