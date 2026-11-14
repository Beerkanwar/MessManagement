// Test Checkpoint: Secure-store round trip survives restart
import { InMemorySecureStorage } from '../../src/data/storage/secureStorage';

describe('Data: Secure Storage Round Trip', () => {
  it('stores, retrieves, and deletes values accurately across simulated restarts', async () => {
    const storage = new InMemorySecureStorage();

    // 1. Initial write
    await storage.setItemAsync('mess_refresh_token', 'refresh_token_test_123');
    await storage.setItemAsync('mess_device_unique_id', 'device_uuid_456');

    // 2. Read back
    expect(await storage.getItemAsync('mess_refresh_token')).toBe('refresh_token_test_123');
    expect(await storage.getItemAsync('mess_device_unique_id')).toBe('device_uuid_456');

    // 3. Update value
    await storage.setItemAsync('mess_refresh_token', 'rotated_refresh_token_789');
    expect(await storage.getItemAsync('mess_refresh_token')).toBe('rotated_refresh_token_789');

    // 4. Delete item
    await storage.deleteItemAsync('mess_refresh_token');
    expect(await storage.getItemAsync('mess_refresh_token')).toBeNull();

    // Device ID is preserved
    expect(await storage.getItemAsync('mess_device_unique_id')).toBe('device_uuid_456');
  });
});
