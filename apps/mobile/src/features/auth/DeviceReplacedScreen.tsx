// Device Replaced Screen per Build Item 5, Test Checkpoints
import React from 'react';
import { View, Text, StyleSheet, SafeAreaView } from 'react-native';
import { colors } from '../../design/tokens';
import { Button } from '../../components/Button';
import { useAuthStore } from '../../state/authStore';

export const DeviceReplacedScreen: React.FC = () => {
  const clearDeviceReplaced = useAuthStore((s) => s.clearDeviceReplaced);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container} testID="device-replaced-screen">
        <View style={styles.iconCircle}>
          <Text style={styles.iconText}>📱</Text>
        </View>

        <Text style={styles.title}>Signed In On Another Device</Text>
        <Text style={styles.message}>
          You signed in on another phone. Active mobile sessions are limited to one device at a time.
          {'\n\n'}
          To use this phone again, please sign in below.
        </Text>

        <View style={styles.buttonWrapper}>
          <Button variant="primary" onPress={clearDeviceReplaced}>
            Sign In On This Phone
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
    backgroundColor: colors.primarySubtle,
    borderWidth: 2,
    borderColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
  },
  iconText: {
    fontSize: 28,
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
