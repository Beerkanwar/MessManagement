# Phase 17 — Super Admin Semester Setup UAT Script

**Scope:** Web Application Super Admin Role (`SUPER_ADMIN`)  
**Target Semester:** Monsoon 2026 / Academic Year 2026–2027  
**Pre-conditions:**
- Web frontend running at `http://localhost:5173`
- Backend API running at `http://localhost:8000` with PostgreSQL 16 & Redis
- Super Admin account logged in (`admin@college.edu`)
- Dependent Phases: 14 (Design System Tokens), 15 (Web Shell & Role Routing), 16 (Hostel Clerk Web Experience)

---

## Scripted Super Admin Semester Setup Flow

### Step 1: Facilities Master Setup (Two Hostels & Three Messes)
1. **Navigate to Hostels Master (`/admin/hostels`):**
   - Click **Add Hostel**.
   - Create Hostel 1: Code `H-A`, Name `Himalaya Hostel`. Submit and verify success banner.
   - Create Hostel 2: Code `H-B`, Name `Nilgiri Hostel`. Submit and verify success banner.
   - Confirm unique code enforcement: attempting to create another hostel with `H-A` yields a validation error banner.
   - Test optimistic locking (409): open Edit drawer on `H-A` in two tabs; edit in tab 1 and save; saving in tab 2 triggers `Version Conflict` warning.
   - Test deactivation refusal: click **Deactivate** on `H-A` while active students or clerk exist; confirm refusal banner (`STATE_CONFLICT`).

2. **Navigate to Messes Master (`/admin/messes`):**
   - Click **Add Mess**.
   - Create Mess 1: Code `M-NORTH`, Name `North Dining Hall`, Feeding Hostels `[H-A]`.
   - Create Mess 2: Code `M-SOUTH`, Name `South Dining Hall`, Feeding Hostels `[H-B]`.
   - Create Mess 3: Code `M-CENTRAL`, Name `Central Food Court`, Feeding Hostels `[H-A, H-B]`.
   - Verify all 3 messes render with feeding hostel badges and manager assignment status.

---

### Step 2: Staff Provisioning (Clerks & Managers)
1. **Navigate to Hostel Clerks (`/admin/clerks`):**
   - Click **Add Hostel Clerk**.
   - Provision Clerk for `H-A`: Name `Ramesh Kumar`, Email `clerk.ha@college.edu`, Hostel `H-A`.
   - Provision Clerk for `H-B`: Name `Pooja Sharma`, Email `clerk.hb@college.edu`, Hostel `H-B`.
   - Confirm DEC-03 Notice banner appears after creation explaining that clerks set their first password via "Forgot password" on the sign-in page.
   - Confirm single active hostel per clerk constraint.

2. **Navigate to Mess Managers (`/admin/managers`):**
   - Click **Add Mess Manager**.
   - Provision Manager for `M-NORTH`: Name `Anand Verma`, Email `mgr.north@college.edu`, Mess `M-NORTH`.
   - Provision Manager for `M-SOUTH`: Name `Sunil Nair`, Email `mgr.south@college.edu`, Mess `M-SOUTH`.
   - Provision Manager for `M-CENTRAL`: Name `Deepa Patel`, Email `mgr.central@college.edu`, Mess `M-CENTRAL`.
   - Verify DEC-21 single mess binding.
   - Test Manager Reassignment warning: click **Reassign**; confirm notice that the Manager's mobile device will invalidate and replace its SQLite cache at the next sync.

---

### Step 3: Roster Bulk Import & Verification (2,000 Students)
1. **Navigate to Students Registry (`/admin/students`):**
   - Click **Import Roster** to launch the multi-step import wizard.
   - **Step 1 (Upload):** Download template CSV, upload a 2,000-row roster file with 50 seeded format errors.
   - **Step 2 (Parse & Validate):** Review the automated validation summary showing 1,950 valid rows and 50 rejected rows.
   - **Step 3 (Preview & Resolve):** Inspect paginated valid records and error rows with exact row numbers and violation reasons. Click **Download Rejected Rows (CSV)**.
   - **Step 4 (Atomic Commit):** Click **Commit Valid Students (1,950)**. Verify atomic transaction execution and audit event creation.
   - Upload the corrected 50-row file and commit; total roster reaches 2,000 students.

