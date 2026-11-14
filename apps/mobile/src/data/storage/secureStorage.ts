// Secure Storage Interface and Adapters per SDD §6.1, SDD §7, Build Item 2
import * as SecureStore from 'expo-secure-store';

export interface ISecureStorage {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
}

export class ExpoSecureStorage implements ISecureStorage {
  private readonly options: SecureStore.SecureStoreOptions = {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  };

  public async getItemAsync(key: string): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(key, this.options);
    } catch {
      return null;
    }
  }

  public async setItemAsync(key: string, value: string): Promise<void> {
    await SecureStore.setItemAsync(key, value, this.options);
  }

  public async deleteItemAsync(key: string): Promise<void> {
    await SecureStore.deleteItemAsync(key, this.options);
  }
}

export class InMemorySecureStorage implements ISecureStorage {
  private store = new Map<string, string>();

  public async getItemAsync(key: string): Promise<string | null> {
    return this.store.get(key) ?? null;
  }

  public async setItemAsync(key: string, value: string): Promise<void> {
    this.store.set(key, value);
  }

  public async deleteItemAsync(key: string): Promise<void> {
    this.store.delete(key);
  }

  public clear(): void {
    this.store.clear();
  }
}

export const defaultSecureStorage: ISecureStorage = new ExpoSecureStorage();
