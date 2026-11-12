"""
Declarative report registry [ImplementationGuide Phase 12, build step 1].

Adding a report later means adding one ``ReportDefinition`` here.  The views,
serializers and exporters are parameterised entirely by this registry, so the
React Reports screens (Phases 16 and 17) can be driven from the same catalog.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from apps.reports import queries
from apps.reports.scope import (
    ROLE_CLERK,
    ROLE_MANAGER,
    ROLE_SUPER_ADMIN,
    ReportContext,
)


@dataclass(frozen=True)
class ReportColumn:
    key: str
    label: str
    kind: str = "text"  # text | int | decimal | date | month
    money: bool = False


@dataclass(frozen=True)
class ReportDefinition:
    id: str
    title: str
    columns: tuple[ReportColumn, ...]
    roles: tuple[str, ...]
    supported_filters: tuple[str, ...]
    row_source: Callable[[ReportContext], Iterable[Any]]
    row_mapper: Callable[[Any], dict[str, Any]]
    totals_func: Callable[[ReportContext], dict[str, Any]]
    groups_func: Callable[[ReportContext], list[dict[str, Any]]]
    total_columns: tuple[ReportColumn, ...] = ()

    def allows(self, role: str | None) -> bool:
        return role in self.roles

    @property
    def column_keys(self) -> tuple[str, ...]:
        return tuple(column.key for column in self.columns)


ALL_ROLES = (ROLE_MANAGER, ROLE_CLERK, ROLE_SUPER_ADMIN)

BILLING_COLUMNS = (
    ReportColumn("student", "Student"),
    ReportColumn("roll_number", "Roll Number"),
    ReportColumn("hostel", "Hostel"),
    ReportColumn("mess", "Mess"),
    ReportColumn("period", "Period"),
    ReportColumn("billed_minimum_count", "Billed Minimum Count", "int"),
    ReportColumn("meal_count", "Meal Count", "int"),
    ReportColumn("rate", "Rate", "decimal", money=True),
    ReportColumn("meal_component", "Meal Component", "decimal", money=True),
    ReportColumn("extras", "Extras", "decimal", money=True),
    ReportColumn("fees_and_fines", "Fees and Fines", "decimal", money=True),
    ReportColumn("final_amount", "Final Amount", "decimal", money=True),
    ReportColumn("status", "Status"),
)

MEAL_COLUMNS = (
    ReportColumn("date", "Date", "date"),
    ReportColumn("meal_type", "Meal Type"),
    ReportColumn("student", "Student"),
    ReportColumn("roll_number", "Roll Number"),
    ReportColumn("mess", "Mess"),
    ReportColumn("hostel", "Hostel"),
    ReportColumn("price", "Price Snapshot", "decimal", money=True),
    ReportColumn("source", "Source"),
)

EXTRA_COLUMNS = (
    ReportColumn("date", "Date", "date"),
    ReportColumn("item", "Item"),
    ReportColumn("quantity", "Quantity", "int"),
    ReportColumn("unit_price", "Unit Price", "decimal", money=True),
    ReportColumn("total_amount", "Total", "decimal", money=True),
    ReportColumn("student", "Student"),
    ReportColumn("mess", "Mess"),
    ReportColumn("hostel", "Hostel"),
)

PAUSE_COLUMNS = (
    ReportColumn("student", "Student"),
    ReportColumn("mess", "Mess"),
    ReportColumn("requested_start", "Requested Start", "date"),
    ReportColumn("requested_end", "Requested End", "date"),
    ReportColumn("effective_start", "Effective Start", "date"),
    ReportColumn("effective_end", "Effective End", "date"),
    ReportColumn("status", "Status"),
    ReportColumn("counted_slots", "Counted Slots", "int"),
)

FEEDBACK_COLUMNS = (
    ReportColumn("student", "Student"),
    ReportColumn("mess", "Mess"),
    ReportColumn("month", "Month", "month"),
    ReportColumn("food_quality_rating", "Food Quality", "int"),
    ReportColumn("taste_rating", "Taste", "int"),
    ReportColumn("comments", "Comments"),
)

BALANCE_COLUMNS = (
    ReportColumn("student", "Student"),
    ReportColumn("roll_number", "Roll Number"),
    ReportColumn("semester", "Semester"),
    ReportColumn("opening", "Opening", "decimal", money=True),
    ReportColumn("credits", "Credits", "decimal", money=True),
    ReportColumn("charges", "Charges", "decimal", money=True),
    ReportColumn("current_balance", "Current Balance", "decimal", money=True),
)

HOSTEL_COMPARISON_COLUMNS = (
    ReportColumn("hostel", "Hostel"),
    ReportColumn("students", "Students", "int"),
    ReportColumn("meals", "Meals", "int"),
    ReportColumn("meal_amount", "Meal Amount", "decimal", money=True),
    ReportColumn("extras_amount", "Extras Amount", "decimal", money=True),
    ReportColumn("billed_total", "Billed Total", "decimal", money=True),
    ReportColumn("average_quality", "Average Quality", "decimal"),
    ReportColumn("average_taste", "Average Taste", "decimal"),
)

MESS_COMPARISON_COLUMNS = (
    ReportColumn("mess", "Mess"),
    ReportColumn("students", "Students", "int"),
    ReportColumn("meals", "Meals", "int"),
    ReportColumn("meal_amount", "Meal Amount", "decimal", money=True),
    ReportColumn("extras_amount", "Extras Amount", "decimal", money=True),
    ReportColumn("billed_total", "Billed Total", "decimal", money=True),
    ReportColumn("average_quality", "Average Quality", "decimal"),
    ReportColumn("average_taste", "Average Taste", "decimal"),
)

CROSS_HOSTEL_COLUMNS = (
    ReportColumn("hostel", "Student Hostel"),
    ReportColumn("mess", "Serving Mess"),
    ReportColumn("meal_count", "Meals", "int"),
    ReportColumn("meal_amount", "Meal Amount", "decimal", money=True),
    ReportColumn("extra_count", "Extras", "int"),
    ReportColumn("extra_amount", "Extras Amount", "decimal", money=True),
    ReportColumn("total_amount", "Total Amount", "decimal", money=True),
)

BILLING_TOTALS = (
    ReportColumn("bill_count", "Bill Count", "int"),
    ReportColumn("billed_minimum_count", "Billed Minimum Count", "int"),
    ReportColumn("meal_count", "Meal Count", "int"),
    ReportColumn("meal_component", "Meal Component", "decimal", money=True),
    ReportColumn("extras", "Extras", "decimal", money=True),
    ReportColumn("fees_and_fines", "Fees and Fines", "decimal", money=True),
    ReportColumn("final_amount", "Final Amount", "decimal", money=True),
)

MEAL_TOTALS = (
    ReportColumn("meal_count", "Meal Count", "int"),
    ReportColumn("amount", "Amount", "decimal", money=True),
)

EXTRA_TOTALS = (
    ReportColumn("transaction_count", "Transaction Count", "int"),
    ReportColumn("quantity", "Quantity", "int"),
    ReportColumn("amount", "Amount", "decimal", money=True),
)

PAUSE_TOTALS = (
    ReportColumn("pause_count", "Pause Count", "int"),
    ReportColumn("counted_slots", "Counted Slots", "int"),
)

FEEDBACK_TOTALS = (
    ReportColumn("response_count", "Response Count", "int"),
    ReportColumn("average_quality", "Average Quality", "decimal"),
    ReportColumn("average_taste", "Average Taste", "decimal"),
)

BALANCE_TOTALS = (
    ReportColumn("account_count", "Account Count", "int"),
    ReportColumn("opening", "Opening", "decimal", money=True),
    ReportColumn("credits", "Credits", "decimal", money=True),
    ReportColumn("charges", "Charges", "decimal", money=True),
    ReportColumn("current_balance", "Current Balance", "decimal", money=True),
)

COMPARISON_TOTALS = (
    ReportColumn("students", "Students", "int"),
    ReportColumn("meals", "Meals", "int"),
    ReportColumn("meal_amount", "Meal Amount", "decimal", money=True),
    ReportColumn("extras_amount", "Extras Amount", "decimal", money=True),
    ReportColumn("billed_total", "Billed Total", "decimal", money=True),
    ReportColumn("average_quality", "Average Quality", "decimal"),
    ReportColumn("average_taste", "Average Taste", "decimal"),
)

HOSTEL_COMPARISON_TOTALS = (
    ReportColumn("hostel_count", "Hostel Count", "int"),
    *COMPARISON_TOTALS,
)

MESS_COMPARISON_TOTALS = (
    ReportColumn("mess_count", "Mess Count", "int"),
    *COMPARISON_TOTALS,
)

CROSS_HOSTEL_TOTALS = (
    ReportColumn("row_count", "Row Count", "int"),
    ReportColumn("meal_count", "Meals", "int"),
    ReportColumn("meal_amount", "Meal Amount", "decimal", money=True),
    ReportColumn("extra_count", "Extras", "int"),
    ReportColumn("extra_amount", "Extras Amount", "decimal", money=True),
    ReportColumn("total_amount", "Total Amount", "decimal", money=True),
)


def _identity(row: Any) -> dict[str, Any]:
    return row


REPORTS: tuple[ReportDefinition, ...] = (
    ReportDefinition(
        id="student-billing",
        title="Student Billing",
        columns=BILLING_COLUMNS,
        roles=ALL_ROLES,
        supported_filters=("from", "to", "hostel", "mess", "student"),
        row_source=queries.billing_queryset,
        row_mapper=queries.billing_row,
        totals_func=queries.billing_totals,
        groups_func=queries.billing_groups,
        total_columns=BILLING_TOTALS,
    ),
    ReportDefinition(
        id="meal-consumption",
        title="Meal Consumption",
        columns=MEAL_COLUMNS,
        roles=ALL_ROLES,
        supported_filters=("from", "to", "hostel", "mess", "student", "meal_type"),
        row_source=queries.meal_consumption_queryset,
        row_mapper=queries.meal_consumption_row,
        totals_func=queries.meal_consumption_totals,
        groups_func=queries.meal_consumption_groups,
        total_columns=MEAL_TOTALS,
    ),
    ReportDefinition(
        id="extra-item-usage",
        title="Extra-Item Usage",
        columns=EXTRA_COLUMNS,
        roles=ALL_ROLES,
        supported_filters=("from", "to", "hostel", "mess", "student", "extra_item"),
        row_source=queries.extra_item_queryset,
        row_mapper=queries.extra_item_row,
        totals_func=queries.extra_item_totals,
        groups_func=queries.extra_item_groups,
        total_columns=EXTRA_TOTALS,
    ),
    ReportDefinition(
        id="pause",
        title="Mess Pause",
        columns=PAUSE_COLUMNS,
        roles=ALL_ROLES,
        supported_filters=("from", "to", "hostel", "mess", "student"),
        row_source=queries.pause_queryset,
        row_mapper=queries.pause_row,
        totals_func=queries.pause_totals,
        groups_func=queries.pause_groups,
        total_columns=PAUSE_TOTALS,
    ),
    ReportDefinition(
        id="feedback",
        title="Student Feedback",
        columns=FEEDBACK_COLUMNS,
        roles=(ROLE_CLERK, ROLE_SUPER_ADMIN),
        supported_filters=("from", "to", "hostel", "mess", "student"),
        row_source=queries.feedback_queryset,
        row_mapper=queries.feedback_row,
        totals_func=queries.feedback_totals,
        groups_func=queries.feedback_groups,
        total_columns=FEEDBACK_TOTALS,
    ),
    ReportDefinition(
        id="student-balance",
        title="Student Balance",
        columns=BALANCE_COLUMNS,
        roles=(ROLE_CLERK, ROLE_SUPER_ADMIN),
        supported_filters=("from", "to", "hostel", "student"),
        row_source=queries.balance_queryset,
        row_mapper=queries.balance_row,
        totals_func=queries.balance_totals,
        groups_func=queries.balance_groups,
        total_columns=BALANCE_TOTALS,
    ),
    ReportDefinition(
        id="hostel-comparison",
        title="Hostel Comparison",
        columns=HOSTEL_COMPARISON_COLUMNS,
        roles=(ROLE_SUPER_ADMIN,),
        supported_filters=("from", "to"),
        row_source=queries.hostel_comparison_rows,
        row_mapper=_identity,
        totals_func=queries.hostel_comparison_totals,
        groups_func=queries.hostel_comparison_groups,
        total_columns=HOSTEL_COMPARISON_TOTALS,
    ),
    ReportDefinition(
        id="mess-comparison",
        title="Mess Comparison",
        columns=MESS_COMPARISON_COLUMNS,
        roles=(ROLE_SUPER_ADMIN,),
        supported_filters=("from", "to"),
        row_source=queries.mess_comparison_rows,
        row_mapper=_identity,
        totals_func=queries.mess_comparison_totals,
        groups_func=queries.mess_comparison_groups,
        total_columns=MESS_COMPARISON_TOTALS,
    ),
    ReportDefinition(
        id="cross-hostel-statistics",
        title="Cross-Hostel Statistics",
        columns=CROSS_HOSTEL_COLUMNS,
        roles=(ROLE_SUPER_ADMIN,),
        supported_filters=("from", "to"),
        row_source=queries.cross_hostel_rows,
        row_mapper=_identity,
        totals_func=queries.cross_hostel_totals,
        groups_func=queries.cross_hostel_groups,
        total_columns=CROSS_HOSTEL_TOTALS,
    ),
)

REPORTS_BY_ID: dict[str, ReportDefinition] = {report.id: report for report in REPORTS}


def get_report(report_id: str) -> ReportDefinition | None:
    return REPORTS_BY_ID.get(report_id)


def report_catalog(role: str | None) -> list[ReportDefinition]:
    """Returns the reports the role may run, preserving registry order."""
    return [report for report in REPORTS if report.allows(role)]
