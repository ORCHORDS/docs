# Branch by Abstraction Pattern for Cloudflare Workers Refactoring

2026-08-24 / example.com / production

---

## Symptom / Use-case

You need to replace a foundational module inside a deployed Worker—a storage layer, an auth provider, an external API client—without a big-bang rewrite, long-lived feature branches, or downtime. The existing code is spread across many files and is not behind any abstraction boundary, making it dangerous to change.

Indicators you need this pattern:
- The module you want to replace is called directly in dozens of places.
- The replacement module uses a different interface than the current one.
- You want to ship incremental commits to `main` throughout the migration, not merge a multi-week branch.
- You want the ability to run the new implementation in parallel with the old one for a period of time and compare outputs before switching over.

---

## Context

Branch by abstraction (BBA) is a technique introduced by Paul Hammant that lets you refactor a large, entangled system in continuous small steps on a single branch. The core mechanic is:

1. Introduce an abstraction (interface) over the module you intend to replace.
2. Make the existing implementation satisfy that abstraction.
3. Build the new implementation against the same abstraction.
4. Add a toggle (KV or env var) that selects which implementation is active.
5. Progressively migrate call sites to use the abstraction instead of the concrete type.
6. Once the new implementation is validated, remove the toggle and the old implementation.

On the Cloudflare Workers stack, the abstraction is a TypeScript interface, the toggle is a KV value or an environment variable, and the parallel-run validation uses the Tee pattern (`request.clone()`) to compare both implementations' outputs.

---

## Code sections

### 1. Define the abstraction interface

```typescript
// lib/storage/storage-provider.ts

/**
 * Abstraction over the storage layer.
 * Both the legacy D1 implementation and the new KV+D1 hybrid must satisfy this.
 */
export interface StorageProvider {
  getUser(id: string): Promise<User | null>;
  upsertUser(user: User): Promise<void>;
  deleteUser(id: string): Promise<void>;
  listUsersByTenant(tenantId: string, limit: number, cursor?: string): Promise<UserPage>;
}

export interface User {
  id: string;
  tenantId: string;
  email: string;
  role: 'admin' | 'member' | 'viewer';
  createdAt: string;
  updatedAt: string;
}

export interface UserPage {
  items: User[];
  nextCursor: string | null;
}
```

### 2. Wrap the existing implementation behind the abstraction (step 2)

```typescript
// lib/storage/d1-storage-provider.ts
import type { StorageProvider, User, UserPage } from './storage-provider';

/** Legacy implementation – untouched logic, just now behind the interface. */
export class D1StorageProvider implements StorageProvider {
  constructor(private db: D1Database) {}

  async getUser(id: string): Promise<User | null> {
    const row = await this.db
      .prepare('SELECT * FROM users WHERE id = ?')
      .bind(id)
      .first<Record<string, unknown>>();

    return row ? rowToUser(row) : null;
  }

  async upsertUser(user: User): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO users (id, tenant_id, email, role, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT (id) DO UPDATE SET
           email = excluded.email, role = excluded.role, updated_at = excluded.updated_at`
      )
      .bind(user.id, user.tenantId, user.email, user.role, user.createdAt, user.updatedAt)
      .run();
  }

  async deleteUser(id: string): Promise<void> {
    await this.db.prepare('DELETE FROM users WHERE id = ?').bind(id).run();
  }

  async listUsersByTenant(tenantId: string, limit: number, cursor?: string): Promise<UserPage> {
    const rows = await this.db
      .prepare(
        `SELECT * FROM users
         WHERE tenant_id = ? AND id > ?
         ORDER BY id LIMIT ?`
      )
      .bind(tenantId, cursor ?? '', limit)
      .all<Record<string, unknown>>();

    const items = rows.results.map(rowToUser);
    const nextCursor = items.length === limit ? items[items.length - 1].id : null;
    return { items, nextCursor };
  }
}

function rowToUser(r: Record<string, unknown>): User {
  return {
    id: r.id as string,
    tenantId: r.tenant_id as string,
    email: r.email as string,
    role: r.role as User['role'],
    createdAt: r.created_at as string,
    updatedAt: r.updated_at as string,
  };
}
```

### 3. Build the new implementation (step 3)

```typescript
// lib/storage/kv-d1-storage-provider.ts
import type { StorageProvider, User, UserPage } from './storage-provider';

/**
 * New implementation: KV read-through cache backed by D1.
 * Satisfies the same StorageProvider interface.
 */
export class KvD1StorageProvider implements StorageProvider {
  private readonly TTL_SECONDS = 300;

  constructor(
    private db: D1Database,
    private kv: KVNamespace
  ) {}

  async getUser(id: string): Promise<User | null> {
    const cached = await this.kv.get<User>(`user:${id}`, { type: 'json' });
    if (cached) return cached;

    const row = await this.db
      .prepare('SELECT * FROM users WHERE id = ?')
      .bind(id)
      .first<Record<string, unknown>>();

    if (!row) return null;

    const user: User = {
      id: row.id as string,
      tenantId: row.tenant_id as string,
      email: row.email as string,
      role: row.role as User['role'],
      createdAt: row.created_at as string,
      updatedAt: row.updated_at as string,
    };

    await this.kv.put(`user:${id}`, JSON.stringify(user), { expirationTtl: this.TTL_SECONDS });
    return user;
  }

