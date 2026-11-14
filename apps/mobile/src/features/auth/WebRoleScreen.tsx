// Web Role Screen per Build Item 5, Test Checkpoints
import React from 'react';
import { View, Text, StyleSheet, SafeAreaView } from 'react-native';
import { colors } from '../../design/tokens';
import { Button } from '../../components/Button';
import { useAuthStore } from '../../state/authStore';

export const WebRoleScreen: React.FC = () => {
  const role = useAuthStore((s) => s.role);
  const signOut = useAuthStore((s) => s.signOut);

  const roleLabel = role === 'SUPER_ADMIN' ? 'Super Admin' : 'Hostel Clerk';

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container} testID="web-role-screen">
        <View style={styles.iconCircle}>
          <Text style={styles.iconText}>💻</Text>
        </View>

        <Text style={styles.title}>Web Portal Access Only</Text>
        <Text style={styles.message}>
          Your account has administrative web access ({roleLabel}).
          {'\n\n'}
          Staff roles (Hostel Clerk, Super Admin) must sign in using the web application on a desktop browser.
        </Text>

        <View style={styles.buttonWrapper}>
          <Button variant="secondary" onPress={() => signOut()}>
            Sign Out
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
    backgroundColor: colors.infoSubtle,
    borderWidth: 2,
    borderColor: colors.info,
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
