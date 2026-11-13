import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, radius, spacing } from '../design/tokens';

export interface MobileQrDisplayProps {
  rollNumber: string;
  code: string;
  remainingSeconds: number;
}

export const QrDisplay: React.FC<MobileQrDisplayProps> = ({
  rollNumber,
  code,
  remainingSeconds,
}) => {
  const formattedCode =
    code.length === 6 ? `${code.slice(0, 3)} ${code.slice(3)}` : code;

  return (
    <View style={styles.card}>
      <Text style={styles.headerLabel}>STUDENT IDENTITY</Text>
      <Text style={styles.rollNumber}>{rollNumber}</Text>

      {/* Visual QR placeholder box */}
      <View style={styles.qrBox}>
        <View style={styles.cornerTL} />
        <View style={styles.cornerTR} />
        <View style={styles.cornerBL} />
        <View style={styles.cornerBR} />
        <Text style={styles.qrCenterText}>[DYNAMIC TOTP QR]</Text>
      </View>

      <View style={styles.codeRow}>
        <View>
          <Text style={styles.codeLabel}>VERIFICATION CODE</Text>
          <Text style={styles.codeText}>{formattedCode}</Text>
        </View>
        <View style={styles.countdownBadge}>
          <Text style={styles.countdownText}>{remainingSeconds}s</Text>
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.s4,
    alignItems: 'center',
    maxWidth: 320,
    alignSelf: 'center',
  },
  headerLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.textMuted,
    letterSpacing: 1,
  },
  rollNumber: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    marginTop: 2,
    marginBottom: spacing.s3,
    fontFamily: 'Inter',
  },
  qrBox: {
    width: 200,
    height: 200,
    borderWidth: 2,
    borderColor: colors.borderStrong,
    borderRadius: radius.card,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
    position: 'relative',
    marginBottom: spacing.s4,
  },
  cornerTL: {
    position: 'absolute',
    top: 10,
    left: 10,
    width: 24,
    height: 24,
    borderWidth: 4,
    borderColor: colors.text,
  },
  cornerTR: {
    position: 'absolute',
    top: 10,
    right: 10,
    width: 24,
    height: 24,
    borderWidth: 4,
    borderColor: colors.text,
  },
  cornerBL: {
    position: 'absolute',
    bottom: 10,
    left: 10,
    width: 24,
    height: 24,
    borderWidth: 4,
    borderColor: colors.text,
  },
  cornerBR: {
    position: 'absolute',
    bottom: 10,
    right: 10,
    width: 24,
    height: 24,
    borderWidth: 4,
    borderColor: colors.text,
  },
  qrCenterText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.textSecondary,
  },
  codeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
    paddingHorizontal: spacing.s2,
  },
  codeLabel: {
    fontSize: 11,
    color: colors.textMuted,
    fontWeight: '600',
  },
  codeText: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.text,
    letterSpacing: 1,
    fontFamily: 'Inter',
  },
  countdownBadge: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 2,
    borderColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  countdownText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.primary,
  },
});

