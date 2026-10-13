"""
Injectable clock service for Hostel Mess Management System.
The single authoritative source for system time across the application,
enforcing DEC-01 (Asia/Kolkata calendar dates and UTC timestamps).
Allows automated tests to freeze and time-travel predictably.
"""
from contextlib import contextmanager
from datetime import date, datetime, timezone
import time
from zoneinfo import ZoneInfo
from django.utils import timezone as django_tz

IST_ZONE = ZoneInfo("Asia/Kolkata")


class ClockService:
    """
    Authoritative clock service. All domain services must obtain current time
    and date from this service rather than invoking datetime.now() directly.
    """

    def __init__(self):
        self._frozen_dt: datetime | None = None

    def now(self) -> datetime:
        """
        Returns current UTC timestamp (timezone-aware).
        All database timestamps are stored UTC in timestamptz.
        """
        if self._frozen_dt is not None:
            return self._frozen_dt.astimezone(timezone.utc)
        return django_tz.now()

    def ist_now(self) -> datetime:
        """Returns current timestamp localized to Asia/Kolkata (IST)."""
        return self.now().astimezone(IST_ZONE)

    def today(self) -> date:
        """
        Returns the current calendar date in Asia/Kolkata (DEC-01).
        MealDate, billing dates, and effective dates are IST calendar dates.
        """
        return self.ist_now().date()

    def monotonic(self) -> float:
        """Returns a monotonic clock value in seconds for elapsed duration measurement."""
        return time.monotonic()

    def set_time(self, dt: datetime) -> None:
        """Explicitly freeze clock to the specified datetime for test harnesses."""
        if dt.tzinfo is None:
            # If naive, assume UTC
            self._frozen_dt = dt.replace(tzinfo=timezone.utc)
        else:
            self._frozen_dt = dt

    def reset(self) -> None:
        """Unfreeze clock and resume standard system time tracking."""
        self._frozen_dt = None

    @contextmanager
    def freeze(self, dt: datetime):
        """Context manager to freeze clock temporarily within a test block."""
        previous = self._frozen_dt
        self.set_time(dt)
        try:
            yield self
        finally:
            self._frozen_dt = previous


# Authoritative singleton instance
clock = ClockService()
