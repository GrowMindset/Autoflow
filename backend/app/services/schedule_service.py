from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

APP_TIMEZONE_NAME = "Asia/Kolkata"
APP_TIMEZONE = ZoneInfo(APP_TIMEZONE_NAME)


class ScheduleConfigError(ValueError):
    """Raised when schedule trigger config cannot be parsed."""


MONTH_NAME_TO_INT = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

WEEKDAY_NAME_TO_INT = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}

SCHEDULE_INTERVALS = {"minutes", "hours", "days", "weeks", "months", "custom"}


def is_schedule_enabled(config: Mapping[str, Any] | None) -> bool:
    if not isinstance(config, Mapping):
        return False
    enabled_raw = config.get("enabled", True)
    if isinstance(enabled_raw, str):
        return enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(enabled_raw)


def build_cron_expression(config: Mapping[str, Any] | None) -> str:
    rules = _get_schedule_rules(config)
    if rules:
        for index, rule in enumerate(rules):
            if not _is_rule_enabled(rule):
                continue
            return _rule_to_display_expression(rule, index=index + 1)
        return _rule_to_display_expression(rules[0], index=1)

    if not isinstance(config, Mapping):
        return "* * * * *"

    cron = str(config.get("cron") or "").strip()
    if cron:
        return cron

    minute = str(config.get("minute") or "*").strip() or "*"
    hour = str(config.get("hour") or "*").strip() or "*"
    day_of_month = str(config.get("day_of_month") or "*").strip() or "*"
    month = str(config.get("month") or "*").strip() or "*"
    day_of_week = str(config.get("day_of_week") or "*").strip() or "*"
    return f"{minute} {hour} {day_of_month} {month} {day_of_week}"


def resolve_schedule_timezone(config: Mapping[str, Any] | None) -> str:
    if not isinstance(config, Mapping):
        return APP_TIMEZONE_NAME
    return str(config.get("timezone") or APP_TIMEZONE_NAME).strip() or APP_TIMEZONE_NAME


def is_schedule_due(
    config: Mapping[str, Any] | None,
    *,
    now_utc: datetime | None = None,
) -> bool:
    if not is_schedule_enabled(config):
        return False

    rules = _get_schedule_rules(config)
    timezone_name = resolve_schedule_timezone(config)
    now = now_utc or datetime.now(timezone.utc)

    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ScheduleConfigError(f"Unknown schedule timezone '{timezone_name}'.") from exc

    localized = now.astimezone(tz)
    if rules:
        for index, rule in enumerate(rules):
            if not _is_rule_enabled(rule):
                continue
            if _is_schedule_rule_due(rule, localized, index=index + 1):
                return True
        return False

    cron_expr = build_cron_expression(config)
    return _cron_expression_matches(cron_expr, localized)


def next_schedule_run_at(
    config: Mapping[str, Any] | None,
    *,
    now_utc: datetime | None = None,
    max_lookahead_minutes: int = 60 * 24 * 400,
) -> datetime | None:
    """
    Computes the next UTC datetime when this schedule becomes due.

    The returned datetime is always strictly after ``now_utc`` (or current UTC time).
    Returns ``None`` when schedule is disabled or no due time is found in lookahead window.
    """
    if not is_schedule_enabled(config):
        return None

    if max_lookahead_minutes < 1:
        max_lookahead_minutes = 1

    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    base = now.replace(second=0, microsecond=0)
    candidate = base + timedelta(minutes=1)

    for _ in range(max_lookahead_minutes):
        if is_schedule_due(config, now_utc=candidate):
            return candidate
        candidate += timedelta(minutes=1)

    return None


def build_schedule_payload(
    *,
    config: Mapping[str, Any] | None,
    node_id: str,
    fired_at_utc: datetime | None = None,
) -> dict[str, Any]:
    fired_at = fired_at_utc or datetime.now(timezone.utc)
    scheduled_at = fired_at.astimezone(APP_TIMEZONE).isoformat()
    return {
        "triggered": True,
        "trigger_type": "schedule",
        "schedule_node_id": node_id,
        "scheduled_at": scheduled_at,
        "schedule_timezone": resolve_schedule_timezone(config),
        "schedule_cron": build_cron_expression(config),
        "source": "schedule",
    }


