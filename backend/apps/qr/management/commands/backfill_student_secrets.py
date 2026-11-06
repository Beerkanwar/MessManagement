"""
Management command to backfill student secrets for all active students lacking an active secret.
[ImplementationGuide Phase 4 & Phase 6 requirement]
Idempotent: safe to run multiple times.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.hostel.models import Student
from apps.identity.models import StudentSecret
from apps.qr.services import provision_student_secret


class Command(BaseCommand):
    help = "Idempotently provisions QR secrets for active students lacking an active secret [Phase 6]."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many secrets would be provisioned without committing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)

        all_active_students = Student.objects.filter(status="ACTIVE")
        total_students = all_active_students.count()

        # Find students who already have an active secret
        students_with_secrets = set(
            StudentSecret.objects.filter(status="ACTIVE").values_list("student_id", flat=True)
        )

        students_needing_secrets = all_active_students.exclude(
            student_id__in=students_with_secrets
        )
        needed_count = students_needing_secrets.count()
        skipped_count = total_students - needed_count

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[DRY RUN] Would provision secrets for {needed_count} student(s). "
                    f"({skipped_count} already provisioned out of {total_students} total)."
                )
            )
            return

        provisioned_count = 0
        with transaction.atomic():
            for student in students_needing_secrets.iterator():
                provision_student_secret(student)
                provisioned_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully provisioned secrets for {provisioned_count} student(s). "
                f"({skipped_count} already provisioned out of {total_students} total)."
            )
        )

