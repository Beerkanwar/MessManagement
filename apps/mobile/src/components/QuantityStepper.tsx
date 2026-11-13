import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { colors, radius, spacing, touchTargets } from '../design/tokens';

export interface MobileQuantityStepperProps {
  label?: string;
  value: number;
  min?: number;
  max?: number;
  onChange: (val: number) => void;
  disabled?: boolean;
}

export const QuantityStepper: React.FC<MobileQuantityStepperProps> = ({
  label,
  value,
  min = 1,
  max = 99,
  onChange,
  disabled = false,
}) => {
  return (
    <View style={styles.container}>
      {label && <Text style={styles.label}>{label}</Text>}
      <View style={styles.stepperBox}>
        <TouchableOpacity
          onPress={() => value > min && onChange(value - 1)}
          disabled={disabled || value <= min}
          style={[styles.button, (disabled || value <= min) && styles.disabled]}
        >
          <Text style={styles.btnText}>-</Text>
        </TouchableOpacity>
        <Text style={styles.valueText}>{value}</Text>
        <TouchableOpacity
          onPress={() => value < max && onChange(value + 1)}
          disabled={disabled || value >= max}
          style={[styles.button, (disabled || value >= max) && styles.disabled]}
        >
          <Text style={styles.btnText}>+</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginBottom: spacing.s3,
  },
  label: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.text,
    marginBottom: spacing.s1,
    fontFamily: 'Inter',
  },
  stepperBox: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.input,
    backgroundColor: colors.surface,
    height: touchTargets.androidMin,
    alignSelf: 'flex-start',
  },
  button: {
    width: touchTargets.androidMin,
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  disabled: {
    opacity: 0.3,
  },
  btnText: {
    fontSize: 20,
    fontWeight: '600',
    color: colors.text,
  },
  valueText: {
    width: 44,
    textAlign: 'center',
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
    fontFamily: 'Inter',
  },
});

