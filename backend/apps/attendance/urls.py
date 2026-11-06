"""
URL patterns for attendance, summary, extras, and corrections [SPEC SDD §64, ImplementationGuide Phase 7].
"""
from django.urls import path
from apps.attendance import views

urlpatterns = [
    # Attendance List & Summary [SPEC SDD §64, ImplementationGuide Phase 7]
    path("attendance", views.attendance_list_view, name="attendance_list"),
    path("attendance/summary", views.attendance_summary_view, name="attendance_summary"),

    # Attendance Corrections [SPEC SRS §32, ImplementationGuide Phase 7]
    path("attendance/corrections", views.attendance_corrections_list_create_view, name="attendance_corrections_list_create"),

    # Extras Transactions History [SPEC SDD §64, Appendix A, ImplementationGuide Phase 7]
    path("extras/transactions", views.extra_transactions_list_view, name="extra_transactions_list"),
]
