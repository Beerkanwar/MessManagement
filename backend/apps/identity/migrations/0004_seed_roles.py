"""
Data migration seeding standard application roles [SPEC DBDD §3, §21].
Idempotent: uses update_or_create.
"""
from django.db import migrations


ROLES = [
    ("STUDENT", "Student mess consumer"),
    ("MESS_MANAGER", "Mess operations manager and scanner"),
    ("HOSTEL_CLERK", "Hostel clerk and student verifier"),
    ("SUPER_ADMIN", "System administrator"),
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    for name, description in ROLES:
        Role.objects.update_or_create(
            name=name,
            defaults={"description": description},
        )


def reverse_roles(apps, schema_editor):
    Role = apps.get_model("identity", "Role")
    names = [r[0] for r in ROLES]
    Role.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0003_studentsecret"),
    ]

    operations = [
        migrations.RunPython(seed_roles, reverse_code=reverse_roles),
    ]
