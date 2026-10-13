"""
Example no-op scheduled job implementing PostgreSQL advisory lock convention.
Reference implementation for future cron jobs (Phases 5, 9, 10, 13).
"""
from typing import Any
from apps.core.management.commands.base import BaseAdvisoryLockCommand


class Command(BaseAdvisoryLockCommand):
    help = "Executes the example no-op scheduled job protected by a PostgreSQL advisory lock."

    def handle_locked(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Running example no-op job under advisory lock...")
        # No-op payload
        self.stdout.write("Example job completed successfully.")
