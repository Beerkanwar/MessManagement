import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  TextInputProps,
} from 'react-native';
import { colors, radius, spacing, touchTargets } from '../design/tokens';

export interface MobileTextFieldProps extends TextInputProps {
  label?: string;
  helperText?: string;
  error?: string;
  isPassword?: boolean;
}

export const TextField: React.FC<MobileTextFieldProps> = ({
  label,
  helperText,
  error,
  isPassword = false,
  style,
  ...props
}) => {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <View style={styles.container}>
      {label && <Text style={styles.label}>{label}</Text>}
      <View
        style={[
          styles.inputContainer,
          error ? styles.inputError : styles.inputNormal,
        ]}
      >
        <TextInput
          placeholderTextColor={colors.textMuted}
          secureTextEntry={isPassword && !showPassword}
          style={[styles.input, style]}
          {...props}
        />
        {isPassword && (
          <TouchableOpacity
            onPress={() => setShowPassword(!showPassword)}
            style={styles.toggleBtn}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          >
            <Text style={styles.toggleText}>{showPassword ? 'Hide' : 'Show'}</Text>
          </TouchableOpacity>
        )}
      </View>
      {error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : helperText ? (
        <Text style={styles.helperText}>{helperText}</Text>
      ) : null}
    </View>
  );
};

export const PasswordField: React.FC<Omit<MobileTextFieldProps, 'isPassword'>> = (props) => (
  <TextField isPassword {...props} />
);

const styles = StyleSheet.create({
  container: {
    width: '100%',
    marginBottom: spacing.s3,
  },
  label: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.text,
    marginBottom: spacing.s1,
    fontFamily: 'Inter',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: touchTargets.androidMin,
    borderRadius: radius.input,
    borderWidth: 1,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.s3,
  },
  inputNormal: {
    borderColor: colors.border,
  },
  inputError: {
    borderColor: colors.danger,
  },
  input: {
    flex: 1,
    fontSize: 16,
    color: colors.text,
    fontFamily: 'Inter',
    paddingVertical: spacing.s2,
  },
  toggleBtn: {
    padding: spacing.s2,
  },
  toggleText: {
    fontSize: 13,
    color: colors.primary,
    fontWeight: '600',
    fontFamily: 'Inter',
  },
  errorText: {
    fontSize: 12,
    color: colors.danger,
    marginTop: spacing.s1,
    fontFamily: 'Inter',
  },
  helperText: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: spacing.s1,
    fontFamily: 'Inter',
  },
});