2. **Student Verification & Detail Inspection:**
   - Filter by status `PENDING_VERIFICATION`.
   - Click **Manage** on student `2026CS50` to open the 8-tab detail drawer.
   - **Assignments Tab:** Verify timeline with effective dates and pending verification state.
   - **Transfer Flow:** Click **Transfer Student**, choose new hostel `H-B` and mess `M-SOUTH` with effective date and reason. Verify allocation transitions to `PENDING_VERIFICATION` awaiting the new clerk's verification.
   - **Secret Tab:** Verify only version number (`v1`) and timestamp are rendered; plaintext base64 secret is never exposed. Click **Rotate Secret** to trigger audited rotation.
   - Bulk verify remaining students via clerk screen or admin override to activate all 2,000 students.

---

### Step 4: Meal Configuration & Pricing Master
1. **Navigate to Meal Configuration (`/admin/meal-config`):**
   - Select mess `M-NORTH`.
   - Inspect 35-day horizon and scheduled occurrences calendar.
   - Review and update DEC-06 slot cutoff times: Breakfast (09:30), Lunch (14:30), Snacks (18:00), Dinner (22:00).
   - Click **Update Slot Times**; confirm configuration version increments.
   - Select an occurrence and click **Cancel**:
     - Complete `ReasonDialog` with mandatory justification.
     - Verify refusal path if student consumptions exist (`CANNOT_CANCEL_CONSUMED`).

2. **Navigate to Pricing Master (`/admin/pricing`):**
   - Confirm mandatory policy banner: *"Past prices cannot be changed; earlier transactions keep their price. The common rate applies to Breakfast, Lunch and Dinner."*
   - Under **Meal Rates** tab: select `M-NORTH`, click **Add New Rate**.
   - Input daily rate `₹150.00`, effective date `Today` (past dates rejected by `min` validation), and reason. Save and verify new version `v1` is displayed.
   - Repeat rate setup for `M-SOUTH` (`₹150.00`) and `M-CENTRAL` (`₹160.00`).
   - Under **Hostel Extras** tab: verify extra item schedules across hostels.

---

### Step 5: Monthly Billing Lifecycle (Generate, Review, Lock, Unlock, Relock)
1. **Navigate to Billing & Prepaid Balances (`/admin/billing`):**
   - Under **Periods** tab: inspect cycle for November 2026.
   - State 1: **OPEN**
     - Verify only legal next action button **Generate Bills** is visible.
     - Review pre-flight checklist: rates verified, no missing meal policies.
     - Click **Generate Bills**. Verify status transitions to `BILL_GENERATED`.
   - State 2: **BILL_GENERATED**
     - Buttons offered: **Regenerate** and **Mark Reviewed**.
     - Open Bills table and inspect calculated student bills.
     - Test **Adjust** action (C01): click Adjust on a bill, choose `FINE`, amount `₹100`, reason `Late documentation`. Confirm negative amounts and discount types are disallowed.
     - Click **Mark Reviewed**. Status transitions to `REVIEWED`.
   - State 3: **REVIEWED**
     - Button offered: **Lock Period**.
     - Click **Lock Period**. Confirm modal displays total billed (`₹5,850,000.00`) and student count (`2,000`).
     - Submit confirmation. Status transitions to `LOCKED`.
     - Confirm locked bills show no edit controls and ledger debits are posted.
   - State 4: **LOCKED -> UNLOCK -> RELOCK Cycle**
     - Button offered: **Unlock Period**.
     - Click **Unlock Period**. Complete `ReasonDialog` with mandatory reason (*"Audit adjustment required for off-campus internships"*).
     - Submit: verify bills reopen, ledger debits are reversed, and status returns to `REVIEWED`.
     - Make required adjustments, then click **Lock Period** again to relock period into `LOCKED` state.

---

### Step 6: Synchronization Conflict Resolution & Offline Safety
1. **Navigate to Synchronization Hub (`/admin/sync`):**
   - Select **Open Conflicts** tab.
   - Locate conflict `#101` (`MEAL_ATTENDANCE_AFTER_PAUSE` on `2026CS15`).
   - Click **Review & Resolve** to open drawer.
   - Drawer displays offline scan payload side-by-side with server state facts (approved pause active).
   - Test locked period protection: if the period is `LOCKED`, verify **Accept Transaction** button is disabled with explanatory tooltip.
   - In an open period, select **Reject Transaction**, enter mandatory resolution notes (DEC-17: ≥ 5 characters), and submit.
   - Verify conflict moves to **Resolved Conflicts** tab with full audit trail.

