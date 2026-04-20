"""Delay runner to pause workflow execution before passing data forward."""

from __future__ import annotations

import time
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

    def run(
        self,
        config: dict[str, Any],
        input_data: Any,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        delay_seconds = self._resolve_delay_seconds(config)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        if isinstance(input_data, dict):
            result: dict[str, Any] = dict(input_data)
        elif input_data is None:
            result = {}
        else:
            result = {"_default": input_data}

        result["delay_seconds"] = delay_seconds
        result["delay_completed_at"] = datetime.now(UTC).astimezone(APP_TIMEZONE).isoformat()
        return result

    @classmethod
    def _resolve_delay_seconds(cls, config: dict[str, Any]) -> float:
        until_datetime_raw = str(config.get("until_datetime") or "").strip()
        if until_datetime_raw:
            target = cls._parse_iso_datetime(until_datetime_raw)
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
    def _parse_iso_datetime(value: str) -> datetime:
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
            # Treat naive datetimes as UTC to keep behavior deterministic.
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
