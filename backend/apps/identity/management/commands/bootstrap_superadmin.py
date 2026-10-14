"""
Management command to bootstrap the first Super Admin account.
Enforces Phase 3:
- Never accepts password as command-line argument.
- Refuses to run if a Super Admin already exists.
- Assigns SUPER_ADMIN role and emits audit record.
"""
import getpass
from typing import Any
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from apps.audit.services import record_audit_event
from apps.identity.models import Role, UserRole

User = get_user_model()


class Command(BaseCommand):
    help = "Interactively bootstraps the first Super Admin account without exposing credentials."

    def handle(self, *args: Any, **options: Any) -> None:
        # Check if a Super Admin already exists
        super_admin_exists = (
            User.objects.filter(is_superuser=True).exists()
            or UserRole.objects.filter(role__name="SUPER_ADMIN").exists()
        )
        if super_admin_exists:
            raise CommandError("Bootstrap aborted: A Super Admin user already exists in the system.")

        self.stdout.write(self.style.MIGRATE_HEADING("=== Bootstrap First Super Admin Account ==="))

        # Prompt for email
        while True:
            email = input("Enter Super Admin Email: ").strip()
            try:
                validate_email(email)
                if User.objects.filter(normalized_email=email.lower()).exists():
                    self.stderr.write("An account with this email already exists. Try another.")
                    continue
                break
            except ValidationError as e:
                self.stderr.write(f"Invalid email address: {e.messages[0]}")

        # Prompt for full name
        while True:
            full_name = input("Enter Full Name: ").strip()
            if full_name:
                break
            self.stderr.write("Full name cannot be blank.")

        # Prompt for password via getpass (never CLI arg)
        while True:
            password = getpass.getpass("Enter Password (min 10 characters): ")
            if not password:
                self.stderr.write("Password cannot be blank.")
                continue

            try:
                validate_password(password)
            except ValidationError as e:
                for msg in e.messages:
                    self.stderr.write(f"- {msg}")
                continue

            confirm_password = getpass.getpass("Confirm Password: ")
            if password != confirm_password:
                self.stderr.write("Passwords do not match. Please try again.")
                continue
            break

        # Create user and assign role atomically
        with transaction.atomic():
            super_admin_role, _ = Role.objects.get_or_create(
                name="SUPER_ADMIN",
                defaults={"description": "System administrator"},
            )

            user = User.objects.create_superuser(
                email=email,
                password=password,
                full_name=full_name,
            )

            UserRole.objects.create(
                user=user,
                role=super_admin_role,
            )

            record_audit_event(
                event_type="USER_CREATED",
                actor_user=user,
                entity_type="User",
                entity_id=user.user_id,
                reason="Initial Super Admin Bootstrap",
                metadata={"role": "SUPER_ADMIN"},
            )

        self.stdout.write(self.style.SUCCESS(f"Super Admin '{user.normalized_email}' successfully bootstrapped."))
