import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Switch as RNSwitch,
  StyleSheet,
} from 'react-native';
import { colors, spacing } from '../design/tokens';

export interface MobileCheckboxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export const Checkbox: React.FC<MobileCheckboxProps> = ({
  label,
  checked,
  onChange,
  disabled = false,
}) => {
  return (
    <TouchableOpacity
      onPress={() => !disabled && onChange(!checked)}
      activeOpacity={0.7}
      disabled={disabled}
      style={styles.checkboxRow}
    >
      <View
        style={[
          styles.checkboxBox,
          checked && styles.checkboxChecked,
          disabled && styles.disabled,
        ]}
      >
        {checked && <Text style={styles.checkMark}>✓</Text>}
      </View>
      <Text style={[styles.label, disabled && styles.disabledText]}>{label}</Text>
    </TouchableOpacity>
  );
};

export interface MobileSwitchProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export const Switch: React.FC<MobileSwitchProps> = ({
  label,
  checked,
  onChange,
  disabled = false,
}) => {
  return (
    <View style={styles.switchRow}>
      <Text style={[styles.label, disabled && styles.disabledText]}>{label}</Text>
      <RNSwitch
        value={checked}
        onValueChange={onChange}
        disabled={disabled}
        trackColor={{ false: colors.borderStrong, true: colors.primary }}
        thumbColor="#FFFFFF"
      />
    </View>
  );
};

const styles = StyleSheet.create({
  checkboxRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.s3,
    minHeight: 44,
  },
  checkboxBox: {
    width: 22,
    height: 22,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: colors.borderStrong,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.s2,
  },
  checkboxChecked: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  checkMark: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
  switchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.s3,
    minHeight: 44,
  },
  label: {
    fontSize: 15,
    color: colors.text,
    fontFamily: 'Inter',
  },
  disabled: {
    opacity: 0.5,
  },
  disabledText: {
    color: colors.textMuted,
  },
});

