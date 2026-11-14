// Update Required Screen per DEC-18, Build Item 5
import React from 'react';
import { View, Text, StyleSheet, SafeAreaView, Linking } from 'react-native';
import { colors } from '../../design/tokens';
import { Button } from '../../components/Button';
import { useAuthStore } from '../../state/authStore';

export const UpdateRequiredScreen: React.FC = () => {
  const versionPolicy = useAuthStore((s) => s.versionPolicy);

  const message =
    versionPolicy?.force_update_message ||
    'This version of the application is no longer supported. Please update to the latest version to continue.';

  const handleUpdate = () => {
    // Open app store or update page
    Linking.openURL('https://mess.local/download').catch(() => {});
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container} testID="update-required-screen">
        <View style={styles.iconCircle}>
          <Text style={styles.iconText}>!</Text>
        </View>

        <Text style={styles.title}>Update Required</Text>
        <Text style={styles.message}>{message}</Text>

        <View style={styles.buttonWrapper}>
          <Button variant="primary" onPress={handleUpdate}>
            Update Application
          </Button>
        </View>
      </View>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  container: {
    flex: 1,
    padding: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.dangerSubtle,
    borderWidth: 2,
    borderColor: colors.danger,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
  },
  iconText: {
    fontSize: 32,
    fontWeight: '800',
    color: colors.danger,
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 12,
    textAlign: 'center',
  },
  message: {
    fontSize: 15,
    color: colors.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 32,
    maxWidth: 320,
  },
  buttonWrapper: {
    width: '100%',
    maxWidth: 280,
  },
});
