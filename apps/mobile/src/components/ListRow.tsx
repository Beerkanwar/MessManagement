import React from 'react';
import { TouchableOpacity, View, Text, StyleSheet } from 'react-native';
import { colors, spacing, touchTargets } from '../design/tokens';
import { StatusBadge } from './StatusBadge';

export interface MobileListRowProps {
  primaryText: string;
  secondaryText?: string;
  metadata?: string;
  status?: string;
  domain?: any;
  onPress?: () => void;
}

export const ListRow: React.FC<MobileListRowProps> = ({
  primaryText,
  secondaryText,
  metadata,
  status,
  domain,
  onPress,
}) => {
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={!onPress}
      activeOpacity={0.7}
      style={styles.row}
    >
      <View style={styles.left}>
        <Text style={styles.primary}>{primaryText}</Text>
        {secondaryText && <Text style={styles.secondary}>{secondaryText}</Text>}
        {metadata && <Text style={styles.meta}>{metadata}</Text>}
      </View>
      <View style={styles.right}>
        {status && <StatusBadge domain={domain} status={status} />}
        {onPress && <Text style={styles.chevron}>›</Text>}
      </View>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  row: {
    minHeight: touchTargets.androidMin,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.s3,
    paddingHorizontal: spacing.s4,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  left: {
    flex: 1,
    marginRight: spacing.s2,
  },
  primary: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.text,
    fontFamily: 'Inter',
  },
  secondary: {
    fontSize: 13,
    color: colors.textSecondary,
    marginTop: 2,
    fontFamily: 'Inter',
  },
  meta: {
    fontSize: 12,
    color: colors.textMuted,
    marginTop: 2,
    fontFamily: 'Inter',
  },
  right: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.s2,
  },
  chevron: {
    fontSize: 22,
    color: colors.textMuted,
    fontWeight: '300',
    marginLeft: spacing.s1,
  },
});

