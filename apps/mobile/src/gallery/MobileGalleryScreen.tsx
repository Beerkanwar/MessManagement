import React, { useState } from 'react';
import {
  SafeAreaView,
  ScrollView,
  View,
  Text,
  StyleSheet,
  StatusBar,
} from 'react-native';
import {
  Button,
  TextField,
  PasswordField,
  QuantityStepper,
  Checkbox,
  Switch,
  StatusBadge,
  ListRow,
  Card,
  StatTile,
  Banner,
  BottomSheet,
  ConfirmDialog,
  ReasonDialog,
  MoneyText,
  DateText,
  QrDisplay,
  ScanResultOverlay,
  MobileScanResultType,
} from '../components';
import { colors, spacing } from '../design/tokens';

export const MobileGalleryScreen: React.FC = () => {
  const [stepperVal, setStepperVal] = useState(1);
  const [checkboxVal, setCheckboxVal] = useState(true);
  const [switchVal, setSwitchVal] = useState(true);
  const [sheetVisible, setSheetVisible] = useState(false);
  const [confirmVisible, setConfirmVisible] = useState(false);
  const [reasonVisible, setReasonVisible] = useState(false);
  const [overlayResult, setOverlayResult] = useState<MobileScanResultType | null>(null);

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.header}>
          <Text style={styles.badge}>PHASE 14 MOBILE GALLERY</Text>
          <Text style={styles.title}>Design System Components</Text>
          <Text style={styles.subtitle}>
            Arm's length glanceability, 48dp+ touch targets, plain StyleSheet tokens.
          </Text>
        </View>

        {/* Buttons */}
        <Card title="Buttons">
          <View style={styles.gap}>
            <Button onPress={() => {}}>Primary Action</Button>
            <Button variant="secondary" onPress={() => {}}>Secondary Action</Button>
            <Button variant="danger" onPress={() => {}}>Danger Action</Button>
            <Button variant="primary" loading onPress={() => {}}>Loading Button</Button>
            <Button variant="primary" disabled onPress={() => {}}>Disabled Button</Button>
          </View>
        </Card>

        {/* Form Inputs */}
        <Card title="Inputs & Controls">
          <TextField
            label="Roll Number"
            placeholder="e.g. 2026-CS-042"
            helperText="Uppercase alphanumeric format"
          />
          <TextField
            label="Input with Error"
            value="2026|CS|042"
            error="Pipes not allowed in roll numbers"
          />
          <PasswordField
            label="Manager Pin / Password"
            value="SecretPass"
          />
          <QuantityStepper
            label="Extra Chapati"
            value={stepperVal}
            onChange={setStepperVal}
          />
          <Checkbox
            label="Enforce strict single active manager"
            checked={checkboxVal}
            onChange={setCheckboxVal}
          />
          <Switch
            label="Enable Offline Attendance Mode"
            checked={switchVal}
            onChange={setSwitchVal}
          />
        </Card>

        {/* Status Badges */}
        <Card title="Domain Status Badges">
          <Text style={styles.subhead}>Sync Transactions</Text>
          <View style={styles.badgeRow}>
            <StatusBadge domain="syncTransaction" status="PENDING" />
            <StatusBadge domain="syncTransaction" status="SYNCHRONIZED" />
            <StatusBadge domain="syncTransaction" status="CONFLICT" />
            <StatusBadge domain="syncTransaction" status="REJECTED" />
          </View>

          <Text style={styles.subhead}>Manager Authorization & Trusted Time</Text>
          <View style={styles.badgeRow}>
            <StatusBadge domain="managerAuthorization" status="ACTIVE" />
            <StatusBadge domain="managerAuthorization" status="OFFLINE_GRACE" />
            <StatusBadge domain="trustedTime" status="VALID" />
            <StatusBadge domain="trustedTime" status="EXPIRED" />
          </View>
        </Card>

        {/* List Rows */}
        <Card title="Mobile List Rows (Touch Target >= 48dp)">
          <ListRow
            primaryText="Aarav Sharma"
            secondaryText="Roll: 2026-CS-001 • Hostel 1"
            metadata="Dinner at 20:15 IST"
            status="ACTIVE"
            onPress={() => setSheetVisible(true)}
          />
          <ListRow
            primaryText="Diya Patel"
            secondaryText="Roll: 2026-CS-002 • Hostel 1"
            metadata="Lunch at 13:05 IST"
            status="PENDING_VERIFICATION"
            onPress={() => setSheetVisible(true)}
          />
        </Card>

        {/* Currency & Dates */}
        <Card title="Conventions: Money & Dates">
          <View style={styles.conventionRow}>
            <Text style={styles.convLabel}>Prepaid Balance:</Text>
            <MoneyText amountInRupees={1250.0} />
          </View>
          <View style={styles.conventionRow}>
            <Text style={styles.convLabel}>Overdue Balance:</Text>
            <MoneyText amountInRupees={-350.5} />
          </View>
          <View style={styles.conventionRow}>
            <Text style={styles.convLabel}>IST Meal Timestamp:</Text>
            <DateText date="2026-08-21T06:12:00Z" includeTime />
          </View>
        </Card>

        {/* Banners */}
        <Card title="Banners">
          <Banner
            type="info"
            title="Online Sync Queued"
            message="Batch synchronization will execute automatically."
          />
          <Banner
            type="warning"
            title="Offline Grace Notice"
            message="Device has operated offline for 24 hours."
          />
          <Banner
            type="danger"
            title="Trusted Time Expired"
            message="Clock drift detected. Scanning locked."
          />
        </Card>

        {/* Dynamic QR */}
        <Card title="Dynamic QR Preview">
          <QrDisplay
            rollNumber="2026-CS-042"
            code="849201"
            remainingSeconds={18}
          />
        </Card>

        {/* Overlays & Modals */}
        <Card title="Dialogs & Full-Screen Scanner Overlays">
          <View style={styles.gap}>
            <Button variant="secondary" onPress={() => setConfirmVisible(true)}>
              Trigger Confirm Dialog
            </Button>
            <Button variant="danger" onPress={() => setReasonVisible(true)}>
              Trigger Reason Dialog (Min 10 chars)
            </Button>
            <Button variant="primary" onPress={() => setOverlayResult('SUCCESS')}>
              Preview SUCCESS Overlay
            </Button>
            <Button variant="secondary" onPress={() => setOverlayResult('DUPLICATE')}>
              Preview DUPLICATE Overlay
            </Button>
            <Button variant="danger" onPress={() => setOverlayResult('INVALID_CODE')}>
              Preview INVALID CODE Overlay
            </Button>
            <Button variant="danger" onPress={() => setOverlayResult('TIME_INVALID')}>
              Preview TIME INVALID Overlay
            </Button>
          </View>
        </Card>
      </ScrollView>

      {/* Bottom Sheet */}
      <BottomSheet
        visible={sheetVisible}
        onClose={() => setSheetVisible(false)}
        title="Student Details"
      >
        <Text style={styles.sheetBodyText}>Roll Number: 2026-CS-001</Text>
        <Text style={styles.sheetBodyText}>Name: Aarav Sharma</Text>
        <Text style={styles.sheetBodyText}>Mess: Main Mess North</Text>
        <Button onPress={() => setSheetVisible(false)} style={{ marginTop: spacing.s4 }}>
          Dismiss
        </Button>
      </BottomSheet>

      {/* Confirm Dialog */}
      <ConfirmDialog
        visible={confirmVisible}
        onClose={() => setConfirmVisible(false)}
        onConfirm={() => setConfirmVisible(false)}
        title="Confirm Meal Sync"
        description="Sync 124 recorded offline transactions to central server?"
      />

      {/* Reason Dialog */}
      <ReasonDialog
        visible={reasonVisible}
        onClose={() => setReasonVisible(false)}
        onConfirm={(reason) => {
          setReasonVisible(false);
          alert(`Reason submitted: ${reason}`);
        }}
        title="Manual Correction"
        description="Enter explanation for attendance correction (min 10 chars)."
        minLength={10}
      />

      {/* Full-Screen Scanner Result Overlay */}
      {overlayResult && (
        <ScanResultOverlay
          visible={Boolean(overlayResult)}
          resultType={overlayResult}
          studentName={overlayResult === 'SUCCESS' ? 'Aarav Sharma' : undefined}
          rollNumber={overlayResult === 'SUCCESS' ? '2026-CS-001' : undefined}
          mealType={overlayResult === 'SUCCESS' ? 'Dinner' : undefined}
          detailNote={overlayResult === 'DUPLICATE' ? 'Already recorded at 20:05 IST' : undefined}
          onDismiss={() => setOverlayResult(null)}
        />
      )}
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  container: {
    padding: spacing.s4,
  },
  header: {
    marginBottom: spacing.s4,
  },
  badge: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.primary,
    letterSpacing: 1,
    marginBottom: 4,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.text,
    fontFamily: 'Inter',
  },
  subtitle: {
    fontSize: 13,
    color: colors.textSecondary,
    marginTop: 2,
    fontFamily: 'Inter',
  },
  gap: {
    gap: spacing.s3,
  },
  subhead: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.textMuted,
    marginTop: spacing.s2,
    marginBottom: spacing.s2,
    textTransform: 'uppercase',
  },
  badgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.s2,
    marginBottom: spacing.s2,
  },
  conventionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: spacing.s2,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  convLabel: {
    fontSize: 14,
    color: colors.textSecondary,
  },
  sheetBodyText: {
    fontSize: 15,
    color: colors.text,
    marginVertical: 4,
    fontFamily: 'Inter',
  },
});

export default MobileGalleryScreen;

