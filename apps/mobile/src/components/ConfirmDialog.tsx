import React, { useState } from 'react';
import {
  Modal,
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableWithoutFeedback,
} from 'react-native';
import { colors, radius, spacing } from '../design/tokens';
import { Button } from './Button';

export interface MobileConfirmDialogProps {
  visible: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'primary' | 'danger';
}

export const ConfirmDialog: React.FC<MobileConfirmDialogProps> = ({
  visible,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'primary',
}) => {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <TouchableWithoutFeedback onPress={onClose}>
        <View style={styles.backdrop} />
      </TouchableWithoutFeedback>
      <View style={styles.dialogContainer}>
        <View style={styles.dialog}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.desc}>{description}</Text>
          <View style={styles.actions}>
            <Button variant="secondary" onPress={onClose} style={styles.btn}>
              {cancelLabel}
            </Button>
            <Button
              variant={variant === 'danger' ? 'danger' : 'primary'}
              onPress={onConfirm}
              style={styles.btn}
            >
              {confirmLabel}
            </Button>
          </View>
        </View>
      </View>
    </Modal>
  );
};

export interface MobileReasonDialogProps {
  visible: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
  title: string;
  description: string;
  minLength?: number;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'primary' | 'danger';
}

export const ReasonDialog: React.FC<MobileReasonDialogProps> = ({
  visible,
  onClose,
  onConfirm,
  title,
  description,
  minLength = 10,
  confirmLabel = 'Submit',
  cancelLabel = 'Cancel',
  variant = 'primary',
}) => {
  const [reason, setReason] = useState('');
  const trimmed = reason.trim();
  const isValid = trimmed.length >= minLength;

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <TouchableWithoutFeedback onPress={onClose}>
        <View style={styles.backdrop} />
      </TouchableWithoutFeedback>
      <View style={styles.dialogContainer}>
        <View style={styles.dialog}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.desc}>{description}</Text>
          <TextInput
            multiline
            numberOfLines={3}
            placeholder="Mandatory audited reason..."
            placeholderTextColor={colors.textMuted}
            value={reason}
            onChangeText={setReason}
            style={styles.textArea}
          />
          <Text style={styles.counterText}>
            {trimmed.length} / {minLength} characters min
          </Text>
          <View style={styles.actions}>
            <Button variant="secondary" onPress={onClose} style={styles.btn}>
              {cancelLabel}
            </Button>
            <Button
              variant={variant === 'danger' ? 'danger' : 'primary'}
              onPress={() => isValid && onConfirm(trimmed)}
              disabled={!isValid}
              style={styles.btn}
            >
              {confirmLabel}
            </Button>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(15, 23, 42, 0.4)',
  },
  dialogContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.s4,
  },
  dialog: {
    width: '100%',
    maxWidth: 400,
    backgroundColor: colors.surface,
    borderRadius: radius.dialog,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.s4,
    elevation: 4,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    fontFamily: 'Inter',
  },
  desc: {
    fontSize: 14,
    color: colors.textSecondary,
    marginVertical: spacing.s2,
    fontFamily: 'Inter',
  },
  textArea: {
    minHeight: 80,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.input,
    padding: spacing.s3,
    fontSize: 14,
    color: colors.text,
    fontFamily: 'Inter',
    textAlignVertical: 'top',
  },
  counterText: {
    fontSize: 11,
    color: colors.textMuted,
    textAlign: 'right',
    marginTop: 4,
    marginBottom: spacing.s3,
  },
  actions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: spacing.s2,
    marginTop: spacing.s2,
  },
  btn: {
    minWidth: 100,
  },
});

