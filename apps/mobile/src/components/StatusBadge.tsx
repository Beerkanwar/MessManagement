import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import {
  statusMapping,
  statusColorStyles,
  StatusColorType,
  spacing,
  radius,
} from '../design/tokens';

export type MobileStatusDomain = keyof typeof statusMapping;

export interface MobileStatusBadgeProps {
  domain?: MobileStatusDomain;
  status: string;
}

export const StatusBadge: React.FC<MobileStatusBadgeProps> = ({ domain, status }) => {
  let colorType: StatusColorType = 'neutral';

  if (domain && statusMapping[domain]) {
    const domainMap = statusMapping[domain] as Record<string, string>;
    if (domainMap[status]) {
      colorType = domainMap[status] as StatusColorType;
    }
  } else {
    for (const d of Object.values(statusMapping)) {
      const mapping = d as Record<string, string>;
      if (mapping[status]) {
        colorType = mapping[status] as StatusColorType;
        break;
      }
    }
  }

  const style = statusColorStyles[colorType] || statusColorStyles.neutral;

  const renderSymbol = () => {
    switch (colorType) {
      case 'success':
        return '✓';
      case 'warning':
        return '▲';
      case 'danger':
        return '✕';
      case 'info':
        return 'ℹ';
      case 'neutral':
      default:
        return '•';
    }
  };

  const formattedLabel = status.replace(/_/g, ' ');

  return (
    <View
      style={[
        styles.badge,
        {
          backgroundColor: style.bg,
          borderColor: style.border,
        },
      ]}
    >
      <Text style={[styles.symbol, { color: style.text }]}>{renderSymbol()}</Text>
      <Text style={[styles.text, { color: style.text }]}>{formattedLabel}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.s2,
    paddingVertical: 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  symbol: {
    fontSize: 11,
    fontWeight: '700',
    marginRight: 4,
  },
  text: {
    fontSize: 12,
    fontWeight: '600',
    fontFamily: 'Inter',
  },
});

