// Deprecated Version Banner per DEC-18, Build Item 5
import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { colors } from '../../design/tokens';
import { useAuthStore } from '../../state/authStore';
import { isVersionDeprecated } from '../../domain/auth/versionPolicy';

export const DeprecatedVersionBanner: React.FC = () => {
  const versionPolicy = useAuthStore((s) => s.versionPolicy);
  const [dismissed, setDismissed] = useState(false);

  if (!isVersionDeprecated(versionPolicy) || dismissed) {
    return null;
  }

  const message =
    versionPolicy?.force_update_message ||
    'A new version of Hostel Mess is available. Please update soon.';

  return (
    <View style={styles.container} testID="deprecated-version-banner">
      <View style={styles.content}>
        <Text style={styles.title}>Update Recommended</Text>
        <Text style={styles.message}>{message}</Text>
      </View>
      <TouchableOpacity
        style={styles.dismissButton}
        onPress={() => setDismissed(true)}
        accessibilityLabel="Dismiss update banner"
      >
        <Text style={styles.dismissText}>Dismiss</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.warningSubtle,
    borderBottomWidth: 1,
    borderBottomColor: colors.warning,
    paddingHorizontal: 16,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  content: {
    flex: 1,
    marginRight: 8,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.warning,
    marginBottom: 2,
  },
  message: {
    fontSize: 12,
    color: colors.text,
  },
  dismissButton: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 4,
    backgroundColor: '#FEF3C7',
  },
  dismissText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.warning,
  },
});
