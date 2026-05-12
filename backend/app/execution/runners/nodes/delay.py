"""Delay runner to pause workflow execution before passing data forward."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Asia/Kolkata")


class DelayRunner:
    """Pauses execution for a configured duration and passes input data through."""

    UNIT_SECONDS: dict[str, float] = {
        "second": 1.0,
        "seconds": 1.0,
        "minute": 60.0,
        "minutes": 60.0,
        "hour": 3600.0,
        "hours": 3600.0,
        "day": 86400.0,
        "days": 86400.0,
        # Month is approximated as 30 days for fixed-duration delays.
        "month": 2592000.0,
        "months": 2592000.0,
    }
    WAIT_MODE_ALIASES: dict[str, str] = {
        "after_interval": "after_interval",
        "interval": "after_interval",
        "after": "after_interval",
        "until_datetime": "until_datetime",
        "untildatetime": "until_datetime",
        "until": "until_datetime",
        "datetime": "until_datetime",
        "at_datetime": "until_datetime",
        # Backward compatibility: previously supported webhook wait mode now
        # falls back to standard interval wait behavior.
        "on_webhook": "after_interval",
        "onwebhook": "after_interval",
        "on-webhook": "after_interval",
        "on webhook": "after_interval",
        "webhook": "after_interval",
        "on_event": "after_interval",
        "event": "after_interval",
    }

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        wait_mode = self._resolve_wait_mode(config)

        if isinstance(input_data, dict):
            result: dict[str, Any] = dict(input_data)
        elif input_data is None:
            result = {}
        else:
            result = {"_default": input_data}

        now_utc = datetime.now(UTC)
        result["wait_mode"] = wait_mode
        result["delay_completed_at"] = now_utc.astimezone(APP_TIMEZONE).isoformat()

        delay_seconds = self._resolve_delay_seconds(config, wait_mode=wait_mode)
        result["delay_seconds"] = delay_seconds
        if delay_seconds > 0:
            result["delay_run_at"] = (
                now_utc.timestamp() + delay_seconds
            )
        return result

    @classmethod
    def _resolve_wait_mode(cls, config: dict[str, Any]) -> str:
        raw_mode = str(config.get("wait_mode") or "").strip().lower()
        if not raw_mode:
            return "until_datetime" if str(config.get("until_datetime") or "").strip() else "after_interval"
        normalized = cls.WAIT_MODE_ALIASES.get(raw_mode)
        if normalized:
            return normalized
        raise ValueError(
            "Delay node: wait_mode must be one of after_interval, until_datetime."
        )

    @classmethod
    def _resolve_delay_seconds(
        cls,
        config: dict[str, Any],
        *,
        wait_mode: str | None = None,
    ) -> float:
        mode = wait_mode or cls._resolve_wait_mode(config)

        until_datetime_raw = str(config.get("until_datetime") or "").strip()
        if mode == "until_datetime":
            if not until_datetime_raw:
                raise ValueError(
                    "Delay node: wait_mode='until_datetime' requires 'until_datetime'."
                )
            target = cls._parse_iso_datetime(
                until_datetime_raw,
                timezone_name=str(config.get("timezone") or "").strip() or None,
            )
            now = datetime.now(UTC)
            return max(0.0, (target - now).total_seconds())

        amount_raw = config.get("amount")
        if amount_raw is None or str(amount_raw).strip() == "":
            # Backward-compatible alias if model/workflow uses "seconds" directly.
            amount_raw = config.get("seconds")

        if amount_raw is None or str(amount_raw).strip() == "":
            raise ValueError(
                "Delay node: provide either 'until_datetime' or 'amount' (or 'seconds')."
            )

        try:
            amount = float(str(amount_raw).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Delay node: amount must be a valid number.") from exc

        if amount < 0:
            raise ValueError("Delay node: amount must be >= 0.")

        unit = str(config.get("unit") or "seconds").strip().lower()
        multiplier = cls.UNIT_SECONDS.get(unit)
        if multiplier is None:
            raise ValueError(
                "Delay node: unit must be one of seconds, minutes, hours, days, months."
            )

        return amount * multiplier

    @staticmethod
    def _parse_iso_datetime(value: str, *, timezone_name: str | None = None) -> datetime:
        candidate = value.strip()
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError(
                "Delay node: 'until_datetime' must be a valid ISO datetime, e.g. 2026-04-17T18:30:00Z."
            ) from exc

        if parsed.tzinfo is None:
            resolved_timezone = timezone_name or "Asia/Kolkata"
            try:
                parsed = parsed.replace(tzinfo=ZoneInfo(resolved_timezone))
            except Exception as exc:
                raise ValueError(
                    "Delay node: timezone must be a valid IANA timezone, e.g. Asia/Kolkata or UTC."
                ) from exc
        return parsed.astimezone(UTC)
