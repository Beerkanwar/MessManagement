"""
Cron job: provision missing student QR secrets [ImplementationGuide Phase 13].

This is the Phase 13 name for the Phase 4 backfill. It is on-demand rather than
scheduled; the advisory lock and idempotent provisioning make repeated runs
safe. The implementation delegates to the Phase 6 backfill command.
"""
from apps.qr.management.commands.backfill_student_secrets import (
    Command as BackfillStudentSecretsCommand,
)


class Command(BackfillStudentSecretsCommand):
    help = (
        "Provision QR secrets for active students that do not have one "
        "(idempotent; safe to run on demand) [Phase 4 / Phase 13]."
    )
