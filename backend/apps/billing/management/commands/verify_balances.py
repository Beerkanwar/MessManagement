"""
Cron job: verify every prepaid balance against its append-only ledger
[ImplementationGuide Phase 10 build 8, REC].

The cached CurrentBalance is never silently repaired: any drift is reported and
the command exits non-zero so the scheduled-job alert fires.
"""
from typing import Any

import structlog
from django.core.management.base import CommandError

from apps.billing.services import verify_balances
from apps.core.management.commands.base import BaseAdvisoryLockCommand

logger = structlog.get_logger("apps.billing.jobs")


class Command(BaseAdvisoryLockCommand):
    help = "Recompute every BalanceAccount from its ledger and alert on drift."

    def handle_locked(self, *args: Any, **options: Any) -> None:
        result = verify_balances()
        self.stdout.write(
            f"verify_balances: checked={result['checked']} drifts={len(result['drifts'])}"
        )
        for drift in result["drifts"]:
            self.stdout.write(
                "  drift: "
                f"account={drift['balance_account_id']} "
                f"student={drift['student_id']} "
                f"semester={drift['semester_id']} "
                f"ledger_sum={drift['ledger_sum']} "
                f"cached={drift['cached_balance']} "
                f"difference={drift['difference']}"
            )
        if result["drifts"]:
            logger.error(
                "balance_verification_drift",
                checked=result["checked"],
                drift_count=len(result["drifts"]),
            )
            raise CommandError(
                f"Balance verification found {len(result['drifts'])} drifting account(s)."
            )
