"""
Cron job: open the monthly billing period [ImplementationGuide Phase 10 build 3].

Runs on the 1st of each month at 00:30 IST and creates the OPEN BillingPeriod for
the previous calendar month if it is missing. The advisory lock makes overlapping
runs exit quietly; the unique (year, month) constraint is the final guard.
"""
from datetime import datetime
from typing import Any

from apps.billing.services import open_billing_period
from apps.core.clock import clock
from apps.core.management.commands.base import BaseAdvisoryLockCommand


class Command(BaseAdvisoryLockCommand):
    help = "Create the OPEN BillingPeriod for the previous calendar month if missing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            default=None,
            help="Reference IST date in YYYY-MM-DD (default: today). Used by tests.",
        )

    def handle_locked(self, *args: Any, **options: Any) -> None:
        reference = options.get("date")
        target_date = (
            datetime.strptime(reference, "%Y-%m-%d").date()
            if reference
            else clock.today()
        )
        period, created = open_billing_period(target_date)
        self.stdout.write(
            "open_billing_period: "
            f"period={period.year}-{period.month:02d} "
            f"status={period.status} "
            f"created={str(created).lower()}"
        )