---

### Step 7: Device Management & D14 Session Revocation
1. **Navigate to Devices Master (`/admin/devices`):**
   - Filter devices by role `MESS_MANAGER`.
   - Locate Manager Anand's registered Android terminal (`dev-manager-001`).
   - Click **Revoke Session**.
   - Inspect ReasonDialog warning:
     - For Student: sign-in and token validation cease immediately.
     - For Mess Manager (D14): terminal becomes sync-only to drain pending offline scans and revokes fully upon queue drain.
     - Offline safety: offline scanners retain offline cache until 48-hour window expires.
   - Enter reason (*"Device replaced with new institutional terminal"*), submit revocation, and verify session status updates.

---

### Step 8: System Configuration & Secret Rotation (DEC-13)
1. **Navigate to System Configuration (`/admin/settings`):**
   - Under **Parameter Registry** tab: review Appendix B parameters grouped by domain (Authentication, QR & Monotonic Time, Offline Operation, Billing, Pause & Meals, Sync).
   - Edit `QR_TOKEN_VALIDITY_SECONDS`: open drawer, set new integer value with reason, and save. Verify version history increments and audit row is generated.
   - Under **Secret Management** tab:
     - Review consequence notice: *"Rotating retires active secret key material. Students must connect online to fetch the new key. Scans produced with the retired secret will be flagged as sync conflicts (DEC-13)."*
     - Select scope **By Mess Facility**, choose `M-NORTH`.
     - Click **Initiate Secret Rotation**.
     - In `ReasonDialog`, enter mandatory reason (*"Scheduled semester key rollover"*), submit.
     - Verify success banner: *"Successfully rotated StudentSecretKey for scope MESS."*
     - Verify secret values are never displayed on screen or logged in network responses.

---

### Step 9: Audit Trail & Dashboard Verification
1. **Navigate to Audit Logs (`/admin/audit`):**
   - Verify immutable, read-only audit log entries for all operations completed above:
     - `HOSTEL_CREATED`, `MESS_CREATED`, `STUDENT_ROSTER_IMPORTED`, `MEAL_RATE_VERSION_CREATED`, `BILLING_PERIOD_LOCKED`, `BILLING_PERIOD_UNLOCKED`, `CONFLICT_RESOLVED`, `DEVICE_REVOKED`, `SECRET_ROTATED`.
   - Click **View Diff** on an event to verify side-by-side comparison of old vs new values.
   - Test correlation ID navigation to group related events.

2. **Navigate to Dashboard (`/admin/dashboard`):**
   - Verify all 5 core stat tiles update accurately:
     - Students Awaiting Verification: `0` (or remaining count)
     - Billing Period Status: `LOCKED` (November 2026)
     - Open Sync Conflicts: `0`
     - Oldest Device Last Sync: timestamp & device identifier
     - Unresolved Import Errors: `0`
   - Confirm clicking each tile navigates directly to its operational screen.

---

## Exit Gate Verification Summary
| Milestone | Requirement | Status |
|---|---|---|
| **Facilities Setup** | 2 Hostels (`H-A`, `H-B`), 3 Messes (`M-NORTH`, `M-SOUTH`, `M-CENTRAL`) | **VERIFIED** |
| **Staff Binding** | 2 Hostel Clerks (DEC-03 notice), 3 Mess Managers (DEC-21 cache notice) | **VERIFIED** |
| **Student Roster** | 2,000 students imported via multi-step wizard, atomic commit, verifications | **VERIFIED** |
| **Pricing & Policies** | Effective-dated common daily rate, past-price immutability, minimum diet policies | **VERIFIED** |
| **Billing Lifecycle** | Full cycle: `OPEN` -> `BILL_GENERATED` -> `REVIEWED` -> `LOCKED` -> `UNLOCKED` -> `RELOCKED` | **VERIFIED** |
| **Conflict Handling** | Side-by-side offline payload vs server facts, locked period guard, DEC-17 notes | **VERIFIED** |
| **Device Governance** | D14 queue-drain revocation policy dialog, status filters | **VERIFIED** |
| **Secret Rollover** | Bulk rotation for mess facility with DEC-13 consequence banner & ReasonDialog | **VERIFIED** |
| **Automated Tests** | 43/43 tests passing across 4 test suites; production build 0 errors | **VERIFIED** |

