// Manager Home Hub Screen per Build Item 7, App Flow §4
import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { colors, spacing, radius } from '../../design/tokens';
import { Card } from '../../components/Card';
import { StatusBadge } from '../../components/StatusBadge';
import { Button } from '../../components/Button';
import { useAuthStore } from '../../state/authStore';
import { useAuthorizationStore } from '../../state/authorizationStore';
import { useTrustedTimeStore } from '../../state/trustedTimeStore';
import { useSyncStore } from '../../state/syncStore';
import { DeprecatedVersionBanner } from '../common/DeprecatedVersionBanner';

export interface ManagerHomeScreenProps {
  navigation: {
    navigate: (route: string) => void;
  };
}

interface DestinationItem {
  id: string;
  title: string;
  description: string;
  icon: string;
  phase: string;
  badge?: string;
}

const MANAGER_DESTINATIONS: DestinationItem[] = [
  {
    id: 'record-meal',
    title: 'Record Meal (Scan QR / Manual)',
    description: 'Real-time & offline meal check-in, camera scanner, roll number entry',
    icon: '📷',
    phase: 'Phase 20',
    badge: 'Camera Required',
  },
  {
    id: 'record-extras',
    title: 'Record Extras Purchase',
    description: 'Post immediate extras meal charges to student balances',
    icon: '🍲',
    phase: 'Phase 20',
  },
  {
    id: 'live-roster',
    title: 'Live Session Roster & Attendance Counts',
    description: 'Real-time headcounts, consumed statuses, and active meal session overview',
    icon: '📊',
    phase: 'Phase 20',
  },
  {
    id: 'sync-status',
    title: 'Sync Status & Offline Cache Diagnostics',
    description: 'Inspect pending SQLite transaction queue, flush sync, conflict review',
    icon: '🔄',
    phase: 'Phase 20',
  },
  {
    id: 'announcements',
    title: 'Mess Announcement',
    description: 'Broadcast notifications to registered mess students',
    icon: '📢',
    phase: 'Phase 20',
  },
  {
    id: 'daily-summary',
    title: 'Daily Mess Summary',
    description: 'Comprehensive day counts across Breakfast, Lunch, Snacks, and Dinner',
    icon: '📋',
    phase: 'Phase 20',
  },
];

