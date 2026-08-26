# Test Data Factory Pattern for D1 in Workers Tests

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Every test file defines its own `INSERT` statements with hard-coded values. When the schema changes, dozens of files break. Related entities (user → order → line item) are created by hand, leading to missing foreign keys or wrong IDs. A factory pattern centralises data creation, applies sensible defaults, and handles cleanup automatically.

## Context

D1 in Miniflare (`@cloudflare/vitest-pool-workers`) is a real SQLite database reset between test suites. Factories use the D1 binding directly, return typed objects, and register created rows in a cleanup registry that the `afterEach` hook can drain. Seed scripts reuse the same factories against a real D1 namespace for staging.

---

## Solution

### 1. Schema

```sql
-- migrations/0001_init.sql
CREATE TABLE IF NOT EXISTS users (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  email      TEXT    NOT NULL UNIQUE,
  role       TEXT    NOT NULL DEFAULT 'member',
  createdAt  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  userId     INTEGER NOT NULL REFERENCES users(id),
  status     TEXT    NOT NULL DEFAULT 'pending',
  totalCents INTEGER NOT NULL DEFAULT 0,
  createdAt  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS line_items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  orderId    INTEGER NOT NULL REFERENCES orders(id),
  sku        TEXT    NOT NULL,
  quantity   INTEGER NOT NULL DEFAULT 1,
  unitCents  INTEGER NOT NULL
);
```

### 2. Typed factory functions with defaults

```typescript
// test/factories/types.ts
export interface UserRow {
  id: number;
  name: string;
  email: string;
  role: string;
  createdAt: string;
}

export interface OrderRow {
  id: number;
  userId: number;
  status: string;
  totalCents: number;
  createdAt: string;
}

export interface LineItemRow {
  id: number;
  orderId: number;
  sku: string;
  quantity: number;
  unitCents: number;
}
```

```typescript
// test/factories/userFactory.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { UserRow } from './types';

let seq = 0;
const nextSeq = () => ++seq;

export type UserOverrides = Partial<Omit<UserRow, 'id' | 'createdAt'>>;

export async function createUser(
  db: D1Database,
  overrides: UserOverrides = {},
): Promise<UserRow> {
  const n = nextSeq();
  const name  = overrides.name  ?? `Test User ${n}`;
  const email = overrides.email ?? `user${n}@example.com`;
  const role  = overrides.role  ?? 'member';

  const result = await db
    .prepare(
      `INSERT INTO users (name, email, role)
       VALUES (?, ?, ?)
       RETURNING *`,
    )
    .bind(name, email, role)
    .first<UserRow>();

  if (!result) throw new Error('createUser: INSERT returned no row');
  return result;
}
```

### 3. Related entity factories

```typescript
// test/factories/orderFactory.ts
import type { D1Database } from '@cloudflare/workers-types';
import type { OrderRow, LineItemRow } from './types';

export type OrderOverrides = Partial<Omit<OrderRow, 'id' | 'createdAt'>>;
export type LineItemOverrides = Partial<Omit<LineItemRow, 'id' | 'orderId'>>;

export async function createOrder(
  db: D1Database,
  userId: number,
  overrides: OrderOverrides = {},
): Promise<OrderRow> {
  const status     = overrides.status     ?? 'pending';
  const totalCents = overrides.totalCents ?? 0;

  const result = await db
    .prepare(
      `INSERT INTO orders (userId, status, totalCents)
       VALUES (?, ?, ?)
       RETURNING *`,
    )
    .bind(userId, status, totalCents)
    .first<OrderRow>();

  if (!result) throw new Error('createOrder: INSERT returned no row');
  return result;
}

export async function createLineItem(
  db: D1Database,
  orderId: number,
  overrides: LineItemOverrides = {},
): Promise<LineItemRow> {
  const sku       = overrides.sku       ?? 'SKU-0000';
  const quantity  = overrides.quantity  ?? 1;
  const unitCents = overrides.unitCents ?? 100;

  const result = await db
    .prepare(
      `INSERT INTO line_items (orderId, sku, quantity, unitCents)
       VALUES (?, ?, ?, ?)
       RETURNING *`,
    )
    .bind(orderId, sku, quantity, unitCents)
    .first<LineItemRow>();

  if (!result) throw new Error('createLineItem: INSERT returned no row');
  return result;
}
```

### 4. Batch creation

```typescript
// test/factories/batch.ts
import type { D1Database } from '@cloudflare/workers-types';
import { createUser, type UserOverrides } from './userFactory';
import { createOrder, createLineItem, type OrderOverrides, type LineItemOverrides } from './orderFactory';
import type { UserRow, OrderRow, LineItemRow } from './types';

export interface FullOrder {
  user: UserRow;
  order: OrderRow;
  lineItems: LineItemRow[];
}

/**
 * Creates N orders for a single user, each with M line items.
 * Useful for pagination and aggregation tests.
 */
export async function createOrderBatch(
  db: D1Database,
  opts: {
    userOverrides?: UserOverrides;
    orderCount?: number;
    itemsPerOrder?: number;
    orderOverrides?: OrderOverrides;
    itemOverrides?: LineItemOverrides;
  } = {},
): Promise<FullOrder[]> {
  const { orderCount = 3, itemsPerOrder = 2 } = opts;
  const user = await createUser(db, opts.userOverrides);

  const results: FullOrder[] = [];
  for (let i = 0; i < orderCount; i++) {
    const order = await createOrder(db, user.id, opts.orderOverrides);
    const lineItems: LineItemRow[] = [];
    for (let j = 0; j < itemsPerOrder; j++) {
      lineItems.push(await createLineItem(db, order.id, opts.itemOverrides));
    }
    results.push({ user, order, lineItems });
  }
  return results;
}
```

