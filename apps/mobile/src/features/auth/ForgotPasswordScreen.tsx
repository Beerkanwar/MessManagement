// Forgot Password Screen (3-Step Wizard) per Build Item 5
import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  SafeAreaView,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
} from 'react-native';
import { colors, spacing, radius } from '../../design/tokens';
import { TextField } from '../../components/TextField';
import { Button } from '../../components/Button';
import { Card } from '../../components/Card';
import { apiClient } from '../../data/api/apiClient';

export interface ForgotPasswordScreenProps {
  navigation: {
    navigate: (route: string) => void;
    goBack: () => void;
  };
}

export const ForgotPasswordScreen: React.FC<ForgotPasswordScreenProps> = ({ navigation }) => {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Step 1: Request OTP
  const handleRequestOtp = async () => {
    setErrorMsg(null);
    if (!email.trim()) {
      setErrorMsg('Please enter your registered email address');
      return;
    }
    setLoading(true);
    try {
      await apiClient.requestPasswordReset(email.trim());
      setStep(2);
      setSuccessMsg('A 6-digit verification code has been sent to your email.');
    } catch (err: any) {
      setErrorMsg(err.message || 'Could not send verification code');
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Verify OTP
  const handleVerifyOtp = async () => {
    setErrorMsg(null);
    if (!otp.trim() || otp.trim().length !== 6) {
      setErrorMsg('Please enter the 6-digit verification code');
      return;
    }
    setLoading(true);
    try {
      const res = await apiClient.verifyPasswordResetOtp(email.trim(), otp.trim());
      if (res.reset_token) {
        setResetToken(res.reset_token);
      }
      setStep(3);
      setSuccessMsg('Code verified. Set your new password.');
    } catch (err: any) {
      setErrorMsg(err.message || 'Invalid or expired verification code');
    } finally {
      setLoading(false);
    }
  };

  // Step 3: Reset Password
  const handleResetPassword = async () => {
    setErrorMsg(null);
    if (!newPassword || newPassword.length < 8) {
      setErrorMsg('Password must be at least 8 characters long');
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorMsg('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      await apiClient.confirmPasswordReset({
        email: email.trim(),
        otp: otp.trim(),
        reset_token: resetToken || undefined,
        new_password: newPassword,
      });
      setSuccessMsg('Password reset successfully! You can now sign in.');
      setTimeout(() => {
        navigation.navigate('SignIn');
      }, 1500);
    } catch (err: any) {
      setErrorMsg(err.message || 'Could not reset password');
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
            <Text style={styles.stepIndicator}>Step {step} of 3</Text>
            <Text style={styles.title}>
              {step === 1 && 'Reset Password'}
              {step === 2 && 'Verify Code'}
              {step === 3 && 'New Password'}
            </Text>
            <Text style={styles.subtitle}>
              {step === 1 && 'Enter your registered email to receive a verification code.'}
              {step === 2 && `Enter the 6-digit code sent to ${email}`}
              {step === 3 && 'Create a strong new password for your account.'}
            </Text>
          </View>

          <Card style={styles.card}>
            {errorMsg && (
              <View style={styles.errorBanner} testID="forgot-error">
                <Text style={styles.errorBannerText}>{errorMsg}</Text>
              </View>
            )}

            {successMsg && (
              <View style={styles.successBanner} testID="forgot-success">
                <Text style={styles.successBannerText}>{successMsg}</Text>
              </View>
            )}

            {step === 1 && (
              <>
                <TextField
                  label="Registered Email"
                  placeholder="student@hostel.edu"
                  value={email}
                  onChangeText={setEmail}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                  testID="forgot-email-input"
                />
                <View style={styles.buttonWrapper}>
                  <Button
                    variant="primary"
                    size="lg"
                    loading={loading}
                    disabled={loading}
                    onPress={handleRequestOtp}
                  >
                    Send Verification Code
                  </Button>
                </View>
              </>
            )}

            {step === 2 && (
              <>
                <TextField
                  label="6-Digit Verification Code"
                  placeholder="123456"
                  value={otp}
                  onChangeText={setOtp}
                  keyboardType="number-pad"
                  maxLength={6}
                  testID="forgot-otp-input"
                />
                <View style={styles.buttonWrapper}>
                  <Button
                    variant="primary"
                    size="lg"
                    loading={loading}
                    disabled={loading}
                    onPress={handleVerifyOtp}
                  >
                    Verify Code
                  </Button>
                </View>
                <TouchableOpacity
                  style={styles.backStepButton}
                  onPress={() => setStep(1)}
                >
                  <Text style={styles.backStepText}>Change Email</Text>
                </TouchableOpacity>
              </>
            )}

            {step === 3 && (
              <>
                <TextField
                  label="New Password"
                  placeholder="At least 8 characters"
                  value={newPassword}
                  onChangeText={setNewPassword}
                  isPassword
                  testID="new-password-input"
                />
                <View style={styles.fieldSpacing} />
                <TextField
                  label="Confirm New Password"
                  placeholder="Re-enter password"
                  value={confirmPassword}
                  onChangeText={setConfirmPassword}
                  isPassword
                  testID="confirm-password-input"
                />
                <View style={styles.buttonWrapper}>
                  <Button
                    variant="primary"
                    size="lg"
                    loading={loading}
                    disabled={loading}
                    onPress={handleResetPassword}
                  >
                    Save New Password
                  </Button>
                </View>
              </>
            )}

            <TouchableOpacity
              style={styles.backToSignIn}
              onPress={() => navigation.navigate('SignIn')}
            >
              <Text style={styles.backToSignInText}>Return to Sign In</Text>
            </TouchableOpacity>
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
    justifyContent: 'center',
    padding: spacing.s4,
  },
  header: {
    alignItems: 'center',
    marginBottom: spacing.s6,
  },
  stepIndicator: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.primary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.s1,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.text,
    textAlign: 'center',
    marginBottom: spacing.s1,
  },
  subtitle: {
    fontSize: 14,
    color: colors.textSecondary,
    textAlign: 'center',
    maxWidth: 300,
  },
  card: {
    padding: spacing.s4,
  },
  fieldSpacing: {
    height: spacing.s3,
  },
  buttonWrapper: {
    marginTop: spacing.s4,
  },
  backStepButton: {
    alignItems: 'center',
    marginTop: spacing.s3,
  },
  backStepText: {
    fontSize: 13,
    color: colors.textSecondary,
  },
  backToSignIn: {
    alignItems: 'center',
    marginTop: spacing.s4,
    paddingTop: spacing.s3,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  backToSignInText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.primary,
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
