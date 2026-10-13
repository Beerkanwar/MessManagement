# Physical Entity Relationship Diagram & Schema Verification

**Hostel Mess Management System — Phase 2 Exit Gate Artifact**  
Verified against: `Hostel_Mess_DBDD_v2.0` (§2–§17, §22), `ImplementationGuide.md` (Phase 2), and live PostgreSQL 16 schema.

---

## 1. Relational ERD (Mermaid)

```mermaid
erDiagram
    %% Identity App (§3, §13)
    identity_user {
        int user_id PK
        string email
        string normalized_email UK
        string full_name
        string phone_number
        string status "ACTIVE, INACTIVE, LOCKED"
        timestamp last_login_at
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    identity_role {
        int role_id PK
        string name UK "STUDENT, MESS_MANAGER, HOSTEL_CLERK, SUPER_ADMIN"
        text description
        timestamp created_at
        timestamp updated_at
    }

    identity_user_role {
        int user_role_id PK
        int user_id FK
        int role_id FK
        timestamp created_at
    }

    identity_device_registration {
        int device_registration_id PK
        int user_id FK
        string device_id
        string platform "ANDROID, IOS, WEB"
        string session_status "ACTIVE, REPLACED, REVOKE_PENDING_SYNC, REVOKED, LOGGED_OUT"
        timestamp registered_at
        timestamp last_active_at
        timestamp revoked_at
        text revoke_reason
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    identity_refresh_token {
        int refresh_token_id PK
        int user_id FK
        int device_registration_id FK
        string token_hash UK
        int replaced_by_id FK
        timestamp expires_at
        boolean is_revoked
        timestamp created_at
    }

    identity_password_reset_token {
        int password_reset_token_id PK
        int user_id FK
        string token_hash UK
        string otp_hash
        string email
        int attempts
        int max_attempts
        timestamp expires_at
        boolean is_used
        timestamp created_at
    }

    identity_student_secret {
        int student_secret_id PK
        int student_id FK
        int secret_version
        binary encrypted_secret
        string status "ACTIVE, RETIRED"
        timestamp created_at
        timestamp updated_at
    }

    %% Hostel App (§4)
    hostel_hostel {
        int hostel_id PK
        string code UK
        string name
        text address
        string status "ACTIVE, INACTIVE"
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    hostel_student {
        int student_id PK
        int user_id FK,UK
        string roll_number UK
        int hostel_id FK
        string department
        int year_of_study
        string room_number
        string status "ACTIVE, INACTIVE"
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    hostel_student_mess_assignment {
        int assignment_id PK
        int student_id FK
        int mess_id FK
        int hostel_id FK
        string status "PENDING_VERIFICATION, ACTIVE, ENDED, REJECTED"
        date effective_from
        date effective_to
        int verified_by_id FK
        timestamp verified_at
        text rejection_reason
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    hostel_hostel_clerk_assignment {
        int clerk_assignment_id PK
        int user_id FK
        int hostel_id FK
        boolean is_active
        timestamp assigned_at
        timestamp deactivated_at
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    hostel_student_verification {
        int verification_id PK
        int assignment_id FK
        int verified_by_id FK
        string verification_status "VERIFIED, REJECTED"
        text verification_notes
        timestamp verified_at
        timestamp created_at
    }

    hostel_student_import_batch {
        int batch_id PK
        int imported_by_id FK
        string file_name
        int total_rows
        int successful_rows
        int failed_rows
        string status "STAGED, VALIDATED, COMMITTED, FAILED, CANCELLED"
        timestamp started_at
        timestamp completed_at
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    hostel_student_import_error {
        int error_id PK
        int batch_id FK
        int row_number
        string roll_number
        text error_message
        jsonb raw_row_data
        timestamp created_at
    }

    %% Mess App (§5)
    mess_mess {
        int mess_id PK
        string code UK
        string name
        string status "ACTIVE, INACTIVE"
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    mess_mess_manager_assignment {
        int assignment_id PK
        int user_id FK
        int mess_id FK
        boolean is_active
        timestamp assigned_at
        timestamp deactivated_at
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    mess_meal_type {
        int meal_type_id PK
        string code UK "BREAKFAST, LUNCH, EVENING_SNACKS, DINNER"
        string name
        int sequence_no
        boolean is_fixed
        boolean is_active
    }

    mess_meal_occurrence {
        int meal_occurrence_id PK
        int mess_id FK
        int meal_type_id FK
        date meal_date
        string status "SCHEDULED, CANCELLED"
        bigint configuration_version
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    mess_meal_rate {
        int meal_rate_id PK
        int mess_id FK
        decimal rate
        date effective_from
        date effective_to
        int created_by_id FK
        timestamp created_at
        timestamp updated_at
    }

    mess_extra_item {
        int extra_item_id PK
        int hostel_id FK
        string name
        string normalized_name
        string status "ACTIVE, INACTIVE"
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    mess_extra_price {
        int extra_price_id PK
        int extra_item_id FK
        decimal unit_price
        date effective_from
        date effective_to
        int created_by_id FK
        timestamp created_at
        timestamp updated_at
    }

    %% Attendance App (§6)
    attendance_meal_consumption {
        int meal_consumption_id PK
        uuid transaction_id UK
        int student_id FK
        string roll_number_snapshot
        int mess_id FK
        int meal_type_id FK
        date meal_date
        int meal_occurrence_id FK
        decimal price_at_transaction
        timestamp transaction_timestamp
        string verification_method
        string verification_result
        int device_registration_id FK
        int recorded_by_user_id FK
        string source
        string sync_status
        timestamp created_at
        timestamp accepted_at
    }

    attendance_extra_transaction {
        int extra_transaction_id PK
        uuid transaction_id UK
        int student_id FK
        int hostel_id FK
        int mess_id FK
        int extra_item_id FK
        int quantity
        decimal unit_price_at_transaction
        decimal total_amount
        timestamp transaction_timestamp
        int recorded_by_user_id FK
        int device_registration_id FK
        string source
        string sync_status
        timestamp created_at
        timestamp accepted_at
    }

    attendance_attendance_correction {
        int correction_id PK
        uuid correction_transaction_id UK
        int student_id FK
        int mess_id FK
        date meal_date
        int meal_type_id FK
        string action "ADD_MISSING, REMOVE_INCORRECT"
        int original_meal_consumption_id FK
        timestamp requested_at
        timestamp applied_at
        text reason
        int actor_user_id FK
        string status "APPLIED, REJECTED"
        uuid source_transaction_id
        timestamp created_at
    }

    %% Pause App (§7)
    pause_mess_pause {
        int pause_id PK
        int student_id FK
        int mess_id FK
        date requested_start_date
        date requested_end_date
        date effective_start_date
        date effective_end_date
        date activation_meal_date
        string status "SCHEDULED, ACTIVE, CANCELLED, COMPLETED"
        timestamp requested_at
        timestamp cancelled_at
        timestamp completed_at
        text cancellation_reason
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    pause_mess_pause_meal_slot {
        int pause_slot_id PK
        int pause_id FK
        int meal_occurrence_id FK
        int slot_sequence
        boolean qualifies_for_activation
        date slot_date
        boolean consumed_for_activation
        timestamp created_at
    }

    %% Billing App (§8)
    billing_semester {
        int semester_id PK
        string code UK
        string name
        date start_date
        date end_date
        string status "UPCOMING, ACTIVE, COMPLETED, ARCHIVED"
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    billing_billing_period {
        int billing_period_id PK
        int year
        int month
        date period_start
        date period_end
        string status "OPEN, BILL_GENERATED, REVIEWED, LOCKED"
        timestamp opened_at
        timestamp generated_at
        timestamp reviewed_at
        timestamp locked_at
        int locked_by_id FK
        timestamp unlocked_at
        int unlocked_by_id FK
        text unlock_reason
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    billing_billing_policy {
        int billing_policy_id PK
        int mess_id FK
        int minimum_diet_count
        date effective_from
        date effective_to
        int policy_version
        int created_by_id FK
        timestamp created_at
        timestamp updated_at
    }

    billing_bill {
        int bill_id PK
        int student_id FK
        int mess_id FK
        int billing_period_id FK
        int semester_id FK
        decimal meal_component_amount
        decimal extra_charges_amount
        decimal adjustment_amount
        decimal final_amount
        decimal common_diet_rate_snapshot
        int minimum_diet_count_snapshot
        int actual_meal_count
        string status "DRAFT, FINAL, LOCKED"
        timestamp generated_at
        timestamp locked_at
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    billing_bill_line {
        int bill_line_id PK
        int bill_id FK
        string line_type "MINIMUM_DIET, EXTRA, ADJUSTMENT"
        string source_entity_type
        string source_entity_id
        text description
        int quantity
        decimal unit_rate
        decimal amount
        int calculation_order
        timestamp created_at
    }

    billing_bill_adjustment {
        int adjustment_id PK
        int bill_id FK
        decimal amount
        string adjustment_type "FEE, FINE"
        text reason
        int created_by_id FK
        timestamp created_at
    }

    billing_balance_account {
        int balance_account_id PK
        int student_id FK
        int semester_id FK
        decimal opening_balance
        decimal current_balance
        timestamp last_calculated_at
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    billing_balance_ledger_entry {
        int ledger_entry_id PK
        int balance_account_id FK
        string entry_type "OPENING, CREDIT, BILL_CHARGE, BILL_REVERSAL"
        decimal amount
        string reference_type
        string reference_id
        date effective_date
        text description
        int created_by_id FK
        timestamp created_at
    }

    %% Menu App (§9)
    menu_food_item {
        int food_item_id PK
        string name
        string normalized_name UK
        text description
        string status "ACTIVE, INACTIVE"
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    menu_menu {
        int menu_id PK
        int hostel_id FK
        int menu_year
        int menu_month
        string status "DRAFT, PUBLISHED"
        timestamp published_at
        int published_by_user_id FK
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    menu_menu_meal {
        int menu_meal_id PK
        int menu_id FK
        date menu_date
        int meal_type_id FK
        string status "DRAFT, PUBLISHED"
        timestamp created_at
        timestamp updated_at
    }

    menu_menu_item {
        int menu_item_id PK
        int menu_meal_id FK
        int food_item_id FK
        int display_order
        text notes
        timestamp created_at
    }

    %% Feedback App (§10)
    feedback_feedback {
        int feedback_id PK
        int student_id FK
        int mess_id FK
        int calendar_year
        int calendar_month
        int food_quality_rating
        int taste_rating
        text comments
        timestamp created_at
    }

    %% Sync App (§11)
    sync_sync_batch {
        int sync_batch_id PK
        uuid batch_id UK
        int device_registration_id FK
        int user_id FK
        string status "IN_PROGRESS, COMPLETED, FAILED"
        bigint client_cursor
        bigint server_cursor_before
        bigint server_cursor_after
        int transaction_count
        timestamp sent_at
        timestamp completed_at
        timestamp created_at
    }

    sync_sync_transaction {
        int sync_transaction_id PK
        uuid transaction_id UK
        int sync_batch_id FK
        string entity_type "MEAL, EXTRA"
        string entity_id
        timestamp client_created_at
        timestamp received_at
        string processing_status
        string result_code
        text result_message
        timestamp processed_at
        string idempotency_key
    }

    sync_sync_conflict {
        int conflict_id PK
        int sync_transaction_id FK
        string conflict_type
        text conflict_reason
        timestamp detected_at
        timestamp resolved_at
        int resolved_by_user_id FK
        string resolution "ACCEPTED, REJECTED"
        text resolution_notes
    }

    sync_change_cursor {
        int cursor_id PK
        string aggregate_type UK
        bigint current_version
        timestamp updated_at
    }

    %% Audit & Config (§12)
    audit_audit_log {
        int audit_id PK
        string event_type
        int actor_user_id FK
        int device_registration_id FK
        string entity_type
        string entity_id
        timestamp occurred_at
        text reason
        string correlation_id
        jsonb old_values_json
        jsonb new_values_json
        jsonb metadata_json
        timestamp created_at
    }

    config_system_setting {
        int setting_id PK
        string key
        text value
        string data_type
        text description
        boolean is_sensitive
        timestamp effective_from
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    config_application_version_policy {
        int policy_id PK
        string platform "ANDROID, IOS, WEB"
        string app_version
        string status "SUPPORTED, DEPRECATED, BLOCKED"
        text force_update_message
        timestamp created_at
        timestamp updated_at
        bigint version
    }

    %% Relationships
    identity_user ||--o{ identity_user_role : "holds"
    identity_role ||--o{ identity_user_role : "assigned to"
    identity_user ||--o{ identity_device_registration : "registers"
    identity_user ||--o{ identity_refresh_token : "owns"
    identity_device_registration ||--o{ identity_refresh_token : "binds"
    identity_user ||--o{ identity_password_reset_token : "requests"
    hostel_student ||--o{ identity_student_secret : "holds"

    identity_user ||--|| hostel_student : "profile"
    hostel_hostel ||--o{ hostel_student : "houses"
    hostel_student ||--o{ hostel_student_mess_assignment : "assigned"
    mess_mess ||--o{ hostel_student_mess_assignment : "serves"
    hostel_hostel ||--o{ hostel_student_mess_assignment : "context"
    identity_user ||--o{ hostel_hostel_clerk_assignment : "clerk"
    hostel_hostel ||--o{ hostel_hostel_clerk_assignment : "managed by"
    hostel_student_mess_assignment ||--o{ hostel_student_verification : "verified by"

    identity_user ||--o{ mess_mess_manager_assignment : "manages"
    mess_mess ||--o{ mess_mess_manager_assignment : "assigned manager"
    mess_mess ||--o{ mess_meal_occurrence : "hosts"
    mess_meal_type ||--o{ mess_meal_occurrence : "categorized by"
    mess_mess ||--o{ mess_meal_rate : "prices"
    hostel_hostel ||--o{ mess_extra_item : "offers"
    mess_extra_item ||--o{ mess_extra_price : "priced by"

    hostel_student ||--o{ attendance_meal_consumption : "consumes"
    mess_mess ||--o{ attendance_meal_consumption : "served at"
    mess_meal_type ||--o{ attendance_meal_consumption : "meal slot"
    hostel_student ||--o{ attendance_extra_transaction : "purchases"
    mess_extra_item ||--o{ attendance_extra_transaction : "item"
    attendance_meal_consumption ||--o{ attendance_attendance_correction : "corrects"

    hostel_student ||--o{ pause_mess_pause : "pauses"
    pause_mess_pause ||--o{ pause_mess_pause_meal_slot : "evaluated by"

    mess_mess ||--o{ billing_billing_policy : "governed by"
    hostel_student ||--o{ billing_bill : "billed to"
    billing_billing_period ||--o{ billing_bill : "period"
    billing_bill ||--o{ billing_bill_line : "calculated by"
    billing_bill ||--o{ billing_bill_adjustment : "adjusted by"
    hostel_student ||--o{ billing_balance_account : "prepaid account"
    billing_balance_account ||--o{ billing_balance_ledger_entry : "entries"

    hostel_hostel ||--o{ menu_menu : "offers menu"
    menu_menu ||--o{ menu_menu_meal : "contains meal"
    menu_menu_meal ||--o{ menu_menu_item : "lists food"
    menu_food_item ||--o{ menu_menu_item : "included in"

    hostel_student ||--o{ feedback_feedback : "rates"
    mess_mess ||--o{ feedback_feedback : "feedback for"

    sync_sync_batch ||--o{ sync_sync_transaction : "contains"
    sync_sync_transaction ||--o{ sync_sync_conflict : "flags"
```

