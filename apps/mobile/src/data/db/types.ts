// Database Interface for SQLite / SQLCipher per SDD §6.1, SDD §144, Build Item 3 & 11

export interface QueryResult {
  rows: any[];
  insertId?: number;
  rowsAffected: number;
}

export interface IDatabase {
  executeAsync(sql: string, params?: any[]): Promise<QueryResult>;
  executeBatchAsync(statements: Array<{ sql: string; params?: any[] }>): Promise<void>;
  transactionAsync<T>(fn: (tx: IDatabase) => Promise<T>): Promise<T>;
  closeAsync(): Promise<void>;
}

export class MockDatabase implements IDatabase {
  private inMemoryTables = new Map<string, any[]>();

  public async executeAsync(sql: string, params: any[] = []): Promise<QueryResult> {
    return { rows: [], rowsAffected: 0 };
  }

  public async executeBatchAsync(statements: Array<{ sql: string; params?: any[] }>): Promise<void> {
    for (const stmt of statements) {
      await this.executeAsync(stmt.sql, stmt.params);
    }
  }

  public async transactionAsync<T>(fn: (tx: IDatabase) => Promise<T>): Promise<T> {
    return await fn(this);
  }

  public async closeAsync(): Promise<void> {}
}
