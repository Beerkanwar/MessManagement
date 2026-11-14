// Sign In Screen per SDD §7, Build Item 5
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
import { useAuthStore } from '../../state/authStore';

export interface SignInScreenProps {
  navigation: {
    navigate: (route: string) => void;
  };
}

export const SignInScreen: React.FC<SignInScreenProps> = ({ navigation }) => {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<{ identifier?: string; password?: string }>({});

  const { signIn, isLoading, error, clearError } = useAuthStore();

  const validate = (): boolean => {
    const errors: { identifier?: string; password?: string } = {};
    if (!identifier.trim()) {
      errors.identifier = 'Roll Number, Staff ID, or Email is required';
    }
    if (!password) {
      errors.password = 'Password is required';
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async () => {
    clearError();
    if (!validate()) return;

    try {
      await signIn(identifier.trim(), password);
    } catch {
      // Error handled in store and displayed in UI
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
            <View style={styles.logoBadge}>
              <Text style={styles.logoText}>HM</Text>
            </View>
            <Text style={styles.title}>Hostel Mess Management</Text>
            <Text style={styles.subtitle}>Sign in with your student or staff credentials</Text>
          </View>

          <Card style={styles.card}>
            {error && (
              <View style={styles.errorBanner} testID="sign-in-error">
                <Text style={styles.errorBannerText}>{error.message}</Text>
              </View>
            )}

            <TextField
              label="Roll Number / Staff ID / Email"
              placeholder="e.g. 21BCE1001 or staff@mess.edu"
              value={identifier}
              onChangeText={(text) => {
                setIdentifier(text);
                if (fieldErrors.identifier) {
                  setFieldErrors((prev) => ({ ...prev, identifier: undefined }));
                }
              }}
              error={fieldErrors.identifier}
              autoCapitalize="none"
              autoCorrect={false}
              testID="identifier-input"
            />

            <View style={styles.fieldSpacing} />

            <TextField
              label="Password"
              placeholder="Enter your password"
              value={password}
              onChangeText={(text) => {
                setPassword(text);
                if (fieldErrors.password) {
                  setFieldErrors((prev) => ({ ...prev, password: undefined }));
                }
              }}
              error={fieldErrors.password}
              isPassword
              testID="password-input"
            />

            <View style={styles.forgotPasswordRow}>
              <TouchableOpacity
                onPress={() => navigation.navigate('ForgotPassword')}
                accessibilityRole="button"
                accessibilityLabel="Forgot Password"
                testID="forgot-password-link"
              >
                <Text style={styles.forgotPasswordText}>Forgot Password?</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.buttonWrapper}>
              <Button
                variant="primary"
                size="lg"
                loading={isLoading}
                disabled={isLoading}
                onPress={handleSubmit}
              >
                Sign In
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
    justifyContent: 'center',
    padding: spacing.s4,
  },
  header: {
    alignItems: 'center',
    marginBottom: spacing.s6,
  },
  logoBadge: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.s3,
  },
  logoText: {
    color: '#FFFFFF',
    fontSize: 22,
    fontWeight: '800',
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
  },
  card: {
    padding: spacing.s4,
  },
  fieldSpacing: {
    height: spacing.s3,
  },
  forgotPasswordRow: {
    alignItems: 'flex-end',
    marginTop: spacing.s2,
    marginBottom: spacing.s4,
  },
  forgotPasswordText: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.primary,
  },
  buttonWrapper: {
    marginTop: spacing.s1,
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
    lineHeight: 18,
  },
});
