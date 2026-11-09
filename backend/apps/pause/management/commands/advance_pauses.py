"""
Cron job: advance mess pause lifecycle every 15 minutes [ImplementationGuide P9].

Each pause is processed in its own transaction. The advisory lock guarantees that
overlapping cron runs exit quietly, and the row lock plus idempotent transitions
make a repeated run a no-op.
"""
from typing import Any

from apps.core.management.commands.base import BaseAdvisoryLockCommand
from apps.pause.services import advance_pauses


class Command(BaseAdvisoryLockCommand):
    help = "Consume finished pause slots, activate ready pauses and complete expired ones."

    def handle_locked(self, *args: Any, **options: Any) -> None:
        counts = advance_pauses()
        self.stdout.write(
            "advance_pauses: "
            f"processed={counts['processed']} "
            f"changed={counts['changed']} "
            f"activated={counts['activated']} "
            f"completed={counts['completed']}"
        )
