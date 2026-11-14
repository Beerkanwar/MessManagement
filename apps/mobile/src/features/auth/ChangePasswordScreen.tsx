// Change Password Screen per Build Item 5
import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { colors, spacing, radius } from '../../design/tokens';
import { TextField } from '../../components/TextField';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { apiClient } from '../../data/api/apiClient';

export interface ChangePasswordScreenProps {
  navigation: {
    goBack: () => void;
  };
}

export const ChangePasswordScreen: React.FC<ChangePasswordScreenProps> = ({ navigation }) => {
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleSubmit = async () => {
    setErrorMsg(null);
    setSuccessMsg(null);

    if (!oldPassword) {
      setErrorMsg('Current password is required');
      return;
    }
    if (!newPassword || newPassword.length < 8) {
      setErrorMsg('New password must be at least 8 characters long');
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorMsg('New passwords do not match');
      return;
    }

    setLoading(true);
    try {
      await apiClient.changePassword(oldPassword, newPassword);
      setSuccessMsg('Password changed successfully.');
      setTimeout(() => {
        navigation.goBack();
      }, 1500);
    } catch (err: any) {
      setErrorMsg(err.message || 'Could not change password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.keyboardView}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.header}>
            <Text style={styles.title}>Change Password</Text>
            <Text style={styles.subtitle}>Enter your current password and choose a new one.</Text>
          </View>

          <Card style={styles.card}>
            {errorMsg && (
              <View style={styles.errorBanner}>
                <Text style={styles.errorBannerText}>{errorMsg}</Text>
              </View>
            )}

            {successMsg && (
              <View style={styles.successBanner}>
                <Text style={styles.successBannerText}>{successMsg}</Text>
              </View>
            )}

            <TextField
              label="Current Password"
              placeholder="Enter current password"
              value={oldPassword}
              onChangeText={setOldPassword}
              isPassword
              testID="old-password-input"
            />

            <View style={styles.fieldSpacing} />

            <TextField
              label="New Password"
              placeholder="At least 8 characters"
              value={newPassword}
              onChangeText={setNewPassword}
              isPassword
              testID="change-new-password-input"
            />

            <View style={styles.fieldSpacing} />

            <TextField
              label="Confirm New Password"
              placeholder="Re-enter new password"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              isPassword
              testID="change-confirm-password-input"
            />

            <View style={styles.buttonWrapper}>
              <Button
                variant="primary"
                size="lg"
                loading={loading}
                disabled={loading}
                onPress={handleSubmit}
              >
                Update Password
              </Button>
            </View>
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
};

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  keyboardView: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    padding: spacing.s4,
  },
  header: {
    marginBottom: spacing.s4,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.text,
    marginBottom: spacing.s1,
  },
  subtitle: {
    fontSize: 14,
    color: colors.textSecondary,
  },
  card: {
    padding: spacing.s4,
  },
  fieldSpacing: {
    height: spacing.s3,
  },
  buttonWrapper: {
    marginTop: spacing.s6,
  },
  errorBanner: {
    backgroundColor: colors.dangerSubtle,
    borderWidth: 1,
    borderColor: colors.danger,
    borderRadius: radius.input,
    padding: spacing.s3,
    marginBottom: spacing.s3,
  },
  errorBannerText: {
    fontSize: 13,
    color: colors.danger,
  },
  successBanner: {
    backgroundColor: colors.successSubtle,
    borderWidth: 1,
    borderColor: colors.success,
    borderRadius: radius.input,
    padding: spacing.s3,
    marginBottom: spacing.s3,
  },
  successBannerText: {
    fontSize: 13,
    color: colors.success,
  },
});
