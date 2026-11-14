// Student Home Hub Screen per Build Item 7, App Flow §3
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
import { Button } from '../../components/Button';
import { useAuthStore } from '../../state/authStore';
import { DeprecatedVersionBanner } from '../common/DeprecatedVersionBanner';

export interface StudentHomeScreenProps {
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

const STUDENT_DESTINATIONS: DestinationItem[] = [
  {
    id: 'my-qr',
    title: 'My QR Code',
    description: 'Dynamic HMAC QR token for meal attendance verification',
    icon: '📱',
    phase: 'Phase 19',
    badge: '30s Refresh',
  },
  {
    id: 'attendance',
    title: 'Meal Attendance & History',
    description: 'View recorded meals and session check-ins',
    icon: '📅',
    phase: 'Phase 19',
  },
  {
    id: 'billing',
    title: 'Monthly Mess Bill & Dues',
    description: 'Inspect billing statements, fixed fee, and extras breakdown',
    icon: '💳',
    phase: 'Phase 19',
  },
  {
    id: 'wallet',
    title: 'Wallet Balance & Transactions',
    description: 'View prepaid mess balance and payment ledger',
    icon: '💰',
    phase: 'Phase 19',
  },
  {
    id: 'extras',
    title: 'Daily Extras Purchase',
    description: 'Browse available extras items and request purchases',
    icon: '🍲',
    phase: 'Phase 19',
  },
  {
    id: 'pause',
    title: 'Meal Pause Request',
    description: 'Request advance meal pause with 3-qualifying slots lead time',
    icon: '⏸️',
    phase: 'Phase 19',
  },
  {
    id: 'feedback',
    title: 'Daily Menu & Feedback',
    description: 'Today’s meal menu, ratings, and mess manager feedback',
    icon: '⭐',
    phase: 'Phase 19',
  },
];

export const StudentHomeScreen: React.FC<StudentHomeScreenProps> = ({ navigation }) => {
  const { user, assignment, signOut } = useAuthStore();

  return (
    <SafeAreaView style={styles.safeArea}>
      <DeprecatedVersionBanner />

      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Student Profile Card */}
        <Card style={styles.profileCard}>
          <View style={styles.profileHeader}>
            <View style={styles.avatarCircle}>
              <Text style={styles.avatarText}>
                {user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'S'}
              </Text>
            </View>
            <View style={styles.profileDetails}>
              <Text style={styles.studentName}>{user?.full_name || 'Student'}</Text>
              <Text style={styles.studentRoll}>
                Roll: {assignment?.roll_number || 'N/A'} • Room {assignment?.room_number || 'N/A'}
              </Text>
              <Text style={styles.hostelText}>
                {assignment?.hostel_name || 'Hostel'} • {assignment?.mess_name || 'Mess'}
              </Text>
            </View>
          </View>
        </Card>

        {/* Section Title */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Student Destinations (Phase 19)</Text>
          <Text style={styles.sectionSubtitle}>Mobile foundation active; select a destination</Text>
        </View>

        {/* 7 Destinations List */}
        {STUDENT_DESTINATIONS.map((dest) => (
          <TouchableOpacity
            key={dest.id}
            style={styles.destinationCard}
            onPress={() => navigation.navigate(dest.id)}
            activeOpacity={0.7}
            testID={`student-dest-${dest.id}`}
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
            testID="student-diagnostics-btn"
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
  studentName: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
  },
  studentRoll: {
    fontSize: 13,
    color: colors.textSecondary,
    marginTop: 2,
  },
  hostelText: {
    fontSize: 12,
    color: colors.textMuted,
    marginTop: 2,
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
    backgroundColor: colors.infoSubtle,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.chip,
    borderWidth: 1,
    borderColor: '#BFDBFE',
  },
  badgeChipText: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.info,
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
