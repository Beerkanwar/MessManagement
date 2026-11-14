// Student Destination Placeholder Screen per SDD §7, Phase 18 Skeleton
import React from 'react';
import { View, Text, StyleSheet, SafeAreaView, TouchableOpacity } from 'react-native';
import { colors, spacing, radius } from '../../design/tokens';
import { Card } from '../../components/Card';
import { preventScreenCaptureAsync, allowScreenCaptureAsync } from '../../platform/screenCapture';

export interface StudentDestinationPlaceholderProps {
  route: {
    name: string;
    params?: { title?: string; description?: string };
  };
  navigation: {
    goBack: () => void;
  };
}

export const StudentDestinationPlaceholderScreen: React.FC<StudentDestinationPlaceholderProps> = ({
  route,
  navigation,
}) => {
  const isQrScreen = route.name === 'my-qr';

  React.useEffect(() => {
    if (isQrScreen) {
      // Build Item 10: Screen capture prevention on My QR
      preventScreenCaptureAsync();
      return () => {
        allowScreenCaptureAsync();
      };
    }
  }, [isQrScreen]);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.navBar}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Text style={styles.backButtonText}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.screenTitle}>{route.params?.title || route.name}</Text>
        <View style={styles.placeholder} />
      </View>

      <View style={styles.container}>
        <Card style={styles.card}>
          <View style={styles.iconCircle}>
            <Text style={styles.iconText}>{isQrScreen ? '🛡️' : '📋'}</Text>
          </View>
          <Text style={styles.title}>{route.params?.title || route.name}</Text>
          <Text style={styles.phaseBadge}>Scheduled for Phase 19</Text>
          <Text style={styles.description}>
            {route.params?.description ||
              'This student feature will be fully implemented in Phase 19 (Mobile: Student app).'}
          </Text>

          {isQrScreen && (
            <View style={styles.securityNote}>
              <Text style={styles.securityNoteTitle}>🔒 Security Protection Active</Text>
              <Text style={styles.securityNoteText}>
                Screen-capture prevention is engaged on this screen to safeguard dynamic QR meal credentials.
              </Text>
            </View>
          )}
        </Card>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  navBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.s4,
    paddingVertical: spacing.s2,
  },
  backButton: {
    paddingVertical: spacing.s1,
    paddingHorizontal: spacing.s2,
  },
  backButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.primary,
  },
  screenTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: colors.text,
  },
  placeholder: {
    width: 60,
  },
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.s4,
  },
  card: {
    width: '100%',
    padding: spacing.s6,
    alignItems: 'center',
  },
  iconCircle: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: colors.primarySubtle,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.s3,
  },
  iconText: {
    fontSize: 28,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.s1,
    textAlign: 'center',
  },
  phaseBadge: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
    backgroundColor: colors.primarySubtle,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.chip,
    marginBottom: spacing.s3,
  },
  description: {
    fontSize: 14,
    color: colors.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
  },
  securityNote: {
    marginTop: spacing.s4,
    padding: spacing.s3,
    backgroundColor: '#F0FDF4',
    borderWidth: 1,
    borderColor: '#86EFAC',
    borderRadius: radius.card,
    alignItems: 'center',
  },
  securityNoteTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#166534',
    marginBottom: 4,
  },
  securityNoteText: {
    fontSize: 12,
    color: '#15803D',
    textAlign: 'center',
    lineHeight: 16,
  },
});
