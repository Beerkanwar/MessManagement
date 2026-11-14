// Manager Destination Placeholder Screen with Hardware Back Confirmation per Build Item 7
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, SafeAreaView, TouchableOpacity, BackHandler } from 'react-native';
import { colors, spacing, radius } from '../../design/tokens';
import { Card } from '../../components/Card';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { useMealSessionStore } from '../../state/mealSessionStore';

export interface ManagerDestinationPlaceholderProps {
  route: {
    name: string;
    params?: { title?: string; description?: string };
  };
  navigation: {
    goBack: () => void;
  };
}

export const ManagerDestinationPlaceholderScreen: React.FC<ManagerDestinationPlaceholderProps> = ({
  route,
  navigation,
}) => {
  const isMealRecordScreen = route.name === 'record-meal';
  const { isSessionActive, endSession } = useMealSessionStore();
  const [showExitConfirm, setShowExitConfirm] = useState(false);

  useEffect(() => {
    if (!isMealRecordScreen) return;

    // Build Item 7: Android hardware back inside a meal session asks for confirmation
    const backAction = () => {
      if (isSessionActive || isMealRecordScreen) {
        setShowExitConfirm(true);
        return true; // prevent default back navigation
      }
      return false;
    };

    const backHandler = BackHandler.addEventListener('hardwareBackPress', backAction);
    return () => backHandler.remove();
  }, [isMealRecordScreen, isSessionActive]);

  const handleConfirmExit = () => {
    setShowExitConfirm(false);
    if (isSessionActive) {
      endSession();
    }
    navigation.goBack();
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.navBar}>
        <TouchableOpacity
          onPress={() => {
            if (isMealRecordScreen && (isSessionActive || true)) {
              setShowExitConfirm(true);
            } else {
              navigation.goBack();
            }
          }}
          style={styles.backButton}
        >
          <Text style={styles.backButtonText}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.screenTitle}>{route.params?.title || route.name}</Text>
        <View style={styles.placeholder} />
      </View>

      <View style={styles.container}>
        <Card style={styles.card}>
          <View style={styles.iconCircle}>
            <Text style={styles.iconText}>{isMealRecordScreen ? '📷' : '📦'}</Text>
          </View>
          <Text style={styles.title}>{route.params?.title || route.name}</Text>
          <Text style={styles.phaseBadge}>Scheduled for Phase 20</Text>
          <Text style={styles.description}>
            {route.params?.description ||
              'This manager feature will be fully implemented in Phase 20 (Mobile: Manager scanning & offline sync).'}
          </Text>

          {isMealRecordScreen && (
            <View style={styles.sessionNote}>
              <Text style={styles.sessionNoteTitle}>Session Protection Active</Text>
              <Text style={styles.sessionNoteText}>
                Android hardware back navigation requires confirmation during an active meal scanning session.
              </Text>
            </View>
          )}
        </Card>
      </View>

      <ConfirmDialog
        visible={showExitConfirm}
        title="Exit Meal Session?"
        description="Are you sure you want to exit the current meal recording session? Any unconfirmed scans should be synchronized."
        confirmLabel="Exit Session"
        cancelLabel="Stay in Session"
        onConfirm={handleConfirmExit}
        onClose={() => setShowExitConfirm(false)}
        variant="danger"
      />
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
  sessionNote: {
    marginTop: spacing.s4,
    padding: spacing.s3,
    backgroundColor: '#FFFBEB',
    borderWidth: 1,
    borderColor: '#FCD34D',
    borderRadius: radius.card,
    alignItems: 'center',
  },
  sessionNoteTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#B45309',
    marginBottom: 4,
  },
  sessionNoteText: {
    fontSize: 12,
    color: '#92400E',
    textAlign: 'center',
    lineHeight: 16,
  },
});
