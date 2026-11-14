# Phase 16 — Hostel Clerk UAT Script (Phase 25 Preparation)

**Scope:** Web Application Hostel Clerk Role (`HOSTEL_CLERK`)  
**Target Hostel:** Clerk Assigned Hostel (e.g., Hostel A / H-A)  
**Pre-conditions:**
- Web frontend running at `http://localhost:5173`
- Backend API running at `http://localhost:8000` with seeded test data
- Clerk account logged in (`clerk@hostel.edu`)

---

## Scripted Clerk Day Test Flow

### Step 1: Student Verification Journey
1. Navigate to `/clerk/verifications` via sidebar navigation.
2. Confirm header notice: *"You can verify student details but not edit them; ask the Super Admin to correct roster mistakes."*
3. Verify status tabs: **Pending** (active by default), **Verified**, **Rejected**.
4. Single Verification:
   - Click on a student row (e.g. `2026CS01` - John Doe).
   - Verify drawer opens with read-only record details and audit history.
   - Click **Verify Student**.
   - Verify local state transitions to `ACTIVE` and row moves to Verified tab.
5. Rejection:
   - Select another pending student row.
   - Click **Reject Assignment**.
   - Confirm that the `ReasonDialog` requires a mandatory justification (minimum 5 characters).
   - Enter reason and submit; verify student moves to Rejected tab.
6. Bulk Verification:
   - Select multiple checkboxes in the Pending list.
   - Click **Verify Selected (N)** in the toolbar.
   - Confirm confirmation dialog and inspect per-row results breakdown upon completion.

### Step 2: Menu Authoring & Publication Journey
1. Navigate to `/clerk/menu`.
2. Inspect monthly menus list and click **New Month**.
3. Choose Month and Year (e.g. next calendar month) with optional *"Copy previous month's weekday pattern"*.
4. Open the created Month Editor:
   - Left calendar shows day coverage indicators (Empty, Partial, Complete).
   - Right panel displays 4 meals: Breakfast, Lunch, Evening Snacks, Dinner.
5. Add Meal Items:
   - Select a date on the calendar.
   - Add food items to Breakfast from the master catalog search.
   - Attempt to add the same food item again; verify error message: *"\"[Item]\" is already in this meal [DBDD-AC-30]."*
   - Use **New Item** to add a new food item inline to the catalog.
   - Add notes to items, re-order using up/down controls, and click **Save Breakfast**.
6. Copy Day:
   - Click **Copy Day to Other Dates**, select 3 future dates, and confirm.
7. Student Preview:
   - Click **Preview as Student** and verify the month's schedule renders grouped by date.
8. Publish Menu:
   - Click **Publish Menu**.
   - Verify the pre-flight dialog identifies any days with no scheduled items.
   - Confirm publication; verify the status updates to `PUBLISHED` and the audit warning banner is displayed.

### Step 3: Extra Items & Effective Pricing Journey
1. Navigate to `/clerk/extras`.
2. View existing hostel-specific extra items and their current unit prices.
3. Click **New Extra Item**:
   - Provide item name (e.g. `Evening Tea & Samosa`) and initial price.
   - Confirm creation; verify uniqueness per hostel is enforced case-insensitively.
4. Add Effective-Dated Price:
   - Click the extra item to open the details drawer.
   - Verify pricing hint: *"Past prices cannot be changed; earlier transactions keep their price [SPEC DBDD §5.2]"*.
   - Attempt to enter an effective date in the past (e.g. yesterday); confirm validation refusal.
   - Enter a price effective today or a future date and submit.
   - Verify the price history table updates with the new version.
5. Status Toggle:
   - Toggle item active/inactive status and verify immediate update.

### Step 4: Bills & Ledger Inspection (Read-Only)
1. Navigate to `/clerk/bills`.
2. Verify read-only status and lack of any adjustment or billing manipulation controls.
3. Select an **OPEN** or **BILL_GENERATED** billing period:
   - Confirm notice banner: *"Draft figures: Not visible to students until locked by the Super Admin."*
4. Verify summary stat tiles: Billed Students count, Total Billed, Extras Total, Fees & Fines Total.
5. Click a student bill row:
   - Verify drawer displays calculation lines.
   - Confirm Diet Calculation breakdown highlights the larger of Policy Minimum Diets vs Actual Meal Count.
   - Confirm itemized Extra Items and Fees/Fines lines with author and reason.

### Step 5: Attendance & Audited Corrections Journey
1. Navigate to `/clerk/attendance`.
2. Filter attendance records by date range (default: last 7 days), mess, and meal type.
3. Click on a record to view consumption metadata and audit history.
4. Correct Attendance:
   - Click **Correct** on an effective attendance row.
   - Complete `ReasonDialog` with at least 5 characters.
   - Confirm the record is marked `Removed` and correction transaction is audited (`ATTENDANCE_CORRECTED`).
5. Add Missing Meal:
   - Click **Add Missing Meal**.
   - Input student ID/roll number, meal date, meal type, and reason (≥ 5 chars).
   - Confirm submission creates audited correction record.

### Step 6: Hostel Reports & Exports Journey
1. Navigate to `/clerk/reports`.
2. Verify hostel scope badge (`Scope: Hostel A`).
3. Select report from the left catalog (e.g. `Student Billing Summary`).
4. Validate 366-day rule:
   - Set preset to **Custom Range** and pick dates spanning > 366 days.
   - Click **Run Report**; verify rejection with clear explanation: *"Report date range cannot exceed 366 days. Please narrow the range."*
5. Set date range to **This Month** and click **Run Report**:
   - Verify results table renders with correct columns and summary totals row.
6. Test Export Buttons:
   - Trigger **CSV**, **XLSX**, and **PDF** exports; verify generated files open with matching totals.

