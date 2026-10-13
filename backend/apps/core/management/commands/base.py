"""
Base management command with PostgreSQL advisory lock convention.
Enforces SPEC SRS §26.4: each scheduled cron job acquires a PostgreSQL advisory lock
so overlapping runs exit quietly without duplicating work, logs outcome,
and returns non-zero on failure.
"""
import hashlib
import struct
from typing import Any
import structlog
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

logger = structlog.get_logger("apps.core.jobs")


class BaseAdvisoryLockCommand(BaseCommand):
    """
    Abstract BaseCommand that wraps execution in a PostgreSQL session-level advisory lock.
    """

    def get_lock_id(self) -> int:
        """
        Derives a deterministic signed 64-bit integer from the command module name
        for use with PostgreSQL pg_try_advisory_lock.
        """
        command_name = self.__class__.__module__ + "." + self.__class__.__name__
        digest = hashlib.sha256(command_name.encode("utf-8")).digest()
        # Unpack first 8 bytes as signed 64-bit integer (-2^63 to 2^63-1)
        return struct.unpack(">q", digest[:8])[0]

    def handle(self, *args: Any, **options: Any) -> None:
        lock_id = self.get_lock_id()
        acquired = False

        # Attempt to acquire advisory lock
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s);", [lock_id])
            acquired = cursor.fetchone()[0]

        if not acquired:
            logger.info(
                "job_overlapping_run_skipped",
                command=self.__class__.__name__,
                lock_id=lock_id,
                message="Another job instance holds the advisory lock; exiting quietly.",
            )
            self.stdout.write("Job already running with advisory lock; exiting quietly.")
            return

        logger.info(
            "job_started",
            command=self.__class__.__name__,
            lock_id=lock_id,
        )

        try:
            self.handle_locked(*args, **options)
            logger.info(
                "job_completed_successfully",
                command=self.__class__.__name__,
                lock_id=lock_id,
            )
        except Exception as exc:
            logger.error(
                "job_execution_failed",
                command=self.__class__.__name__,
                lock_id=lock_id,
                error=str(exc),
                exc_info=exc,
            )
            raise CommandError(f"Job failed: {exc}") from exc
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s);", [lock_id])

    def handle_locked(self, *args: Any, **options: Any) -> None:
        """Subclasses must implement actual job execution logic inside this method."""
        raise NotImplementedError("Subclasses of BaseAdvisoryLockCommand must implement handle_locked().")
