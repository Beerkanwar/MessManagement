"""
Checks that a Super Admin may waive when accepting a sync conflict [DEC-17].

Kept in a dependency-free module so both the attendance command and the sync
conflict resolver can import them without a service import cycle.
"""

WAIVE_SCOPE = "SCOPE"
WAIVE_ASSIGNMENT = "ASSIGNMENT"
WAIVE_MEAL_CANCELLED = "MEAL_CANCELLED"