def _get_schedule_rules(config: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(config, Mapping):
        return []
    raw_rules = config.get("rules")
    if not isinstance(raw_rules, list):
        return []
    rules: list[Mapping[str, Any]] = []
    for raw in raw_rules:
        if isinstance(raw, Mapping):
            rules.append(raw)
    return rules


def _is_rule_enabled(rule: Mapping[str, Any]) -> bool:
    enabled_raw = rule.get("enabled", True)
    if isinstance(enabled_raw, str):
        return enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(enabled_raw)


def _is_schedule_rule_due(
    rule: Mapping[str, Any],
    localized_now: datetime,
    *,
    index: int,
) -> bool:
    interval = str(rule.get("interval") or "").strip().lower()
    if interval not in SCHEDULE_INTERVALS:
        raise ScheduleConfigError(f"Schedule rule {index}: unsupported interval '{interval}'.")

    if interval == "custom":
        cron_expr = str(rule.get("cron") or "").strip()
        if not cron_expr:
            raise ScheduleConfigError(f"Schedule rule {index}: custom interval requires non-empty cron.")
        return _cron_expression_matches(cron_expr, localized_now)

    every = _coerce_int(
        rule.get("every", 1),
        minimum=1,
        maximum={
            "minutes": 59,
            "hours": 23,
            "days": 31,
            "weeks": 52,
            "months": 12,
        }[interval],
        rule_index=index,
        field="every",
    )
    trigger_minute = _coerce_int(
        rule.get("trigger_minute", 0),
        minimum=0,
        maximum=59,
        rule_index=index,
        field="trigger_minute",
    )

    if interval == "minutes":
        return localized_now.minute % every == 0

    if interval == "hours":
        return localized_now.minute == trigger_minute and (localized_now.hour % every == 0)

    trigger_hour = _coerce_int(
        rule.get("trigger_hour", 0),
        minimum=0,
        maximum=23,
        rule_index=index,
        field="trigger_hour",
    )
    if localized_now.hour != trigger_hour or localized_now.minute != trigger_minute:
        return False

    if interval == "days":
        return ((localized_now.day - 1) % every) == 0

    if interval == "weeks":
        target_weekday = _coerce_weekday(
            rule.get("trigger_weekday", 1),
            rule_index=index,
            field="trigger_weekday",
        )
        current_weekday = (localized_now.weekday() + 1) % 7
        if current_weekday != target_weekday:
            return False
        epoch_monday = date(1970, 1, 5)
        week_index = (localized_now.date() - epoch_monday).days // 7
        return week_index % every == 0

    if interval == "months":
        target_dom = _coerce_int(
            rule.get("trigger_day_of_month", 1),
            minimum=1,
            maximum=31,
            rule_index=index,
            field="trigger_day_of_month",
        )
        if localized_now.day != target_dom:
            return False
        month_index = localized_now.year * 12 + (localized_now.month - 1)
        return month_index % every == 0

    return False


def _rule_to_display_expression(rule: Mapping[str, Any], *, index: int) -> str:
    interval = str(rule.get("interval") or "").strip().lower()
    if interval not in SCHEDULE_INTERVALS:
        raise ScheduleConfigError(f"Schedule rule {index}: unsupported interval '{interval}'.")

    if interval == "custom":
        cron_expr = str(rule.get("cron") or "").strip()
        if not cron_expr:
            raise ScheduleConfigError(f"Schedule rule {index}: custom interval requires non-empty cron.")
        return cron_expr

    every = _coerce_int(
        rule.get("every", 1),
        minimum=1,
        maximum={
            "minutes": 59,
            "hours": 23,
            "days": 31,
            "weeks": 52,
            "months": 12,
        }[interval],
        rule_index=index,
        field="every",
    )
    trigger_minute = _coerce_int(
        rule.get("trigger_minute", 0),
        minimum=0,
        maximum=59,
        rule_index=index,
        field="trigger_minute",
    )

    if interval == "minutes":
        return "* * * * *" if every == 1 else f"*/{every} * * * *"

    if interval == "hours":
        hour_expr = "*" if every == 1 else f"*/{every}"
        return f"{trigger_minute} {hour_expr} * * *"

    trigger_hour = _coerce_int(
        rule.get("trigger_hour", 0),
        minimum=0,
        maximum=23,
        rule_index=index,
        field="trigger_hour",
    )
    if interval == "days":
        dom_expr = "*" if every == 1 else f"*/{every}"
        return f"{trigger_minute} {trigger_hour} {dom_expr} * *"

    if interval == "weeks":
        weekday = _coerce_weekday(
            rule.get("trigger_weekday", 1),
            rule_index=index,
            field="trigger_weekday",
        )
        # For every>1 this is only an approximate cron representation.
        return f"{trigger_minute} {trigger_hour} * * {weekday}"

    target_dom = _coerce_int(
        rule.get("trigger_day_of_month", 1),
        minimum=1,
        maximum=31,
        rule_index=index,
        field="trigger_day_of_month",
    )
    month_expr = "*" if every == 1 else f"*/{every}"
    return f"{trigger_minute} {trigger_hour} {target_dom} {month_expr} *"


def _coerce_int(
    raw_value: Any,
    *,
    minimum: int,
    maximum: int,
    rule_index: int,
    field: str,
) -> int:
    try:
        value = int(str(raw_value).strip())
    except Exception as exc:
        raise ScheduleConfigError(
            f"Schedule rule {rule_index}: '{field}' must be an integer."
        ) from exc
    if value < minimum or value > maximum:
        raise ScheduleConfigError(
            f"Schedule rule {rule_index}: '{field}' must be in range [{minimum}, {maximum}]."
        )
    return value


def _coerce_weekday(raw_value: Any, *, rule_index: int, field: str) -> int:
    value_str = str(raw_value).strip().upper()
    if value_str in WEEKDAY_NAME_TO_INT:
        return WEEKDAY_NAME_TO_INT[value_str]
    try:
        value = int(value_str)
    except Exception as exc:
        raise ScheduleConfigError(
            f"Schedule rule {rule_index}: '{field}' must be weekday number 0-6 or name."
        ) from exc
    if value == 7:
        value = 0
    if value < 0 or value > 6:
        raise ScheduleConfigError(
            f"Schedule rule {rule_index}: '{field}' must be weekday number 0-6."
        )
    return value


def _cron_expression_matches(cron_expr: str, localized: datetime) -> bool:
    fields = [part.strip() for part in cron_expr.split()]
    if len(fields) != 5:
        raise ScheduleConfigError("Schedule cron must contain exactly 5 fields.")

    minute_expr, hour_expr, dom_expr, month_expr, dow_expr = fields

    minute_match = _value_matches(
        minute_expr,
        value=localized.minute,
        minimum=0,
        maximum=59,
    )
    hour_match = _value_matches(
        hour_expr,
        value=localized.hour,
        minimum=0,
        maximum=23,
    )
    month_match = _value_matches(
        month_expr,
        value=localized.month,
        minimum=1,
        maximum=12,
        name_to_value=MONTH_NAME_TO_INT,
    )

    day_of_month_match = _value_matches(
        dom_expr,
        value=localized.day,
        minimum=1,
        maximum=31,
    )
    cron_weekday = (localized.weekday() + 1) % 7
    day_of_week_match = _value_matches(
        dow_expr,
        value=cron_weekday,
        minimum=0,
        maximum=6,
        name_to_value=WEEKDAY_NAME_TO_INT,
        treat_7_as_0=True,
    )

    day_match = _combine_day_matches(
        day_of_month_expr=dom_expr,
        day_of_week_expr=dow_expr,
        day_of_month_match=day_of_month_match,
        day_of_week_match=day_of_week_match,
    )

    return minute_match and hour_match and month_match and day_match


def _combine_day_matches(
    *,
    day_of_month_expr: str,
    day_of_week_expr: str,
    day_of_month_match: bool,
    day_of_week_match: bool,
) -> bool:
    dom_wildcard = _is_wildcard(day_of_month_expr)
    dow_wildcard = _is_wildcard(day_of_week_expr)

    if dom_wildcard and dow_wildcard:
        return True
    if dom_wildcard:
        return day_of_week_match
    if dow_wildcard:
        return day_of_month_match
    # Cron semantics: if both DOM and DOW are restricted, either can match.
    return day_of_month_match or day_of_week_match


def _is_wildcard(expr: str) -> bool:
    return expr.strip() == "*"


def _value_matches(
    expr: str,
    *,
    value: int,
    minimum: int,
    maximum: int,
    name_to_value: Mapping[str, int] | None = None,
    treat_7_as_0: bool = False,
) -> bool:
    allowed = _expand_values(
        expr,
        minimum=minimum,
        maximum=maximum,
        name_to_value=name_to_value,
        treat_7_as_0=treat_7_as_0,
    )
    return value in allowed


def _expand_values(
    expr: str,
    *,
    minimum: int,
    maximum: int,
    name_to_value: Mapping[str, int] | None = None,
    treat_7_as_0: bool = False,
) -> set[int]:
    cleaned = expr.strip().upper()
    if not cleaned:
        raise ScheduleConfigError("Schedule field cannot be empty.")

    parts = [part.strip() for part in cleaned.split(",")]
    values: set[int] = set()
    for part in parts:
        if not part:
            raise ScheduleConfigError(f"Invalid empty schedule segment in '{expr}'.")

        step = 1
        base = part
        if "/" in part:
            split = part.split("/", 1)
            base = split[0].strip()
            step_raw = split[1].strip()
            if not step_raw:
                raise ScheduleConfigError(f"Missing step value in '{part}'.")
            try:
                step = int(step_raw)
            except ValueError as exc:
                raise ScheduleConfigError(f"Invalid step value '{step_raw}' in '{part}'.") from exc
            if step <= 0:
                raise ScheduleConfigError(f"Step must be > 0 in '{part}'.")

        if base == "*":
            start = minimum
            end = maximum
        elif "-" in base:
            left_raw, right_raw = base.split("-", 1)
            start = _token_to_int(
                left_raw.strip(),
                minimum=minimum,
                maximum=maximum,
                name_to_value=name_to_value,
                treat_7_as_0=treat_7_as_0,
            )
            end = _token_to_int(
                right_raw.strip(),
                minimum=minimum,
                maximum=maximum,
                name_to_value=name_to_value,
                treat_7_as_0=treat_7_as_0,
            )
            if end < start:
                raise ScheduleConfigError(f"Invalid range '{base}' (end < start).")
        else:
            single = _token_to_int(
                base,
                minimum=minimum,
                maximum=maximum,
                name_to_value=name_to_value,
                treat_7_as_0=treat_7_as_0,
            )
            start = single
            end = single

        values.update(range(start, end + 1, step))

    return values


def _token_to_int(
    token: str,
    *,
    minimum: int,
    maximum: int,
    name_to_value: Mapping[str, int] | None = None,
    treat_7_as_0: bool = False,
) -> int:
    normalized = token.strip().upper()
    if not normalized:
        raise ScheduleConfigError("Schedule token cannot be empty.")

    if name_to_value and normalized in name_to_value:
        value = name_to_value[normalized]
    else:
        try:
            value = int(normalized)
        except ValueError as exc:
            raise ScheduleConfigError(f"Invalid schedule token '{token}'.") from exc

    if treat_7_as_0 and value == 7:
        value = 0

    if value < minimum or value > maximum:
        raise ScheduleConfigError(
            f"Schedule value '{value}' out of range [{minimum}, {maximum}]."
        )

    return value
