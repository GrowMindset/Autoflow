from __future__ import annotations

from datetime import datetime, timezone

import unittest

from app.services.schedule_service import (
    ScheduleConfigError,
    build_cron_expression,
    build_schedule_payload,
    is_schedule_due,
    is_schedule_enabled,
)


class ScheduleServiceTests(unittest.TestCase):
    def test_build_cron_expression_prefers_explicit_cron(self) -> None:
        config = {
            "cron": "*/15 9-17 * * 1-5",
            "minute": "1",
            "hour": "2",
        }
        self.assertEqual(build_cron_expression(config), "*/15 9-17 * * 1-5")

    def test_build_cron_expression_from_rules(self) -> None:
        config = {
            "rules": [
                {"interval": "hours", "every": 2, "trigger_minute": 15, "enabled": True},
            ],
        }
        self.assertEqual(build_cron_expression(config), "15 */2 * * *")

    def test_is_schedule_enabled_defaults_true(self) -> None:
        self.assertTrue(is_schedule_enabled({}))
        self.assertFalse(is_schedule_enabled({"enabled": False}))
        self.assertFalse(is_schedule_enabled({"enabled": "false"}))

    def test_is_schedule_due_matches_basic_minute_hour(self) -> None:
        now = datetime(2026, 4, 16, 10, 30, tzinfo=timezone.utc)
        config = {
            "minute": "30",
            "hour": "10",
            "day_of_month": "*",
            "month": "*",
            "day_of_week": "*",
            "timezone": "UTC",
        }
        self.assertTrue(is_schedule_due(config, now_utc=now))

        mismatch = dict(config)
        mismatch["minute"] = "31"
        self.assertFalse(is_schedule_due(mismatch, now_utc=now))

    def test_is_schedule_due_supports_ranges_steps_and_names(self) -> None:
        # 2026-04-17 is Friday.
        now = datetime(2026, 4, 17, 9, 15, tzinfo=timezone.utc)
        config = {
            "cron": "*/15 9-18 * APR MON-FRI",
            "timezone": "UTC",
        }
        self.assertTrue(is_schedule_due(config, now_utc=now))

    def test_is_schedule_due_respects_timezone(self) -> None:
        # 2026-04-16T03:30:00Z == 2026-04-16 09:00 in Asia/Kolkata.
        now = datetime(2026, 4, 16, 3, 30, tzinfo=timezone.utc)
        config = {
            "minute": "0",
            "hour": "9",
            "day_of_month": "*",
            "month": "*",
            "day_of_week": "*",
            "timezone": "Asia/Kolkata",
        }
        self.assertTrue(is_schedule_due(config, now_utc=now))

    def test_is_schedule_due_matches_rule_based_config(self) -> None:
        now = datetime(2026, 4, 16, 10, 30, tzinfo=timezone.utc)
        config = {
            "timezone": "UTC",
            "enabled": True,
            "rules": [
                {
                    "interval": "hours",
                    "every": 2,
                    "trigger_minute": 30,
                    "enabled": True,
                }
            ],
        }
        self.assertTrue(is_schedule_due(config, now_utc=now))

        mismatch = {
            **config,
            "rules": [
                {
                    "interval": "hours",
                    "every": 2,
                    "trigger_minute": 10,
                    "enabled": True,
                }
            ],
        }
        self.assertFalse(is_schedule_due(mismatch, now_utc=now))

    def test_is_schedule_due_matches_custom_rule(self) -> None:
        now = datetime(2026, 4, 17, 9, 15, tzinfo=timezone.utc)
        config = {
            "timezone": "UTC",
            "rules": [
                {"interval": "custom", "cron": "*/15 9-18 * APR MON-FRI", "enabled": True}
            ],
        }
        self.assertTrue(is_schedule_due(config, now_utc=now))

    def test_is_schedule_due_raises_for_invalid_timezone(self) -> None:
        now = datetime(2026, 4, 16, 10, 30, tzinfo=timezone.utc)
        with self.assertRaises(ScheduleConfigError):
            is_schedule_due({"cron": "* * * * *", "timezone": "Mars/Phobos"}, now_utc=now)

    def test_build_schedule_payload_contains_runtime_metadata(self) -> None:
        now = datetime(2026, 4, 16, 10, 30, tzinfo=timezone.utc)
        payload = build_schedule_payload(
            config={"cron": "*/10 * * * *", "timezone": "UTC"},
            node_id="trigger_schedule_1",
            fired_at_utc=now,
        )
        self.assertEqual(payload["trigger_type"], "schedule")
        self.assertEqual(payload["schedule_node_id"], "trigger_schedule_1")
        self.assertEqual(payload["schedule_cron"], "*/10 * * * *")
        self.assertEqual(payload["schedule_timezone"], "UTC")


if __name__ == "__main__":
    unittest.main()
