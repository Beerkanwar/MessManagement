// Screen capture prevention wrapper per Build Item 10 / SDD §82
import * as ScreenCapture from 'expo-screen-capture';
import { logger } from './diagnostics';

let isPreventing = false;

export async function preventScreenCaptureAsync(): Promise<boolean> {
  try {
    if (typeof ScreenCapture.preventScreenCaptureAsync === 'function') {
      await ScreenCapture.preventScreenCaptureAsync();
      isPreventing = true;
      logger.info('ScreenCapture', 'Screen capture prevention enabled');
      return true;
    }
  } catch (err: any) {
    logger.warn('ScreenCapture', `Could not enable screen capture prevention: ${err?.message}`);
  }
  return false;
}

export async function allowScreenCaptureAsync(): Promise<boolean> {
  try {
    if (typeof ScreenCapture.allowScreenCaptureAsync === 'function') {
      await ScreenCapture.allowScreenCaptureAsync();
      isPreventing = false;
      logger.info('ScreenCapture', 'Screen capture prevention disabled');
      return true;
    }
  } catch (err: any) {
    logger.warn('ScreenCapture', `Could not disable screen capture prevention: ${err?.message}`);
  }
  return false;
}

export function isScreenCapturePrevented(): boolean {
  return isPreventing;
}
