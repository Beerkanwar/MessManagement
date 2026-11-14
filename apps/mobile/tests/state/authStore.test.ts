// Test Checkpoints: Session restoration, device replaced, web-role refusal, version policy
import { useAuthStore } from '../../src/state/authStore';
import { ApiClient } from '../../src/data/api/apiClient';
import { InMemorySecureStorage } from '../../src/data/storage/secureStorage';
import { AppError } from '../../src/domain/types';

describe('State: AuthStore Lifecycle & Checkpoints', () => {
  let storage: InMemorySecureStorage;
  let client: ApiClient;

  beforeEach(() => {
    storage = new InMemorySecureStorage();
    client = new ApiClient({
      baseUrl: 'http://test-server/api/v1',
      secureStorage: storage,
    });
    // Reset Zustand store state
    useAuthStore.setState({
      status: 'SIGNED_OUT',
      user: null,
      role: null,
      assignment: null,
      device: null,
      versionPolicy: null,
      isDeviceReplaced: false,
      isWebOnlyRole: false,
      isLoading: false,
      error: null,
    });
  });

  it('Checkpoint 1: Sign in, kill the app (simulate restart), reopen -> session restored', async () => {
    // 1. Mock Sign In API
    client.signIn = jest.fn().mockImplementation(async () => {
      client.setAccessToken('new_access_token');
      await storage.setItemAsync('mess_refresh_token', 'stored_refresh_token');
      return { access_token: 'new_access_token', refresh_token: 'stored_refresh_token' };
    });

    client.getMe = jest.fn().mockResolvedValue({
      user: { id: 1, email: 'student1@mess.edu', full_name: 'Test Student' },
      role: 'STUDENT',
      assignment: { roll_number: '21BCE1001', hostel_name: 'BH-1', mess_name: 'Central Mess' },
      device: { device_id: 'dev-123', platform: 'ANDROID' },
      version_policy: { status: 'SUPPORTED' },
    });

    // Sign In
    await useAuthStore.getState().signIn('student1@mess.edu', 'secret123', client);
    expect(useAuthStore.getState().status).toBe('SIGNED_IN');
    expect(useAuthStore.getState().user?.email).toBe('student1@mess.edu');
    expect(useAuthStore.getState().role).toBe('STUDENT');

    // 2. Simulate "kill app and reopen":
    // Access token in memory is wiped, store state is reset to RESTORING, but SecureStorage refresh token remains
    client.setAccessToken(null);
    useAuthStore.setState({ status: 'RESTORING', user: null, role: null });

    client.refreshSession = jest.fn().mockResolvedValue({
      access_token: 'restored_access_token',
      refresh_token: 'rotated_refresh_token',
    });

    // Reopen / restoreSession
    await useAuthStore.getState().restoreSession(client);

    expect(useAuthStore.getState().status).toBe('SIGNED_IN');
    expect(useAuthStore.getState().user?.email).toBe('student1@mess.edu');
    expect(useAuthStore.getState().role).toBe('STUDENT');
  });

  it('Checkpoint 2: Sign in on a second phone -> first phone shows device-replaced screen', async () => {
    await storage.setItemAsync('mess_refresh_token', 'old_phone_refresh_token');

    // Refresh throws DEVICE_REPLACED 401 error
    client.refreshSession = jest.fn().mockRejectedValue(
      new AppError('You signed in on another phone.', 'DEVICE_REPLACED', 401)
    );
    client.clearStoredTokens = jest.fn().mockImplementation(async () => {
      await storage.deleteItemAsync('mess_refresh_token');
    });

    await useAuthStore.getState().restoreSession(client);

    expect(useAuthStore.getState().status).toBe('SIGNED_OUT');
    expect(useAuthStore.getState().isDeviceReplaced).toBe(true);
    expect(await storage.getItemAsync('mess_refresh_token')).toBeNull();

    // User can clear the replaced state to re-sign in
    useAuthStore.getState().clearDeviceReplaced();
    expect(useAuthStore.getState().isDeviceReplaced).toBe(false);
  });

  it('Checkpoint 3: Web-role account (Hostel Clerk / Super Admin) is refused with web-role screen', async () => {
    client.signIn = jest.fn().mockRejectedValue(
      new AppError('Staff roles (Hostel Clerk, Super Admin) must sign in using the web application.', 'WRONG_CLIENT', 403)
    );

    await expect(useAuthStore.getState().signIn('clerk@hostel.edu', 'secret123', client)).rejects.toThrow();

    expect(useAuthStore.getState().status).toBe('SIGNED_OUT');
    expect(useAuthStore.getState().isWebOnlyRole).toBe(true);
  });

  it('Checkpoint 4: Stores BLOCKED and DEPRECATED version policies per DEC-18', async () => {
    await storage.setItemAsync('mess_refresh_token', 'valid_refresh');
    client.refreshSession = jest.fn().mockResolvedValue({ access_token: 'tok', refresh_token: 'tok' });

    client.getMe = jest.fn().mockResolvedValue({
      user: { id: 2, email: 'mgr@mess.edu', full_name: 'Mess Manager' },
      role: 'MESS_MANAGER',
      assignment: { mess_id: 1, mess_name: 'Central Mess' },
      device: { device_id: 'dev-456', platform: 'ANDROID' },
      version_policy: { status: 'DEPRECATED', force_update_message: 'Please upgrade to v2.0' },
    });

    await useAuthStore.getState().restoreSession(client);

    expect(useAuthStore.getState().status).toBe('SIGNED_IN');
    expect(useAuthStore.getState().versionPolicy?.status).toBe('DEPRECATED');
    expect(useAuthStore.getState().versionPolicy?.force_update_message).toBe('Please upgrade to v2.0');
  });

  it('sign out clears state and wipes tokens', async () => {
    useAuthStore.setState({
      status: 'SIGNED_IN',
      user: { id: 1, email: 'user@mess.edu', full_name: 'User' },
      role: 'STUDENT',
    });

    client.signOut = jest.fn().mockResolvedValue(undefined);

    await useAuthStore.getState().signOut(client);

    expect(useAuthStore.getState().status).toBe('SIGNED_OUT');
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().role).toBeNull();
  });
});
