import React from 'react';
import { Text, TextStyle } from 'react-native';
import { colors } from '../design/tokens';

export interface MobileDateTextProps {
  date: string | Date;
  includeTime?: boolean;
  style?: TextStyle;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export const DateText: React.FC<MobileDateTextProps> = ({ date, includeTime = false, style }) => {
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) {
    return <Text style={style}>Invalid date</Text>;
  }

  // Format in IST
  const utc = d.getTime() + d.getTimezoneOffset() * 60000;
  const istOffsetMs = 5.5 * 3600000;
  const istDate = new Date(utc + istOffsetMs);

  const day = istDate.getDate();
  const month = MONTHS[istDate.getMonth()];
  const year = istDate.getFullYear();

  let formatted = `${day} ${month} ${year}`;
  if (includeTime) {
    let hours = istDate.getHours();
    const minutes = istDate.getMinutes().toString().padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12 || 12;
    formatted = `${day} ${month}, ${hours}:${minutes} ${ampm} (IST)`;
  }

  return (
    <Text style={[{ color: colors.text, fontFamily: 'Inter' }, style]}>
      {formatted}
    </Text>
  );
};

