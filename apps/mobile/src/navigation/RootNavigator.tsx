// Root Navigator per Build Item 5 & 7
import React, { useEffect } from 'react';
import { View, ActivityIndicator, StyleSheet, Text } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { useAuthStore } from '../state/authStore';
import { isVersionBlocked } from '../domain/auth/versionPolicy';
import { AuthStack } from './AuthStack';
import { StudentStack } from './StudentStack';
import { ManagerStack } from './ManagerStack';
import { UpdateRequiredScreen } from '../features/auth/UpdateRequiredScreen';
import { DeviceReplacedScreen } from '../features/auth/DeviceReplacedScreen';
import { WebRoleScreen } from '../features/auth/WebRoleScreen';
import { colors } from '../design/tokens';
import { networkMonitor } from '../platform/network';
import { useConnectivityStore } from '../state/connectivityStore';

export const RootNavigator: React.FC = () => {
  const {
    status,
    role,
    versionPolicy,
    isDeviceReplaced,
    isWebOnlyRole,
    restoreSession,
  } = useAuthStore();

  const setConnectivity = useConnectivityStore((s) => s.setConnectivity);

  useEffect(() => {
    // Restore session on app launch (Build Item 5)
    restoreSession();

    // Subscribe to network connectivity changes (SDD §94)
    const unsubscribe = networkMonitor.subscribe((netStatus) => {
      setConnectivity(netStatus.isConnected, netStatus.connectionType);
    });

    return () => {
      unsubscribe();
    };
  }, []);

  // 1. Check if application version is BLOCKED (DEC-18)
  if (isVersionBlocked(versionPolicy)) {
    return <UpdateRequiredScreen />;
  }

  // 2. Check if session was replaced by login on another device
  if (isDeviceReplaced) {
    return <DeviceReplacedScreen />;
  }

  // 3. Loading splash while restoring session on launch
  if (status === 'RESTORING') {
    return (
      <View style={styles.splashContainer} testID="splash-loading">
        <View style={styles.splashBadge}>
          <Text style={styles.splashLogoText}>HM</Text>
        </View>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.splashText}>Restoring session...</Text>
      </View>
    );
  }

  // 4. Authenticated state: route by user role
  if (status === 'SIGNED_IN') {
    if (isWebOnlyRole) {
      return <WebRoleScreen />;
    }

    if (role === 'STUDENT') {
      return (
        <NavigationContainer>
          <StudentStack />
        </NavigationContainer>
      );
    }

    if (role === 'MESS_MANAGER') {
      return (
        <NavigationContainer>
          <ManagerStack />
        </NavigationContainer>
      );
    }

    // Any other web role (Clerk, Admin)
    return <WebRoleScreen />;
  }

  // 5. Signed out state: render Auth stack
  return (
    <NavigationContainer>
      <AuthStack />
    </NavigationContainer>
  );
};

const styles = StyleSheet.create({
  splashContainer: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  splashBadge: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  splashLogoText: {
    color: '#FFFFFF',
    fontSize: 26,
    fontWeight: '800',
  },
  splashText: {
    marginTop: 16,
    fontSize: 14,
    color: colors.textSecondary,
    fontWeight: '500',
  },
});
