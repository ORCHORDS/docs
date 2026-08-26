# feature-cookbook-config

**Issue:** App configuration — env vars, secrets, runtime config
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a feature. The marketing team wants to enable
it for a specific cohort. The dev team has to redeploy.
The marketing team is blocked. You wish the config was
runtime-controllable.

## Root cause
**Config is often baked into the code.** For features
that need to change often, runtime config is the answer.

**Source:** Various config guides.

## The "config types" choice

Three types:
1. **Build-time:** Baked into the code at build
2. **Env vars:** Set per environment, not runtime
3. **Runtime config:** Set per environment, changeable
   without deploy

For most things, use env vars. For things that change
often (feature flags, A/B tests, business config), use
runtime config.

## The "env var" pattern

For env vars:
```toml
# wrangler.toml
[vars]
ENVIRONMENT = "production"
LOG_LEVEL = "info"
FEATURE_NEW_DASHBOARD = "true"
```

```ts
// In the Worker
const isNewDashboard = env.FEATURE_NEW_DASHBOARD === 'true';
```

Env vars are per-environment; they don't change at
runtime.

## The "secret" pattern

For secrets:
```bash
wrangler secret put STRIPE_SECRET_KEY
wrangler secret put OPENAI_API_KEY
```

```ts
// In the Worker
const stripeKey = env.STRIPE_SECRET_KEY;
```

Secrets are encrypted; not in the repo.

## The "runtime config" pattern

For runtime config, store in D1 or KV:
```sql
CREATE TABLE app_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

```ts
async function getConfig<T>(key: string, env: Env, defaultValue: T): Promise<T> {
  const row = await env.DB!.prepare(
    `SELECT value FROM app_config WHERE key = ?`
  ).bind(key).first<{ value: string }>();
  return row ? JSON.parse(row.value) : defaultValue;
}

async function setConfig(key: string, value: unknown, env: Env): Promise<void> {
  await env.DB!.prepare(
    `INSERT INTO app_config (key, value) VALUES (?, ?)
     ON CONFLICT (key) DO UPDATE SET value = ?, updated_at = ?`
  ).bind(key, JSON.stringify(value), JSON.stringify(value), new Date().toISOString()).run();
}
```

The config is in the DB; changes don't require a deploy.

## The "config schema" pattern

For a typed config:
```ts
interface AppConfig {
  maintenanceMode: boolean;
  newDashboardEnabled: boolean;
  signupBonus: number;
  supportEmail: string;
}

async function getAppConfig(env: Env): Promise<AppConfig> {
  const config = await getConfig<Partial<AppConfig>>('app_config', env, {});
  return {
    maintenanceMode: false,
    newDashboardEnabled: true,
    signupBonus: 0,
    supportEmail: 'support@example.com',
    ...config,
  };
}
```

The config is typed; missing values have defaults.

## The "config validation" pattern

For invalid config, fail fast:
```ts
function validateConfig(config: AppConfig): void {
  if (config.signupBonus < 0) throw new Error('Invalid signupBonus');
  if (!config.supportEmail.includes('@')) throw new Error('Invalid supportEmail');
  // ... more validation
}
```

Invalid config is caught early.

## The "config cache" pattern

For performance, cache the config:
```ts
class ConfigCache {
  private cache: AppConfig | null = null;
  private expiresAt = 0;

  async get(env: Env): Promise<AppConfig> {
    if (this.cache && this.expiresAt > Date.now()) return this.cache;

    this.cache = await getAppConfig(env);
    this.expiresAt = Date.now() + 60_000;  // 1 min cache

    return this.cache;
  }

  invalidate() {
    this.cache = null;
    this.expiresAt = 0;
  }
}
```

The config is cached for 1 min; invalidated on update.

## The "config audit" pattern

For audit, log every config change:
```ts
async function setConfig(key: string, value: unknown, ctx: McContext, env: Env): Promise<void> {
  const oldValue = await getConfig(key, env, null);

  await env.DB!.prepare(
    `INSERT INTO app_config (key, value) VALUES (?, ?)
     ON CONFLICT (key) DO UPDATE SET value = ?, updated_at = ?`
  ).bind(key, JSON.stringify(value), JSON.stringify(value), new Date().toISOString()).run();

  await writeAudit(env, {
    userId: ctx.user.id,
    action: 'config.changed',
    resourceType: 'config',
    resourceId: key,
    metadata: { oldValue, newValue: value },
  });
}
```

Every change is logged.

## The "config UI" pattern

For an admin UI:
```tsx
function ConfigEditor() {
  const { data: config } = useSWR('/api/admin/config', fetcher);
  const [value, setValue] = useState('');

  const handleSave = async () => {
    await fetch('/api/admin/config', {
      method: 'PATCH',
      body: JSON.stringify({ key: 'maintenanceMode', value }),
    });
  };

  return (
    <div>
      <h1>Config</h1>
      <input value={value} onChange={(e) => setValue(e.target.value)} />
      <button onClick={handleSave}>Save</button>
    </div>
  );
}
```

The admin can edit config from the UI.

## The "config change" notification

For "config changed" notifications:
```ts
// After a config change
await env.CONFIG_CHANGE_QUEUE.send({ key, value });

// Worker
export default {
  async queue(batch: MessageBatch<ConfigChange>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      // Invalidate the cache
      configCache.invalidate();

      // Notify subscribers
      await env.SSE_QUEUE.send({ event: 'config.changed', data: message.body });

      message.ack();
    }
  },
};
```

Subscribers are notified of changes.

## The "config version" pattern

For tracking config changes:
```sql
CREATE TABLE app_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_by TEXT
);
```

The version increments on every change; you can roll back
to a specific version.

## The "config environment" pattern

For per-environment config:
```ts
async function getConfig<T>(key: string, env: Env, defaultValue: T): Promise<T> {
  // env-specific key
  const envKey = `${key}:${env.ENVIRONMENT}`;
  const row = await env.DB!.prepare(`SELECT value FROM app_config WHERE key = ?`).bind(envKey).first();
  if (row) return JSON.parse(row.value);

  // fallback to default
  return defaultValue;
}
```

Each environment has its own config.

## The "config" anti-patterns

### 1. Config in code
- **Issue:** Config change requires a deploy
- **Fix:** Use env vars or runtime config

### 2. Secret in code
- **Issue:** A breach exposes the secret
- **Fix:** Use `wrangler secret`

### 3. No validation
- **Issue:** Invalid config breaks the app
- **Fix:** Validate on load

### 4. No audit
- **Issue:** No record of who changed what
- **Fix:** Audit log

### 5. No cache
- **Issue:** Every request fetches the config
- **Fix:** In-memory cache

## Verification
- **Test:** Config is loaded correctly
- **Test:** Config can be updated
- **Test:** Changes don't require a deploy
- **Live:** Config is monitored
- **Audit:** Quarterly review of config

## Gotchas
- **The "config in code" anti-pattern.** Config change
  requires a deploy.
- **The "no validation" anti-pattern.** Invalid config
  breaks the app at runtime.
- **The "no cache" anti-pattern.** Config fetches slow
  down the request.
- **The "no audit" anti-pattern.** No record of who
  changed what.

## Related
- `secrets-management-detail.md`
- `feature-flags-implementations.md`
- `feature-environment-promotion.md`
- `safe-deploy-checklist.md`
- `audit-log-as-product.md`
