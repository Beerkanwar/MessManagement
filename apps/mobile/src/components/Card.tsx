import React from 'react';
import { View, Text, StyleSheet, ViewStyle } from 'react-native';
import { colors, radius, spacing } from '../design/tokens';

export interface MobileCardProps {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  style?: ViewStyle;
}

export const Card: React.FC<MobileCardProps> = ({ title, subtitle, children, style }) => {
  return (
    <View style={[styles.card, style]}>
      {(title || subtitle) && (
        <View style={styles.header}>
          {title && <Text style={styles.title}>{title}</Text>}
          {subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
        </View>
      )}
      <View style={styles.body}>{children}</View>
    </View>
  );
};

export interface MobileStatTileProps {
  label: string;
  value: string | number;
  change?: string;
  style?: ViewStyle;
}

export const StatTile: React.FC<MobileStatTileProps> = ({ label, value, change, style }) => {
  return (
    <View style={[styles.tile, style]}>
      <Text style={styles.tileLabel}>{label}</Text>
      <Text style={styles.tileValue}>{value}</Text>
      {change && <Text style={styles.tileChange}>{change}</Text>}
    </View>
  );
};

export interface MobileBannerProps {
  type: 'info' | 'warning' | 'danger';
  title?: string;
  message: string;
}

export const Banner: React.FC<MobileBannerProps> = ({ type, title, message }) => {
  const isDanger = type === 'danger';
  const isWarning = type === 'warning';

  const bg = isDanger ? colors.dangerSubtle : isWarning ? colors.warningSubtle : colors.infoSubtle;
  const borderColor = isDanger ? '#FECACA' : isWarning ? '#FDE68A' : '#BFDBFE';
  const textColor = isDanger ? '#991B1B' : isWarning ? '#92400E' : '#1E40AF';

  return (
    <View style={[styles.banner, { backgroundColor: bg, borderColor }]}>
      {title && <Text style={[styles.bannerTitle, { color: textColor }]}>{title}</Text>}
      <Text style={[styles.bannerMessage, { color: textColor }]}>{message}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.s3,
    overflow: 'hidden',
  },
  header: {
    paddingHorizontal: spacing.s4,
    paddingVertical: spacing.s3,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.text,
    fontFamily: 'Inter',
  },
  subtitle: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 2,
    fontFamily: 'Inter',
  },
  body: {
    padding: spacing.s4,
  },
  tile: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.s4,
    marginBottom: spacing.s3,
  },
  tileLabel: {
    fontSize: 12,
    color: colors.textSecondary,
    fontWeight: '500',
    fontFamily: 'Inter',
  },
  tileValue: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.text,
    marginVertical: 4,
    fontFamily: 'Inter',
  },
  tileChange: {
    fontSize: 11,
    color: colors.textMuted,
    fontFamily: 'Inter',
  },
  banner: {
    borderRadius: radius.input,
    borderWidth: 1,
    padding: spacing.s3,
    marginBottom: spacing.s3,
  },
  bannerTitle: {
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 2,
    fontFamily: 'Inter',
  },
  bannerMessage: {
    fontSize: 13,
    lineHeight: 18,
    fontFamily: 'Inter',
  },
});

