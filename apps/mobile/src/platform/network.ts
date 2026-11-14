// Network Connectivity Monitor Platform Adapter per SDD §94
import NetInfo, { NetInfoState } from '@react-native-community/netinfo';

export interface NetworkStatus {
  isConnected: boolean;
  connectionType: string | null;
}

export type NetworkListener = (status: NetworkStatus) => void;

export interface INetworkMonitor {
  subscribe(listener: NetworkListener): () => void;
  checkConnection(): Promise<NetworkStatus>;
}

export class NetInfoNetworkMonitor implements INetworkMonitor {
  public subscribe(listener: NetworkListener): () => void {
    const unsubscribe = NetInfo.addEventListener((state: NetInfoState) => {
      listener({
        isConnected: Boolean(state.isConnected && state.isInternetReachable !== false),
        connectionType: state.type || null,
      });
    });
    return unsubscribe;
  }

  public async checkConnection(): Promise<NetworkStatus> {
    const state = await NetInfo.fetch();
    return {
      isConnected: Boolean(state.isConnected && state.isInternetReachable !== false),
      connectionType: state.type || null,
    };
  }
}

export const networkMonitor: INetworkMonitor = new NetInfoNetworkMonitor();