---

## 2. Invariant & Constraint Verification Matrix

| Spec Section | Invariant / Constraint Rule | Enforcement Level | Verification Status |
| :--- | :--- | :--- | :--- |
| **DBDD §16.1** | No overlapping active mess assignments per student | PostgreSQL `ExclusionConstraint` (`gist`) | ✅ Verified via `test_invariant_1_student_mess_assignment_overlap` |
| **DBDD §16.2 / DEC-21** | At most one active mess per manager; one manager per mess | PostgreSQL `UniqueConstraint(condition=Q(is_active=True))` | ✅ Verified via `test_invariant_2_manager_one_active_mess` |
| **DBDD §16.3** | At most one active hostel per clerk | PostgreSQL `UniqueConstraint(condition=Q(is_active=True))` | ✅ Verified via `test_invariant_3_clerk_one_active_hostel` |
| **DBDD §16.4** | At most one meal consumption per student + date + meal type | PostgreSQL `UniqueConstraint(fields=[student, meal_date, meal_type])` | ✅ Verified via `test_invariant_4_duplicate_meal_attendance` |
| **DBDD §16.5** | Global uniqueness of operational transaction identifiers | PostgreSQL `UniqueConstraint(fields=[transaction_id])` | ✅ Verified via `test_invariant_5_unique_transaction_id` |
| **DBDD §16.6** | At most one feedback submission per student per month | PostgreSQL `UniqueConstraint(fields=[student, calendar_year, calendar_month])` | ✅ Verified via `test_invariant_6_monthly_feedback_uniqueness` |
| **DBDD §16.7** | At most one bill per student + mess + billing period | PostgreSQL `UniqueConstraint(fields=[student, mess, billing_period])` | ✅ Verified via `test_invariant_7_unique_bill_per_period` |
| **DBDD §16.8** | At most one prepaid account per student + semester | PostgreSQL `UniqueConstraint(fields=[student, semester])` | ✅ Verified via `test_invariant_8_unique_balance_account` |
| **DBDD §16.9** | Unique meal occurrence per mess + date + meal type | PostgreSQL `UniqueConstraint(fields=[mess, meal_date, meal_type])` | ✅ Verified via `test_invariant_9_unique_meal_occurrence` |
| **DBDD §16.10** | No duplicate FoodItem in same MenuMeal | PostgreSQL `UniqueConstraint(fields=[menu_meal, food_item])` | ✅ Verified via `test_invariant_10_unique_food_item_in_menu_meal` |
| **DBDD §16.11** | Price snapshot immutability on transactions | PostgreSQL `BEFORE UPDATE` trigger function | ✅ Verified via `test_invariant_11_price_snapshot_immutability` |
| **DBDD §16.12** | Append-only tables (Audit, Ledger, Verification, etc.) | Django `InsertOnlyModel` + PostgreSQL `BEFORE UPDATE OR DELETE` trigger | ✅ Verified via `test_invariant_12_insert_only_tables` |
| **DBDD §8.3 / DBDD-AC-22** | Locked billing period rejects bill/line/adjustment mutation | PostgreSQL `BEFORE INSERT/UPDATE/DELETE` triggers | ✅ Verified via `test_locked_bill_guard` |
| **DBDD §18.2 / DBDD-AC-17** | Concurrent duplicate meal attendance insertion | PostgreSQL transactions & unique constraints | ✅ Verified via `test_concurrency_duplicate_meal_attendance` |
| **DBDD §17** | Foreign Key delete rule = RESTRICT / PROTECT | Django ORM `on_delete=models.PROTECT` across all FKs | ✅ Verified |
| **DBDD §18.3** | Optimistic concurrency control counter on mutable models | BigIntegerField `version` on all `VersionedModel` classes | ✅ Verified |
| **DBDD §21 / DEC-11** | Default seed migrations for Roles, MealTypes, Settings | Idempotent `RunPython` data migrations | ✅ Verified via `test_seeds_present_and_correct` |
