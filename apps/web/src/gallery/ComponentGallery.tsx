import React, { useState } from 'react';
import {
  Button,
  TextField,
  PasswordField,
  Select,
  DatePicker,
  DateRangePicker,
  Textarea,
  QuantityStepper,
  Checkbox,
  Switch,
  StatusBadge,
  Card,
  StatTile,
  Banner,
  DataTable,
  FilterBar,
  Tabs,
  Drawer,
  ConfirmDialog,
  ReasonDialog,
  Toast,
  Skeleton,
  EmptyState,
  ErrorState,
  Stepper,
  MoneyText,
  DateText,
  QrDisplay,
  ScanResultOverlay,
  ScanResultType,
} from '../components';

export const ComponentGallery: React.FC = () => {
  // Interactive gallery state
  const [activeTab, setActiveTab] = useState('inputs');
  const [checkboxVal, setCheckboxVal] = useState(true);
  const [switchVal, setSwitchVal] = useState(true);
  const [stepperVal, setStepperVal] = useState(2);
  const [currentStep, setCurrentStep] = useState(1);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [isReasonOpen, setIsReasonOpen] = useState(false);
  const [activeOverlay, setActiveOverlay] = useState<ScanResultType | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [selectedTableKeys, setSelectedTableKeys] = useState<Set<string>>(new Set(['1']));
  const [searchQuery, setSearchQuery] = useState('');

  const tableData = [
    { id: '1', rollNumber: '2026-CS-001', name: 'Aarav Sharma', hostel: 'H1', balance: 1450.50, status: 'ACTIVE' },
    { id: '2', rollNumber: '2026-CS-002', name: 'Diya Patel', hostel: 'H1', balance: -220.00, status: 'PENDING_VERIFICATION' },
    { id: '3', rollNumber: '2026-EE-014', name: 'Kabir Singh', hostel: 'H2', balance: 0.00, status: 'REJECTED' },
  ];

  return (
    <div className="min-h-screen bg-bg text-text p-6 md:p-10 font-sans">
      <header className="max-w-6xl mx-auto mb-8 border-b border-border pb-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <span className="text-[12px] font-bold text-primary tracking-widest uppercase bg-primary-subtle px-2.5 py-1 rounded border border-primary-border">
              Phase 14 Design System
            </span>
            <h1 className="text-[28px] md:text-[32px] font-bold text-text mt-2">
              Component & Token Gallery
            </h1>
            <p className="text-[14px] text-text-secondary mt-1">
              Living design system catalog covering all color tokens, typography scales, accessibility rings, and component states.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => setToastMessage('Design token audit passed successfully!')}
            >
              Trigger Toast
            </Button>
            <Button
              variant="primary"
              onClick={() => setActiveOverlay('SUCCESS')}
            >
              Test Scan Overlay
            </Button>
          </div>
        </div>

        <div className="mt-6">
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              { key: 'inputs', label: 'Inputs & Controls' },
              { key: 'feedback', label: 'Feedback & Badges' },
              { key: 'data', label: 'Data Display & Tables' },
              { key: 'dialogs', label: 'Dialogs & Overlays' },
              { key: 'qr', label: 'QR & Attendance' },
            ]}
          />
        </div>
      </header>

      <main className="max-w-6xl mx-auto space-y-10">
        {/* TAB 1: Inputs & Controls */}
        {activeTab === 'inputs' && (
          <div className="space-y-8 animate-in fade-in duration-150">
            {/* Buttons */}
            <Card title="Buttons" subtitle="Primary, secondary, ghost, danger; normal, loading, and disabled states">
              <div className="flex flex-wrap items-center gap-4">
                <Button variant="primary">Primary Action</Button>
                <Button variant="primary" loading>Loading</Button>
                <Button variant="primary" disabled>Disabled</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="ghost">Ghost Button</Button>
                <Button variant="danger">Danger Action</Button>
                <Button variant="primary" size="sm">Small</Button>
                <Button variant="primary" size="lg">Large Target (52px)</Button>
              </div>
            </Card>

            {/* Form Fields */}
            <Card title="Text and Form Inputs" subtitle="Accessible labels, descriptions, and error states">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <TextField
                  label="Student Roll Number"
                  placeholder="e.g. 2026-CS-042"
                  helperText="Roll numbers must not contain pipes"
                />
                <TextField
                  label="Roll Number with Error"
                  defaultValue="2026|CS|042"
                  error="Roll numbers containing a pipe are strictly rejected"
                />
                <PasswordField
                  label="Manager Password"
                  defaultValue="SecretPass123"
                  helperText="Toggle visibility to inspect"
                />
                <Select
                  label="Assigned Hostel"
                  options={[
                    { value: 'h1', label: 'Hostel 1 (Boys)' },
                    { value: 'h2', label: 'Hostel 2 (Girls)' },
                    { value: 'h3', label: 'Hostel 3 (Postgrad)' },
                  ]}
                />
                <DatePicker label="Effective Date" defaultValue="2026-08-21" />
                <DateRangePicker label="Billing Period Range" startDate="2026-08-01" endDate="2026-08-31" />
                <div className="md:col-span-2">
                  <Textarea
                    label="Audit Remarks"
                    placeholder="Enter context for this administrative adjustment..."
                  />
                </div>
              </div>
            </Card>

            {/* Stepper, Checkbox, Switch */}
            <Card title="Toggles & Steppers" subtitle="Accessible interactive elements">
              <div className="flex flex-wrap items-center justify-between gap-6 p-2">
                <QuantityStepper
                  label="Extra Servings"
                  value={stepperVal}
                  onChange={setStepperVal}
                />
                <Checkbox
                  label="Active Mess Manager Assignment"
                  helperText="Enforces DEC-21 single active manager per mess"
                  checked={checkboxVal}
                  onChange={(e) => setCheckboxVal(e.target.checked)}
                />
                <Switch
                  label="Offline Sync Allowed"
                  helperText="Grace period expires in 48 hours"
                  checked={switchVal}
                  onChange={setSwitchVal}
                />
              </div>
            </Card>
          </div>
        )}

        {/* TAB 2: Feedback & Badges */}
        {activeTab === 'feedback' && (
          <div className="space-y-8 animate-in fade-in duration-150">
            {/* Status Badges */}
            <Card title="Status Badge Domain Mappings" subtitle="Every domain mapping strictly paired with color and icon">
              <div className="space-y-6">
                <div>
                  <h4 className="text-[13px] font-semibold text-text-secondary uppercase mb-2">Sync Transactions</h4>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge domain="syncTransaction" status="PENDING" />
                    <StatusBadge domain="syncTransaction" status="SENDING" />
                    <StatusBadge domain="syncTransaction" status="SYNCHRONIZED" />
                    <StatusBadge domain="syncTransaction" status="CONFLICT" />
                    <StatusBadge domain="syncTransaction" status="REJECTED" />
                  </div>
                </div>

                <div>
                  <h4 className="text-[13px] font-semibold text-text-secondary uppercase mb-2">Manager Authorization</h4>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge domain="managerAuthorization" status="ACTIVE" />
                    <StatusBadge domain="managerAuthorization" status="OFFLINE_NORMAL" />
                    <StatusBadge domain="managerAuthorization" status="OFFLINE_GRACE" />
                    <StatusBadge domain="managerAuthorization" status="SYNC_REQUIRED" />
                    <StatusBadge domain="managerAuthorization" status="REVOKE_PENDING_SYNC" />
                    <StatusBadge domain="managerAuthorization" status="REVOKED" />
                  </div>
                </div>

                <div>
                  <h4 className="text-[13px] font-semibold text-text-secondary uppercase mb-2">Trusted Time & Pause</h4>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge domain="trustedTime" status="VALID" />
                    <StatusBadge domain="trustedTime" status="EXPIRING" />
                    <StatusBadge domain="trustedTime" status="EXPIRED" />
                    <StatusBadge domain="trustedTime" status="REQUIRES_SYNC" />
                    <StatusBadge domain="pause" status="SCHEDULED" />
                    <StatusBadge domain="pause" status="ACTIVE" />
                    <StatusBadge domain="pause" status="COMPLETED" />
                    <StatusBadge domain="pause" status="CANCELLED" />
                  </div>
                </div>

                <div>
                  <h4 className="text-[13px] font-semibold text-text-secondary uppercase mb-2">Billing, Menu & Assignment</h4>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge domain="billingPeriod" status="OPEN" />
                    <StatusBadge domain="billingPeriod" status="BILL_GENERATED" />
                    <StatusBadge domain="billingPeriod" status="REVIEWED" />
                    <StatusBadge domain="billingPeriod" status="LOCKED" />
                    <StatusBadge domain="menu" status="DRAFT" />
                    <StatusBadge domain="menu" status="PUBLISHED" />
                    <StatusBadge domain="assignment" status="PENDING_VERIFICATION" />
                    <StatusBadge domain="assignment" status="ACTIVE" />
                    <StatusBadge domain="assignment" status="ENDED" />
                    <StatusBadge domain="assignment" status="REJECTED" />
                  </div>
                </div>
              </div>
            </Card>

            {/* Banners */}
            <Card title="Banners" subtitle="Used for offline, authorization and trusted-time alerts">
              <div className="space-y-4">
                <Banner
                  type="info"
                  title="Scheduled Synchronization"
                  message="Device is queued for batch sync at 01:00 IST."
                  action={{ label: 'Sync now', onClick: () => alert('Syncing...') }}
                />
                <Banner
                  type="warning"
                  title="Offline Grace Period (48 Hours)"
                  message="Device has operated offline for 24 hours. Sync within 24 hours to prevent scanning lockout."
                />
                <Banner
                  type="danger"
                  title="Trusted Time Expired"
                  message="System clock drift detected or reboot occurred. Scanning is blocked until time is re-anchored."
                  action={{ label: 'Re-anchor Time', onClick: () => alert('Re-anchoring...') }}
                />
              </div>
            </Card>

            {/* Error & Empty States */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <ErrorState
                errorCode="ERR_PAUSE_CONFLICT"
                message="Cannot record meal: student diet pause is already active for this date range."
                traceId="req-8f4b-220a-9d11"
                onRetry={() => alert('Retrying...')}
              />
              <EmptyState
                title="No Pending Verifications"
                description="All submitted student registrations have been reviewed by the Hostel Clerk."
                action={{ label: 'Refresh List', onClick: () => alert('Refreshed') }}
              />
            </div>

            {/* Skeleton */}
            <Card title="Skeleton Loading States">
              <div className="space-y-3">
                <Skeleton variant="text" width="60%" />
                <Skeleton variant="rectangular" height={40} />
                <div className="flex gap-4">
                  <Skeleton variant="circular" width={48} height={48} />
                  <div className="flex-1 space-y-2">
                    <Skeleton variant="text" width="80%" />
                    <Skeleton variant="text" width="40%" />
                  </div>
                </div>
              </div>
            </Card>
          </div>
        )}

        {/* TAB 3: Data Display & Tables */}
        {activeTab === 'data' && (
          <div className="space-y-8 animate-in fade-in duration-150">
            {/* Stat Tiles */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
              <StatTile
                label="Students Awaiting Verification"
                value="28"
                change="+5 today"
                changeType="negative"
              />
              <StatTile
                label="Average Daily Attendance"
                value="942"
                change="+3.4% this week"
                changeType="positive"
              />
              <StatTile
                label="Open Sync Conflicts"
                value="0"
                change="All synchronized"
                changeType="neutral"
              />
            </div>

            {/* Money and Date Conventions */}
            <Card title="Formatting Conventions" subtitle="Rupee symbol (₹), Indian en-IN grouping, IST timestamps">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-[15px]">
                <div className="p-4 bg-bg rounded-[8px] border border-border">
                  <span className="block text-[12px] font-semibold text-text-muted uppercase mb-1">
                    Currency Formatting
                  </span>
                  <div className="flex items-center justify-between">
                    <span>Positive Balance:</span>
                    <MoneyText amountInRupees={12500.5} />
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span>Negative Balance (Overdue):</span>
                    <MoneyText amountInRupees={-450.75} />
                  </div>
                </div>

                <div className="p-4 bg-bg rounded-[8px] border border-border">
                  <span className="block text-[12px] font-semibold text-text-muted uppercase mb-1">
                    Date & IST Timestamp Formatting
                  </span>
                  <div className="flex items-center justify-between">
                    <span>Date only:</span>
                    <DateText date="2026-08-21T00:00:00Z" />
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span>Date-time with IST tooltip:</span>
                    <DateText date="2026-08-21T06:12:00Z" includeTime />
                  </div>
                </div>
              </div>
            </Card>

            {/* DataTable */}
            <Card title="Data Table" subtitle="Server-side sortable, column toggling, sticky header, multi-row selection">
              <div className="space-y-4">
                <FilterBar
                  searchQuery={searchQuery}
                  onSearchChange={setSearchQuery}
                  searchPlaceholder="Filter students by name or roll number..."
                />
                <DataTable
                  selectable
                  selectedKeys={selectedTableKeys}
                  onSelectionChange={setSelectedTableKeys}
                  columns={[
                    { key: 'rollNumber', header: 'Roll Number', sortable: true },
                    { key: 'name', header: 'Student Name', sortable: true },
                    { key: 'hostel', header: 'Hostel' },
                    {
                      key: 'balance',
                      header: 'Prepaid Balance',
                      align: 'right',
                      sortable: true,
                      render: (row) => <MoneyText amountInRupees={row.balance} />,
                    },
                    {
                      key: 'status',
                      header: 'Status',
                      render: (row) => <StatusBadge domain="assignment" status={row.status} />,
                    },
                  ]}
                  data={tableData.filter((r) => !searchQuery || r.name.toLowerCase().includes(searchQuery.toLowerCase()) || r.rollNumber.toLowerCase().includes(searchQuery.toLowerCase()))}
                  keyExtractor={(row) => row.id}
                />
              </div>
            </Card>

            {/* Stepper Wizard */}
            <Card title="Import Wizard Stepper" subtitle="Used for student and meal imports">
              <Stepper
                currentStep={currentStep}
                onStepClick={setCurrentStep}
                steps={[
                  { id: 'upload', label: 'Upload CSV', description: 'File validation' },
                  { id: 'preview', label: 'Preview & Map', description: 'Check discrepancies' },
                  { id: 'commit', label: 'Apply Changes', description: 'Database save' },
                ]}
              />
            </Card>
          </div>
        )}

        {/* TAB 4: Dialogs & Overlays */}
        {activeTab === 'dialogs' && (
          <div className="space-y-8 animate-in fade-in duration-150">
            <Card title="Interactive Dialog Controls" subtitle="Mandatory reason validation and destructive confirmations">
              <div className="flex flex-wrap gap-4">
                <Button variant="secondary" onClick={() => setIsDrawerOpen(true)}>
                  Open Detail Drawer
                </Button>
                <Button variant="primary" onClick={() => setIsConfirmOpen(true)}>
                  Trigger ConfirmDialog
                </Button>
                <Button variant="danger" onClick={() => setIsReasonOpen(true)}>
                  Trigger ReasonDialog (Min 10 chars)
                </Button>
              </div>
            </Card>

            <Card title="Scanner Full-Screen Overlay Tests" subtitle="Glanceable under pressure at arm's length (Never color alone)">
              <div className="flex flex-wrap gap-3">
                <Button variant="primary" onClick={() => setActiveOverlay('SUCCESS')}>
                  Success (Green)
                </Button>
                <Button variant="secondary" onClick={() => setActiveOverlay('DUPLICATE')}>
                  Duplicate (Warning Amber)
                </Button>
                <Button variant="danger" onClick={() => setActiveOverlay('INVALID_CODE')}>
                  Invalid Code (Danger Red)
                </Button>
                <Button variant="danger" onClick={() => setActiveOverlay('UNKNOWN_ROLL')}>
                  Unknown Roll (Danger Red)
                </Button>
                <Button variant="secondary" onClick={() => setActiveOverlay('TIME_INVALID')}>
                  Time Invalid (Slate #1E293B)
                </Button>
              </div>
            </Card>
          </div>
        )}

        {/* TAB 5: QR & Attendance */}
        {activeTab === 'qr' && (
          <div className="space-y-8 animate-in fade-in duration-150">
            <Card title="Student Dynamic QR & Countdown Ring" subtitle="30-second TOTP step, left-padded 6 digits, tabular figures">
              <div className="py-6 flex justify-center">
                <QrDisplay
                  rollNumber="2026-CS-042"
                  payload="2026-CS-042|748291"
                  code="748291"
                  remainingSeconds={18}
                  totalSeconds={30}
                />
              </div>
            </Card>
          </div>
        )}
      </main>

      {/* Drawer */}
      <Drawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        title="Student Registration Details"
        subtitle="Review submission metadata"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsDrawerOpen(false)}>Close</Button>
            <Button variant="primary" onClick={() => setIsDrawerOpen(false)}>Verify Student</Button>
          </>
        }
      >
        <div className="space-y-4 text-[14px]">
          <p><strong>Roll Number:</strong> 2026-CS-001</p>
          <p><strong>Name:</strong> Aarav Sharma</p>
          <p><strong>Hostel:</strong> Hostel 1 (Boys)</p>
          <p><strong>Mess Assignment:</strong> Main Mess North</p>
          <p><strong>Prepaid Balance:</strong> <MoneyText amountInRupees={1450.50} /></p>
        </div>
      </Drawer>

      {/* Confirm Dialog */}
      <ConfirmDialog
        isOpen={isConfirmOpen}
        onClose={() => setIsConfirmOpen(false)}
        onConfirm={() => {
          setIsConfirmOpen(false);
          setToastMessage('Action confirmed successfully.');
        }}
        title="Lock Billing Period?"
        description="Locking this billing period will finalize all meal and extra charges. No further offline meals or corrections can modify these balances."
        confirmLabel="Lock Period"
      />

      {/* Reason Dialog */}
      <ReasonDialog
        isOpen={isReasonOpen}
        onClose={() => setIsReasonOpen(false)}
        onConfirm={(reason) => {
          setIsReasonOpen(false);
          setToastMessage(`Attendance corrected. Audited reason: "${reason}"`);
        }}
        title="Correct Attendance Record"
        description="Corrections never rewrite history. Please enter an audited mandatory explanation of at least 10 characters."
        confirmLabel="Apply Correction"
        variant="danger"
        minLength={10}
      />

      {/* Scanner Result Overlay */}
      {activeOverlay && (
        <ScanResultOverlay
          resultType={activeOverlay}
          studentName={activeOverlay === 'SUCCESS' ? 'Aarav Sharma' : activeOverlay === 'DUPLICATE' ? 'Diya Patel' : undefined}
          rollNumber={activeOverlay === 'SUCCESS' ? '2026-CS-001' : activeOverlay === 'DUPLICATE' ? '2026-CS-002' : undefined}
          mealType={activeOverlay === 'SUCCESS' ? 'Dinner (Main Mess)' : undefined}
          detailNote={activeOverlay === 'DUPLICATE' ? 'Already scanned at 19:42:15 IST' : undefined}
          onDismiss={() => setActiveOverlay(null)}
        />
      )}

      {/* Active Toast */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50">
          <Toast
            type="success"
            title="Notice"
            message={toastMessage}
            onDismiss={() => setToastMessage(null)}
          />
        </div>
      )}
    </div>
  );
};
export default ComponentGallery;