### 5. Cleanup registry

```typescript
// test/factories/registry.ts
import type { D1Database } from '@cloudflare/workers-types';

type TableName = 'line_items' | 'orders' | 'users';

interface CleanupEntry {
  table: TableName;
  id: number;
}

/**
 * Tracks created rows so afterEach can delete them in reverse-insertion order,
 * respecting foreign key constraints.
 */
export class CleanupRegistry {
  private entries: CleanupEntry[] = [];

  track(table: TableName, id: number): void {
    this.entries.push({ table, id });
  }

  async flush(db: D1Database): Promise<void> {
    // Delete in LIFO order to satisfy FK constraints
    const reversed = [...this.entries].reverse();
    const stmts = reversed.map(({ table, id }) =>
      db.prepare(`DELETE FROM ${table} WHERE id = ?`).bind(id),
    );
    if (stmts.length > 0) await db.batch(stmts);
    this.entries = [];
  }
}
```

```typescript
// test/orders.test.ts — using factories + registry together
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { env } from 'cloudflare:test';
import { SELF } from 'cloudflare:test';
import { createUser } from './factories/userFactory';
import { createOrder, createLineItem } from './factories/orderFactory';
import { CleanupRegistry } from './factories/registry';

let registry: CleanupRegistry;

beforeEach(() => { registry = new CleanupRegistry(); });
afterEach(() => registry.flush(env.DB));

describe('GET /orders/:id', () => {
  it('returns order with line items', async () => {
    const user  = await createUser(env.DB);
    registry.track('users', user.id);

    const order = await createOrder(env.DB, user.id, { status: 'paid', totalCents: 2000 });
    registry.track('orders', order.id);

    const item  = await createLineItem(env.DB, order.id, { sku: 'WGT-001', quantity: 2, unitCents: 1000 });
    registry.track('line_items', item.id);

    const res  = await SELF.fetch(`http://localhost/orders/${order.id}`);
    const body = await res.json<{ id: number; lineItems: unknown[] }>();

    expect(res.status).toBe(200);
    expect(body.id).toBe(order.id);
    expect(body.lineItems).toHaveLength(1);
  });
});
```

### 6. Seed scripts for staging environments

```typescript
// scripts/seed.ts  — run with: npx wrangler --env staging d1 execute DB --file=- < <(tsx scripts/seed.ts)
import { createUser } from '../test/factories/userFactory';
import { createOrder, createLineItem } from '../test/factories/orderFactory';

// When running against a real D1 via wrangler, inject the binding via the REST API.
// This script prints SQL instead so it can be piped to wrangler d1 execute.
const rows = [
  { user: { name: 'Alice Admin', email: 'alice@example.com', role: 'admin' } },
  { user: { name: 'Bob Member', email: 'bob@example.com', role: 'member' } },
];

for (const { user } of rows) {
  console.log(`INSERT INTO users (name, email, role) VALUES ('${user.name}', '${user.email}', '${user.role}');`);
}
```

For a programmatic seed (Miniflare or local D1):

```typescript
// scripts/seedLocal.ts
import { getPlatformProxy } from 'wrangler';
import { createUser } from '../test/factories/userFactory';
import { createOrderBatch } from '../test/factories/batch';

async function main() {
  const { env, dispose } = await getPlatformProxy<{ DB: D1Database }>();
  try {
    const batch = await createOrderBatch(env.DB, { orderCount: 5, itemsPerOrder: 3 });
    console.log(`Seeded ${batch.length} orders for user ${batch[0].user.email}`);
  } finally {
    await dispose();
  }
}
main();
```

---

## Implementation Details

- `RETURNING *` (SQLite 3.35+, available in D1) lets factories return the full row including the auto-generated `id` and `createdAt` in one round-trip.
- The `seq` counter in `userFactory` is module-level; Vitest resets it between test files because each file runs in its own module scope.
- `CleanupRegistry.flush` uses `db.batch` for a single D1 round-trip regardless of how many rows were created.
- For heavy fixture sets (>50 rows), prefer truncating the tables in `beforeEach` instead of tracking individual rows.

---

## Anti-patterns

- **Hard-coding IDs** — auto-increment IDs are unpredictable; always use the returned row's `id`.
- **Skipping cleanup** — leftover rows pollute subsequent tests when schemas share unique constraints.
- **Factory functions that hit the network** — factories should only touch the D1 binding; HTTP calls belong in the test itself.
- **Deeply nested factory calls without tracking** — register every created row immediately after creation, not at the end of the test.

---

## Gotchas

- `RETURNING *` returns columns in schema definition order, not insertion order; access fields by name, not position.
- D1's `batch` method executes statements in a single transaction; if one fails all roll back — useful for cleanup but avoid mixing factory inserts with cleanup in one batch call.
- `getPlatformProxy` in seed scripts requires `wrangler.toml` to be present in the working directory.

---

## Verification

```bash
# Run the factory-dependent tests
npx vitest run test/orders.test.ts --reporter=verbose

# Seed local dev D1
npx tsx scripts/seedLocal.ts
```

---

## Related

- `documentation/categories/testing/workers-vitest-d1-fixtures.md`
- `documentation/categories/testing/integration-test-d1-fixtures.md`
- `documentation/categories/testing/workers-snapshot-testing-api-responses.md`

---

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://www.sqlite.org/lang_returning.html
