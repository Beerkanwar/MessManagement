"""
URL patterns for hostel management, student provisioning, import pipeline,
verification, transfer, and clerk management — Phase 4.
Enforces SPEC SDD §64, Appendix A, and ImplementationGuide Phase 4.
"""
from django.urls import path
from apps.hostel import views

urlpatterns = [
    # Hostels [SPEC SDD §64, ImplementationGuide Phase 4]
    path("hostels", views.hostel_list_create_view, name="hostels_list_create"),
    path("hostels/<int:hostel_id>", views.hostel_detail_update_view, name="hostel_detail_update"),
    path("hostels/<int:hostel_id>/deactivate", views.hostel_deactivate_view, name="hostel_deactivate"),

    # Hostel Clerks [SPEC SDD §64, ImplementationGuide Phase 4]
    path("admin/hostel-clerks", views.clerk_list_create_view, name="clerk_list_create"),
    path("admin/hostel-clerks/<int:user_id>/reassign", views.clerk_reassign_view, name="clerk_reassign"),
    path("admin/hostel-clerks/<int:user_id>/deactivate", views.clerk_deactivate_view, name="clerk_deactivate"),

    # Students [SPEC SDD §64, ImplementationGuide Phase 4]
    path("students", views.student_list_create_view, name="students_list_create"),
    path("students/me", views.student_me_view, name="student_me"),
    path("students/<int:student_id>", views.student_detail_update_view, name="student_detail_update"),
    path("students/<int:student_id>/transfer", views.student_transfer_view, name="student_transfer"),

    # Student Import Pipeline [SPEC SDD §96-97, ImplementationGuide Phase 4]
    path("students/imports", views.import_upload_view, name="import_upload"),
    path("students/imports/<int:batch_id>", views.import_detail_view, name="import_detail"),
    path("students/imports/<int:batch_id>/preview", views.import_preview_view, name="import_preview"),
    path("students/imports/<int:batch_id>/errors", views.import_errors_view, name="import_errors"),
    path("students/imports/<int:batch_id>/commit", views.import_commit_view, name="import_commit"),
    path("students/imports/<int:batch_id>/cancel", views.import_cancel_view, name="import_cancel"),

    # Student Verifications (Clerk) [SPEC SRS §3.3, ImplementationGuide Phase 4]
    path("students/verifications", views.verification_list_view, name="verification_list"),
    path("students/verifications/<int:assignment_id>/verify", views.verification_verify_view, name="verification_verify"),
    path("students/verifications/<int:assignment_id>/reject", views.verification_reject_view, name="verification_reject"),
    path("students/verifications/bulk-verify", views.verification_bulk_verify_view, name="verification_bulk_verify"),
    path("students/verifications/bulk-reject", views.verification_bulk_reject_view, name="verification_bulk_reject"),
]
