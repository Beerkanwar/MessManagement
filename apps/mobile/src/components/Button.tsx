import React from 'react';
import {
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  ViewStyle,
  TextStyle,
  Platform,
} from 'react-native';
import { colors, radius, touchTargets, spacing } from '../design/tokens';

export interface MobileButtonProps {
  onPress: () => void;
  children: string;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'md' | 'lg';
  loading?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
}

export const Button: React.FC<MobileButtonProps> = ({
  onPress,
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  style,
}) => {
  const minHeight =
    size === 'lg'
      ? touchTargets.scannerMin
      : Platform.OS === 'android'
      ? touchTargets.androidMin
      : touchTargets.iosMin;

  const bgStyle =
    variant === 'primary'
      ? { backgroundColor: colors.primary }
      : variant === 'secondary'
      ? { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }
      : variant === 'danger'
      ? { backgroundColor: colors.danger }
      : { backgroundColor: 'transparent' };

  const textColor =
    variant === 'primary' || variant === 'danger'
      ? '#FFFFFF'
      : colors.text;

  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={disabled || loading}
      activeOpacity={0.7}
      style={[
        styles.base,
        bgStyle,
        { minHeight },
        (disabled || loading) && styles.disabled,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={textColor} size="small" />
      ) : (
        <Text style={[styles.text, { color: textColor }]}>{children}</Text>
      )}
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.input,
    paddingHorizontal: spacing.s4,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  disabled: {
    opacity: 0.5,
  },
  text: {
    fontSize: 16,
    fontWeight: '600',
    fontFamily: 'Inter',
  },
});

