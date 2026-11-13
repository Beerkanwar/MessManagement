import React from 'react';
import { Text, TextStyle } from 'react-native';
import { colors } from '../design/tokens';

export interface MobileMoneyTextProps {
  amountInRupees: number;
  style?: TextStyle;
}

export const MoneyText: React.FC<MobileMoneyTextProps> = ({ amountInRupees, style }) => {
  const isNegative = amountInRupees < 0;
  const absAmount = Math.abs(amountInRupees);

  const formatted = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(absAmount);

  return (
    <Text
      style={[
        {
          fontFamily: 'Inter',
          color: isNegative ? colors.danger : colors.text,
          fontWeight: isNegative ? '700' : '600',
        },
        style,
      ]}
    >
      {isNegative && '-'}₹{formatted}
    </Text>
  );
};

