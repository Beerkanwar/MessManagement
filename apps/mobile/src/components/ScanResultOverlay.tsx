import React from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
} from 'react-native';
import { scannerResults, spacing, radius } from '../design/tokens';

export type MobileScanResultType = keyof typeof scannerResults;

export interface MobileScanResultOverlayProps {
  visible: boolean;
  resultType: MobileScanResultType;
  studentName?: string;
  rollNumber?: string;
  mealType?: string;
  detailNote?: string;
  onDismiss: () => void;
}

export const ScanResultOverlay: React.FC<MobileScanResultOverlayProps> = ({
  visible,
  resultType,
  studentName,
  rollNumber,
  mealType,
  detailNote,
  onDismiss,
}) => {
  const config = scannerResults[resultType] || scannerResults.SUCCESS;

  const renderSymbol = () => {
    switch (resultType) {
      case 'SUCCESS':
      case 'SUCCESS_PAUSE_NOTICE':
        return '✓';
      case 'DUPLICATE':
        return '▲';
      case 'INVALID_CODE':
      case 'UNKNOWN_ROLL':
        return '✕';
      case 'TIME_INVALID':
      default:
        return '⏱';
    }
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onDismiss}>
      <TouchableOpacity
        activeOpacity={1}
        onPress={onDismiss}
        style={[styles.container, { backgroundColor: config.bg }]}
      >
        <View style={styles.centerBox}>
          {/* Symbol */}
          <Text style={styles.symbol}>{renderSymbol()}</Text>

          {/* Large Glanceable State Word */}
          <Text style={styles.stateTitle}>{config.label}</Text>

          {/* Student Info Card */}
          {(studentName || rollNumber) && (
            <View style={styles.infoCard}>
              {studentName && <Text style={styles.studentName}>{studentName}</Text>}
              {rollNumber && <Text style={styles.rollNumber}>{rollNumber}</Text>}
              {mealType && <Text style={styles.mealType}>{mealType}</Text>}
            </View>
          )}

          {detailNote && (
            <View style={styles.noteBadge}>
              <Text style={styles.noteText}>{detailNote}</Text>
            </View>
          )}

          <Text style={styles.dismissHint}>Tap anywhere or scan next student</Text>
        </View>
      </TouchableOpacity>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.s4,
  },
  centerBox: {
    alignItems: 'center',
    maxWidth: 380,
    width: '100%',
  },
  symbol: {
    fontSize: 72,
    color: '#FFFFFF',
    fontWeight: '900',
    marginBottom: spacing.s2,
  },
  stateTitle: {
    fontSize: 28,
    fontWeight: '900',
    color: '#FFFFFF',
    textAlign: 'center',
    letterSpacing: 1.5,
    marginBottom: spacing.s4,
    fontFamily: 'Inter',
  },
  infoCard: {
    backgroundColor: 'rgba(0, 0, 0, 0.2)',
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.3)',
    padding: spacing.s4,
    width: '100%',
    alignItems: 'center',
    marginBottom: spacing.s3,
  },
  studentName: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFFFFF',
    fontFamily: 'Inter',
  },
  rollNumber: {
    fontSize: 18,
    fontWeight: '600',
    color: '#FFFFFF',
    opacity: 0.9,
    marginTop: 4,
    fontFamily: 'Inter',
  },
  mealType: {
    fontSize: 13,
    fontWeight: '600',
    color: '#FFFFFF',
    opacity: 0.8,
    textTransform: 'uppercase',
    marginTop: 4,
    letterSpacing: 1,
    fontFamily: 'Inter',
  },
  noteBadge: {
    backgroundColor: 'rgba(0, 0, 0, 0.25)',
    paddingHorizontal: spacing.s3,
    paddingVertical: spacing.s2,
    borderRadius: radius.pill,
    marginBottom: spacing.s4,
  },
  noteText: {
    fontSize: 13,
    color: '#FFFFFF',
    fontWeight: '600',
    fontFamily: 'Inter',
  },
  dismissHint: {
    fontSize: 13,
    color: '#FFFFFF',
    opacity: 0.7,
    marginTop: spacing.s4,
    fontFamily: 'Inter',
  },
});