  async upsertUser(user: User): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO users (id, tenant_id, email, role, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT (id) DO UPDATE SET
           email = excluded.email, role = excluded.role, updated_at = excluded.updated_at`
      )
      .bind(user.id, user.tenantId, user.email, user.role, user.createdAt, user.updatedAt)
      .run();

    // Invalidate cache on write
    await this.kv.delete(`user:${user.id}`);
  }

  async deleteUser(id: string): Promise<void> {
    await this.db.prepare('DELETE FROM users WHERE id = ?').bind(id).run();
    await this.kv.delete(`user:${id}`);
  }

  async listUsersByTenant(tenantId: string, limit: number, cursor?: string): Promise<UserPage> {
    const rows = await this.db
      .prepare(
        `SELECT * FROM users WHERE tenant_id = ? AND id > ? ORDER BY id LIMIT ?`
      )
      .bind(tenantId, cursor ?? '', limit)
      .all<Record<string, unknown>>();

    const items = rows.results.map((r) => ({
      id: r.id as string,
      tenantId: r.tenant_id as string,
      email: r.email as string,
      role: r.role as User['role'],
      createdAt: r.created_at as string,
      updatedAt: r.updated_at as string,
    }));
    return { items, nextCursor: items.length === limit ? items[items.length - 1].id : null };
  }
}
```

### 4. Provider factory – toggle selects implementation (step 4)

```typescript
// lib/storage/create-storage-provider.ts
import type { StorageProvider } from './storage-provider';
import { D1StorageProvider } from './d1-storage-provider';
import { KvD1StorageProvider } from './kv-d1-storage-provider';

export type StorageImpl = 'legacy-d1' | 'kv-d1';

interface ProviderEnv {
  DB: D1Database;
  USER_CACHE: KVNamespace;
  STORAGE_IMPL?: string; // env var for wrangler.toml override
}

/**
 * Read the active implementation from KV (runtime toggle) or fall back
 * to the STORAGE_IMPL env var (deploy-time default).
 */
export async function createStorageProvider(
  env: ProviderEnv,
  configKv: KVNamespace
): Promise<StorageProvider> {
  const runtimeImpl = await configKv.get('feature:storage-impl');
  const impl = (runtimeImpl ?? env.STORAGE_IMPL ?? 'legacy-d1') as StorageImpl;

  switch (impl) {
    case 'kv-d1':
      return new KvD1StorageProvider(env.DB, env.USER_CACHE);
    case 'legacy-d1':
    default:
      return new D1StorageProvider(env.DB);
  }
}
```

### 5. Shadow-mode comparison – parallel run before full cutover

```typescript
// lib/storage/shadow-storage-provider.ts
import type { StorageProvider, User, UserPage } from './storage-provider';

/**
 * Runs both implementations in parallel.
 * Returns the result from `primary` but logs divergences from `shadow`.
 * Use during the migration window to gain confidence in the new implementation.
 */
export class ShadowStorageProvider implements StorageProvider {
  constructor(
    private primary: StorageProvider,
    private shadow: StorageProvider,
    private ctx: ExecutionContext
  ) {}

  async getUser(id: string): Promise<User | null> {
    const [primaryResult, shadowResult] = await Promise.allSettled([
      this.primary.getUser(id),
      this.shadow.getUser(id),
    ]);

    if (shadowResult.status === 'rejected') {
      console.error('shadow.getUser failed', { id, err: shadowResult.reason });
    } else if (primaryResult.status === 'fulfilled') {
      this.ctx.waitUntil(
        compareAndLog('getUser', primaryResult.value, shadowResult.value, { id })
      );
    }

    if (primaryResult.status === 'rejected') throw primaryResult.reason;
    return primaryResult.value;
  }

  async upsertUser(user: User): Promise<void> {
    const [primaryResult, shadowResult] = await Promise.allSettled([
      this.primary.upsertUser(user),
      this.shadow.upsertUser(user),
    ]);
    if (shadowResult.status === 'rejected') {
      console.error('shadow.upsertUser failed', { id: user.id, err: shadowResult.reason });
    }
    if (primaryResult.status === 'rejected') throw primaryResult.reason;
  }

  async deleteUser(id: string): Promise<void> {
    const [p, s] = await Promise.allSettled([
      this.primary.deleteUser(id),
      this.shadow.deleteUser(id),
    ]);
    if (s.status === 'rejected') console.error('shadow.deleteUser failed', { id, err: s.reason });
    if (p.status === 'rejected') throw p.reason;
  }

  async listUsersByTenant(tenantId: string, limit: number, cursor?: string): Promise<UserPage> {
    const [p, s] = await Promise.allSettled([
      this.primary.listUsersByTenant(tenantId, limit, cursor),
      this.shadow.listUsersByTenant(tenantId, limit, cursor),
    ]);
    if (s.status === 'rejected') console.error('shadow.listUsersByTenant failed', s.reason);
    if (p.status === 'rejected') throw p.reason;
    return p.value;
  }
}

async function compareAndLog(
  method: string,
  primary: unknown,
  shadow: unknown,
  ctx: Record<string, string>
): Promise<void> {
  const pStr = JSON.stringify(primary);
  const sStr = JSON.stringify(shadow);
  if (pStr !== sStr) {
    console.warn('shadow divergence', { method, ...ctx, primary: pStr, shadow: sStr });
  }
}
```

### 6. Main Worker – consuming the abstraction at call sites

```typescript
// workers/users-api/src/index.ts
import { createStorageProvider } from '../../../lib/storage/create-storage-provider';
import { ShadowStorageProvider } from '../../../lib/storage/shadow-storage-provider';
import { KvD1StorageProvider } from '../../../lib/storage/kv-d1-storage-provider';
import { D1StorageProvider } from '../../../lib/storage/d1-storage-provider';

interface Env {
  DB: D1Database;
  USER_CACHE: KVNamespace;
  FEATURE_FLAGS: KVNamespace;
  STORAGE_IMPL?: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const shadowMode = (await env.FEATURE_FLAGS.get('feature:storage-shadow')) === 'true';

    let storage = await createStorageProvider(env, env.FEATURE_FLAGS);

    if (shadowMode) {
      const legacy = new D1StorageProvider(env.DB);
      const next = new KvD1StorageProvider(env.DB, env.USER_CACHE);
      storage = new ShadowStorageProvider(legacy, next, ctx);
    }

    const url = new URL(request.url);
    const userId = url.pathname.split('/').pop() ?? '';

    if (request.method === 'GET' && url.pathname.startsWith('/users/')) {
      const user = await storage.getUser(userId);
      if (!user) return new Response('Not Found', { status: 404 });
      return Response.json(user);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Anti-patterns

- **Skipping the abstraction and using an `if` flag directly at every call site.** This scatters the decision logic and makes the old code hard to delete cleanly. The abstraction boundary is what enables safe removal.
- **Doing the flag check at module scope (outside `fetch`).** Module scope is frozen after first load; KV reads must happen inside the request or alarm handler.
- **Leaving shadow mode on indefinitely.** Shadow mode doubles the write load and can cause divergence noise in logs. Set a calendar reminder to remove it once validation is complete.
- **Introducing the abstraction and migrating all call sites in one PR.** Split these across at least two commits: first the abstraction + old implementation, then the new implementation, then the call-site migration.
- **Using `any` in the abstraction interface.** Typed return values are what make it safe to swap implementations—the compiler enforces contract compliance.

---

## Gotchas

- **KV toggle propagation lag (~60 s).** When switching from `legacy-d1` to `kv-d1` via KV, some edge nodes will still serve the old implementation for up to 60 seconds.
- **Shadow writes mutate both stores.** In shadow mode, `upsertUser` and `deleteUser` write to both D1 and KV. Ensure your shadow D1 and production D1 are not the same binding if you want a clean experiment.
- **`Promise.allSettled` in shadow mode.** Do NOT use `Promise.all` in the shadow provider—a shadow failure should never propagate as a user-visible error.
- **Module-scope caching of the provider.** Do not cache the `StorageProvider` instance in module scope across requests; the KV flag value must be re-read so runtime config changes take effect.

---

## Verification

```bash
# Step 1: deploy with legacy implementation active
wrangler secret put STORAGE_IMPL   # set to "legacy-d1"
wrangler deploy

# Step 2: enable shadow mode via KV
wrangler kv:key put feature:storage-shadow "true" --binding FEATURE_FLAGS

# Step 3: watch for divergence logs
wrangler tail users-api --format pretty | grep "shadow divergence"

# Step 4: once satisfied, switch primary to new implementation
wrangler kv:key put feature:storage-impl "kv-d1" --binding FEATURE_FLAGS

# Step 5: disable shadow mode
wrangler kv:key put feature:storage-shadow "false" --binding FEATURE_FLAGS

# Step 6: after full validation, remove toggle and old implementation in code
wrangler kv:key delete feature:storage-impl --binding FEATURE_FLAGS
```

---

## Related

- `strangler-fig-workers-migration.md`
- `strategy-pattern-workers-kv.md`
- `feature-flags-implementations.md`
- `canary-release-routing-workers-kv.md`
- `proxy-pattern-workers-service-binding-auth.md`

---

## Sources

- Paul Hammant – Branch by Abstraction – https://paulhammant.com/blog/branch_by_abstraction.html
- Martin Fowler – Branch by Abstraction – https://martinfowler.com/bliki/BranchByAbstraction.html
- Cloudflare KV documentation – https://developers.cloudflare.com/kv/
- TypeScript Handbook – Interfaces – https://www.typescriptlang.org/docs/handbook/interfaces.html
