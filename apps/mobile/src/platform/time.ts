// Monotonic Time and Boot Identifier Platform Adapter per Spike S2, SDD §93

export interface IMonotonicClock {
  getMonotonicTimeMs(): number;
  getBootId(): string;
}

let simulatedBootId = `boot-${Date.now()}`;
const baselineTimestamp = Date.now();

export class SystemMonotonicClock implements IMonotonicClock {
  private bootId: string;

  constructor(bootId = simulatedBootId) {
    this.bootId = bootId;
  }

  public getMonotonicTimeMs(): number {
    if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
      return Math.round(performance.now());
    }
    return Date.now() - baselineTimestamp;
  }

  public getBootId(): string {
    return this.bootId;
  }

  public simulateReboot(newBootId?: string): void {
    this.bootId = newBootId || `boot-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`;
  }
}

export const defaultClock: IMonotonicClock = new SystemMonotonicClock();