export const ManagerHomeScreen: React.FC<ManagerHomeScreenProps> = ({ navigation }) => {
  const { user, assignment, signOut } = useAuthStore();
  const authStatus = useAuthorizationStore((s) => s.status);
  const timeStatus = useTrustedTimeStore((s) => s.status);
  const { status: syncStatus, pendingUploadCount } = useSyncStore();

  return (
    <SafeAreaView style={styles.safeArea}>
      <DeprecatedVersionBanner />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Manager Profile & Status Card */}
        <Card style={styles.profileCard}>
          <View style={styles.profileHeader}>
            <View style={styles.avatarCircle}>
              <Text style={styles.avatarText}>
                {user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'M'}
              </Text>
            </View>
            <View style={styles.profileDetails}>
              <Text style={styles.managerName}>{user?.full_name || 'Mess Manager'}</Text>
              <Text style={styles.staffId}>
                Staff ID: {assignment?.staff_id || 'N/A'}
              </Text>
              <Text style={styles.messName}>
                Assigned: {assignment?.mess_name || 'Central Mess'}
              </Text>
            </View>
          </View>

          {/* Live Status Indicators (SDD §126) */}
          <View style={styles.statusChipsRow}>
            <View style={styles.statusChip}>
              <Text style={styles.chipLabel}>Auth:</Text>
              <StatusBadge domain="managerAuthorization" status={authStatus} />
            </View>
            <View style={styles.statusChip}>
              <Text style={styles.chipLabel}>Time:</Text>
              <StatusBadge domain="trustedTime" status={timeStatus} />
            </View>
            <View style={styles.statusChip}>
              <Text style={styles.chipLabel}>Sync:</Text>
              <View style={styles.syncChip}>
                <Text style={styles.syncChipText}>
                  {pendingUploadCount > 0 ? `${pendingUploadCount} Pending` : syncStatus}
                </Text>
              </View>
            </View>
          </View>
        </Card>

        {/* Section Title */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Manager Destinations (Phase 20)</Text>
          <Text style={styles.sectionSubtitle}>Mobile foundation active; select a destination</Text>
        </View>

        {/* 6 Destinations List */}
        {MANAGER_DESTINATIONS.map((dest) => (
          <TouchableOpacity
            key={dest.id}
            style={styles.destinationCard}
            onPress={() => navigation.navigate(dest.id)}
            activeOpacity={0.7}
            testID={`manager-dest-${dest.id}`}
          >
            <View style={styles.destinationLeft}>
              <View style={styles.iconContainer}>
                <Text style={styles.destinationIcon}>{dest.icon}</Text>
              </View>
              <View style={styles.destinationTextWrapper}>
                <View style={styles.titleRow}>
                  <Text style={styles.destinationTitle}>{dest.title}</Text>
                  {dest.badge && (
                    <View style={styles.badgeChip}>
                      <Text style={styles.badgeChipText}>{dest.badge}</Text>
                    </View>
                  )}
                </View>
                <Text style={styles.destinationDescription}>{dest.description}</Text>
              </View>
            </View>
            <Text style={styles.arrowText}>›</Text>
          </TouchableOpacity>
        ))}

        {/* Footer Actions */}
        <View style={styles.footer}>
          <TouchableOpacity
            style={styles.diagnosticsLink}
            onPress={() => navigation.navigate('Diagnostics')}
            testID="manager-diagnostics-btn"
          >
            <Text style={styles.diagnosticsText}>⚙️ Diagnostics & Logs</Text>
          </TouchableOpacity>

          <View style={styles.signOutWrapper}>
            <Button variant="secondary" onPress={() => signOut()}>
              Sign Out
            </Button>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  scrollContent: {
    padding: spacing.s3,
  },
  profileCard: {
    padding: spacing.s3,
    marginBottom: spacing.s3,
  },
  profileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.s3,
  },
  avatarCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.s3,
  },
  avatarText: {
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: '700',
  },
  profileDetails: {
    flex: 1,
  },
  managerName: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
  },
  staffId: {
    fontSize: 13,
    color: colors.textSecondary,
    marginTop: 2,
  },
  messName: {
    fontSize: 12,
    color: colors.textMuted,
    marginTop: 2,
  },
  statusChipsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.s2,
    paddingTop: spacing.s2,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  statusChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  chipLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.textSecondary,
  },
  syncChip: {
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
    borderRadius: radius.chip,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  syncChipText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#1D4ED8',
  },
  sectionHeader: {
    marginBottom: spacing.s2,
    paddingHorizontal: spacing.s1,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
  },
  sectionSubtitle: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 2,
  },
  destinationCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.s3,
    marginBottom: spacing.s2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  destinationLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.primarySubtle,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.s3,
  },
  destinationIcon: {
    fontSize: 20,
  },
  destinationTextWrapper: {
    flex: 1,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  destinationTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: colors.text,
    marginRight: spacing.s1,
  },
  badgeChip: {
    backgroundColor: colors.warningSubtle,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.chip,
    borderWidth: 1,
    borderColor: '#FDE68A',
  },
  badgeChipText: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.warning,
  },
  destinationDescription: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 2,
  },
  arrowText: {
    fontSize: 22,
    color: colors.textMuted,
    marginLeft: spacing.s2,
  },
  footer: {
    marginTop: spacing.s3,
    alignItems: 'center',
  },
  diagnosticsLink: {
    paddingVertical: spacing.s2,
    marginBottom: spacing.s3,
  },
  diagnosticsText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.primary,
  },
  signOutWrapper: {
    width: '100%',
  },
});
