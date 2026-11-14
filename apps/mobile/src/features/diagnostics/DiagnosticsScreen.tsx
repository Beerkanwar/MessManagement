// Diagnostics Screen per Build Item 9, Test Checkpoints
import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  ScrollView,
  TouchableOpacity,
  Share,
} from 'react-native';
import { colors, spacing, radius } from '../../design/tokens';
import { Card } from '../../components/Card';
import { Button } from '../../components/Button';
import { logger, LogEntry } from '../../platform/diagnostics';
import { getDeviceInfoAsync, DeviceInfo } from '../../platform/device';
import { defaultSecureStorage } from '../../data/storage/secureStorage';
import { useAuthStore } from '../../state/authStore';
import { useConnectivityStore } from '../../state/connectivityStore';
import { useAuthorizationStore } from '../../state/authorizationStore';
import { useSyncStore } from '../../state/syncStore';
import { useTrustedTimeStore } from '../../state/trustedTimeStore';

export interface DiagnosticsScreenProps {
  navigation: {
    goBack: () => void;
  };
}

export const DiagnosticsScreen: React.FC<DiagnosticsScreenProps> = ({ navigation }) => {
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
  const [logEntries, setLogEntries] = useState<readonly LogEntry[]>([]);
  const [copiedStatus, setCopiedStatus] = useState<string | null>(null);

  const authState = useAuthStore();
  const connectivityState = useConnectivityStore();
  const authorizationState = useAuthorizationStore();
  const syncState = useSyncStore();
  const timeState = useTrustedTimeStore();

  const refreshLogs = () => {
    setLogEntries(logger.getEntries());
  };

  useEffect(() => {
    getDeviceInfoAsync(defaultSecureStorage).then(setDeviceInfo);
    refreshLogs();
  }, []);

  const handleCopyLogs = async () => {
    const rawLogs = logger.exportAsString();
    const fullDiagnosticDump = [
      `--- MESS MANAGEMENT DIAGNOSTICS DUMP ---`,
      `Timestamp: ${new Date().toISOString()}`,
      `App Version: ${deviceInfo?.appVersion || 'Unknown'}`,
      `Platform: ${deviceInfo?.platform || 'Unknown'}`,
      `Device ID: ${deviceInfo?.deviceId || 'Unknown'}`,
      `Rooted/Jailbroken: ${deviceInfo?.isRootedOrJailbroken ? 'YES (WARNING)' : 'No'}`,
      `Auth Status: ${authState.status}`,
      `User: ${authState.user?.email || 'None'}`,
      `Role: ${authState.role || 'None'}`,
      `Connectivity: ${connectivityState.isOnline ? 'Online' : 'Offline'} (${connectivityState.connectionType || 'unknown'})`,
      `Manager Auth: ${authorizationState.status}`,
      `Sync Status: ${syncState.status} (Pending: ${syncState.pendingUploadCount})`,
      `Trusted Time: ${timeState.status}`,
      `--- EVENT LOG BUFFER (${logEntries.length} entries) ---`,
      rawLogs,
    ].join('\n');

    try {
      if (Share && typeof Share.share === 'function') {
        await Share.share({
          message: fullDiagnosticDump,
          title: 'Mess Management Diagnostics',
        });
      }
      setCopiedStatus('Logs exported / ready to share');
    } catch {
      setCopiedStatus('Export complete');
    }

    setTimeout(() => setCopiedStatus(null), 3000);
  };

  const handleClearLogs = () => {
    logger.clear();
    refreshLogs();
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'ERROR':
        return colors.danger;
      case 'WARN':
        return colors.warning;
      case 'INFO':
        return colors.primary;
      default:
        return colors.textMuted;
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* Navigation Bar */}
        <View style={styles.navBar}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
            <Text style={styles.backButtonText}>‹ Back</Text>
          </TouchableOpacity>
          <Text style={styles.screenTitle}>Diagnostics</Text>
          <View style={styles.backButtonPlaceholder} />
        </View>

        {/* Security Warning if Rooted/Jailbroken */}
        {deviceInfo?.isRootedOrJailbroken && (
          <View style={styles.securityWarningCard} testID="jailbreak-warning">
            <Text style={styles.securityWarningTitle}>⚠️ Security Notice</Text>
            <Text style={styles.securityWarningBody}>
              This device appears to be rooted or jailbroken. Offline credential integrity may be compromised.
            </Text>
          </View>
        )}

        {/* Device Information Card */}
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>Device & Environment</Text>
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>App Version:</Text>
            <Text style={styles.metaValue}>{deviceInfo?.appVersion || 'Loading...'}</Text>
          </View>
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>Platform:</Text>
            <Text style={styles.metaValue}>{deviceInfo?.platform || 'Loading...'}</Text>
          </View>
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>Device ID:</Text>
            <Text style={styles.metaValueSmall} numberOfLines={1}>
              {deviceInfo?.deviceId || 'Loading...'}
            </Text>
          </View>
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>Integrity Check:</Text>
            <Text style={[styles.metaValue, deviceInfo?.isRootedOrJailbroken ? styles.textDanger : styles.textSuccess]}>
              {deviceInfo?.isRootedOrJailbroken ? 'Compromised (Root/Jailbreak)' : 'Secure Standard'}
            </Text>
          </View>
        </Card>

        {/* State Slices Summary Card */}
        <Card style={styles.card}>
          <Text style={styles.cardTitle}>State Slices (SDD §126)</Text>
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>Authentication:</Text>
            <Text style={styles.metaValue}>{authState.status}</Text>
          </View>
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>Connectivity:</Text>
            <Text style={styles.metaValue}>
              {connectivityState.isOnline ? 'ONLINE' : 'OFFLINE'} ({connectivityState.connectionType || 'unknown'})
            </Text>
          </View>
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>Manager Auth:</Text>
            <Text style={styles.metaValue}>{authorizationState.status}</Text>
          </View>
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>Synchronization:</Text>
            <Text style={styles.metaValue}>
              {syncState.status} ({syncState.pendingUploadCount} pending)
            </Text>
          </View>
          <View style={styles.metaRow}>
            <Text style={styles.metaLabel}>Trusted Time:</Text>
            <Text style={styles.metaValue}>{timeState.status}</Text>
          </View>
        </Card>

        {/* Ring Buffer Log Card */}
        <Card style={styles.card}>
          <View style={styles.logsCardHeader}>
            <Text style={styles.cardTitle}>Event Logs ({logEntries.length}/100)</Text>
            <TouchableOpacity onPress={refreshLogs} style={styles.refreshButton}>
              <Text style={styles.refreshText}>Refresh</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.redactionNote}>
            All tokens, passwords, OTPs, and QR payloads are automatically redacted.
          </Text>

          {copiedStatus && (
            <View style={styles.copiedBanner}>
              <Text style={styles.copiedBannerText}>{copiedStatus}</Text>
            </View>
          )}

          <ScrollView style={styles.logContainer} nestedScrollEnabled>
            {logEntries.length === 0 ? (
              <Text style={styles.emptyLogsText}>No log events recorded.</Text>
            ) : (
              logEntries.map((entry) => (
                <View key={entry.id} style={styles.logRow} testID="diagnostics-log-entry">
                  <View style={styles.logMetaRow}>
                    <Text style={[styles.logLevel, { color: getLevelColor(entry.level) }]}>
                      [{entry.level}]
                    </Text>
                    <Text style={styles.logTag}>{entry.tag}</Text>
                    <Text style={styles.logTime}>
                      {entry.timestamp.split('T')[1]?.replace('Z', '') || ''}
                    </Text>
                  </View>
                  <Text style={styles.logMessage}>{entry.message}</Text>
                  {entry.data && (
                    <Text style={styles.logData}>{JSON.stringify(entry.data)}</Text>
                  )}
                </View>
              ))
            )}
          </ScrollView>

          <View style={styles.logActionsRow}>
            <View style={styles.actionBtn}>
              <Button variant="primary" onPress={handleCopyLogs}>
                Export Logs
              </Button>
            </View>
            <View style={styles.actionBtn}>
              <Button variant="secondary" onPress={handleClearLogs}>
                Clear Logs
              </Button>
            </View>
          </View>
        </Card>
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
  navBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.s3,
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
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
  },
  backButtonPlaceholder: {
    width: 60,
  },
  securityWarningCard: {
    backgroundColor: colors.warningSubtle,
    borderWidth: 1,
    borderColor: colors.warning,
    borderRadius: radius.card,
    padding: spacing.s3,
    marginBottom: spacing.s3,
  },
  securityWarningTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.warning,
    marginBottom: 4,
  },
  securityWarningBody: {
    fontSize: 12,
    color: colors.text,
    lineHeight: 18,
  },
  card: {
    padding: spacing.s3,
    marginBottom: spacing.s3,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.s2,
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  metaLabel: {
    fontSize: 13,
    color: colors.textSecondary,
  },
  metaValue: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.text,
  },
  metaValueSmall: {
    fontSize: 12,
    fontWeight: '500',
    color: colors.textSecondary,
    maxWidth: 200,
  },
  textSuccess: {
    color: colors.success,
  },
  textDanger: {
    color: colors.danger,
  },
  logsCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  refreshButton: {
    paddingHorizontal: spacing.s2,
    paddingVertical: 2,
  },
  refreshText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.primary,
  },
  redactionNote: {
    fontSize: 11,
    color: colors.textMuted,
    marginBottom: spacing.s2,
  },
  copiedBanner: {
    backgroundColor: colors.successSubtle,
    borderRadius: radius.chip,
    padding: spacing.s1,
    marginBottom: spacing.s1,
    alignItems: 'center',
  },
  copiedBannerText: {
    fontSize: 12,
    color: colors.success,
    fontWeight: '600',
  },
  logContainer: {
    maxHeight: 280,
    backgroundColor: '#F1F5F9',
    borderRadius: radius.chip,
    padding: spacing.s2,
    marginBottom: spacing.s3,
  },
  emptyLogsText: {
    fontSize: 12,
    color: colors.textMuted,
    fontStyle: 'italic',
    textAlign: 'center',
    paddingVertical: spacing.s3,
  },
  logRow: {
    marginBottom: spacing.s1,
    paddingBottom: spacing.s1,
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  logMetaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  logLevel: {
    fontSize: 10,
    fontWeight: '700',
  },
  logTag: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.text,
  },
  logTime: {
    fontSize: 10,
    color: colors.textMuted,
    marginLeft: 'auto',
  },
  logMessage: {
    fontSize: 12,
    color: colors.text,
    marginTop: 2,
  },
  logData: {
    fontSize: 10,
    fontFamily: 'monospace',
    color: colors.textSecondary,
    marginTop: 2,
  },
  logActionsRow: {
    flexDirection: 'row',
    gap: spacing.s2,
  },
  actionBtn: {
    flex: 1,
  },
});
