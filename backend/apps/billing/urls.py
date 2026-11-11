"""
URL patterns for billing and prepaid balance [SPEC SDD §64, ImplementationGuide Phase 10].
"""
from django.urls import path

from apps.billing import views

urlpatterns = [
    # Configuration (Super Admin)
    path("billing/semesters", views.semester_collection_view, name="billing_semesters"),
    path("billing/policies", views.policy_collection_view, name="billing_policies"),

    # Periods and lifecycle (Super Admin)
    path("billing/periods", views.period_collection_view, name="billing_periods"),
    path(
        "billing/periods/<int:billing_period_id>",
        views.period_detail_view,
        name="billing_period_detail",
    ),
    path(
        "billing/periods/<int:billing_period_id>/generate",
        views.period_generate_view,
        name="billing_period_generate",
    ),
    path(
        "billing/periods/<int:billing_period_id>/review",
        views.period_review_view,
        name="billing_period_review",
    ),
    path(
        "billing/periods/<int:billing_period_id>/lock",
        views.period_lock_view,
        name="billing_period_lock",
    ),
    path(
        "billing/periods/<int:billing_period_id>/unlock",
        views.period_unlock_view,
        name="billing_period_unlock",
    ),

    # Bills (Student own LOCKED, Clerk hostel, Super Admin)
    path("billing/bills", views.bill_collection_view, name="billing_bills"),
    path("billing/bills/<int:bill_id>", views.bill_detail_view, name="billing_bill_detail"),
    path(
        "billing/bills/<int:bill_id>/adjustments",
        views.bill_adjustment_view,
        name="billing_bill_adjustments",
    ),

    # Prepaid balances
    path("billing/balances", views.balance_collection_view, name="billing_balances"),
    path(
        "billing/balances/<int:student_id>/credits",
        views.balance_credit_view,
        name="billing_balance_credits",
    ),
    path(
        "billing/opening-balances",
        views.opening_balance_collection_view,
        name="billing_opening_balances",
    ),
    path(
        "billing/opening-balances/import",
        views.opening_balance_import_view,
        name="billing_opening_balances_import",
    ),
]
