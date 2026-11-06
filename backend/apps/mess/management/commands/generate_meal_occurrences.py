"""
Management command to generate scheduled meal occurrences [SPEC DBDD §5, Phase 5 build item 4].
Enforces SPEC SRS §26.4: runs under PostgreSQL advisory lock convention.
"""
from typing import Any
import structlog
from apps.config.services import get_int_setting
from apps.core.management.commands.base import BaseAdvisoryLockCommand
from apps.mess.services import generate_meal_occurrences

logger = structlog.get_logger("apps.mess.jobs")


class Command(BaseAdvisoryLockCommand):
    help = "Generates SCHEDULED meal occurrences for active messes up to horizon days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Number of days forward to generate occurrences (default: setting 'meal.occurrence_horizon_days' or 35).",
        )
        parser.add_argument(
            "--mess",
            type=str,
            default=None,
            help="Optional mess code filter (e.g. 'M1').",
        )

    def handle_locked(self, *args: Any, **options: Any) -> None:
        horizon_days = options.get("days")
        if horizon_days is None:
            horizon_days = get_int_setting("meal.occurrence_horizon_days", default=35)

        mess_code = options.get("mess")

        logger.info(
            "generate_meal_occurrences_started",
            horizon_days=horizon_days,
            mess_code=mess_code,
        )

        result = generate_meal_occurrences(
            horizon_days=horizon_days,
            mess_code=mess_code,
        )

        logger.info(
            "generate_meal_occurrences_completed",
            created=result["created"],
            skipped=result["skipped"],
            horizon_days=horizon_days,
        )

        self.stdout.write(
            f"Generated occurrences: {result['created']} created, {result['skipped']} already existed."
        )

