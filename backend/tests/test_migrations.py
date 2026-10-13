"""
Tests for migration cleanliness and pending model changes.
Checkpoint:
- makemigrations --check reports no pending changes.
"""
from io import StringIO
import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_makemigrations_check():
    """
    Checkpoint: makemigrations --check passes cleanly with no pending model changes.
    """
    out = StringIO()
    call_command("makemigrations", check=True, dry_run=True, stdout=out)
