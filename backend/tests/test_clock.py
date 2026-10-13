"""
Tests for injectable clock service [DEC-01].
Verifies time localization, freeze capability, and IST calendar date derivation.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from apps.core.clock import clock, IST_ZONE


def test_clock_now_and_ist_conversion():
    """Confirms clock.now() is timezone-aware UTC and ist_now() is localized to Asia/Kolkata."""
    now_utc = clock.now()
    assert now_utc.tzinfo is not None

    now_ist = clock.ist_now()
    assert str(now_ist.tzinfo) == "Asia/Kolkata"


def test_clock_freeze_and_ist_date():
    """
    Tests freezing time to verify DEC-01:
    timestamps stored UTC, but calendar date (today()) evaluates in Asia/Kolkata.
    """
    # 2026-10-15 20:30 UTC is 2026-10-16 02:00 IST (+5:30)
    frozen_utc = datetime(2026, 10, 15, 20, 30, 0, tzinfo=timezone.utc)

    with clock.freeze(frozen_utc):
        assert clock.now() == frozen_utc
        # In IST, date has crossed midnight to Oct 16
        assert clock.today() == date(2026, 10, 16)
        assert clock.ist_now().hour == 2
        assert clock.ist_now().minute == 0

    # Clock unfreezes automatically outside context
    assert clock._frozen_dt is None


def test_clock_monotonic_advances():
    """Confirms clock.monotonic() returns numeric float values."""
    m1 = clock.monotonic()
    assert isinstance(m1, float)
    m2 = clock.monotonic()
    assert m2 >= m1
