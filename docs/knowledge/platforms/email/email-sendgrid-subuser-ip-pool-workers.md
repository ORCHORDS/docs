# SendGrid Subuser and IP Pool Management via Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A SaaS platform provisions a SendGrid subuser and assigns it to a dedicated IP pool for each
customer tenant, so that one tenant's poor sending reputation cannot affect others. The provisioning
and routing logic must run inside Cloudflare Workers without a persistent server.

## Context

SendGrid subusers are isolated sending identities under a parent account. Each subuser has its own
API keys, statistics, and can be pinned to specific IP pools. Cloudflare Workers call the SendGrid
Web API v3 to automate provisioning and route outbound mail through the correct subuser credential
at send time. Tenant metadata is stored in D1.

SendGrid Web API base: `https://api.sendgrid.com/v3`

---

## 1. D1 Schema

```sql
CREATE TABLE tenants (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  sg_username     TEXT UNIQUE,           -- subuser username
  sg_api_key      TEXT,                  -- encrypted subuser API key
  ip_pool_name    TEXT,                  -- assigned IP pool
  status          TEXT NOT NULL DEFAULT 'pending',
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE ip_pools (
  name       TEXT PRIMARY KEY,
  capacity   INTEGER NOT NULL DEFAULT 10,
  allocated  INTEGER NOT NULL DEFAULT 0
);
```

---

## 2. Types

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
  SG_MASTER_KEY: string;     // parent account API key
  ENCRYPTION_KEY: string;    // AES-GCM key for storing subuser keys
}

export interface SubuserPayload {
  username: string;
  email: string;
  password: string;
  ips: string[];
}
```

---

## 3. Provision Subuser

```typescript
// src/provision.ts
import type { Env } from './types';

const SG = 'https://api.sendgrid.com/v3';

export async function provisionTenant(
  tenantId: string,
  tenantEmail: string,
  env: Env
): Promise<void> {
  const username = `tenant_${tenantId.replace(/-/g, '_')}`;
  const password = <redacted-secret> + crypto.randomUUID();

  // Pick the least-loaded IP pool
  const pool = await env.DB.prepare(
    `SELECT name FROM ip_pools
     WHERE allocated < capacity ORDER BY allocated ASC LIMIT 1`
  ).first<{ name: string }>();

  if (!pool) throw new Error('No IP pool capacity available');

  // Fetch IPs assigned to that pool from SendGrid
  const poolIps = await sgGet<{ ips: Array<{ ip: string }> }>(
    `/ips/pools/${pool.name}`, env.SG_MASTER_KEY
  );
  const ipList = poolIps.ips.map((i) => i.ip);

  // Create the subuser
  await sgPost('/subusers', {
    username,
    email: tenantEmail,
    password,
    ips: ipList,
  }, env.SG_MASTER_KEY);

  // Create a subuser-scoped API key
  const keyResp = await sgPostAs<{ api_key: string; api_key_id: string }>(
    username,
    '/api_keys',
    { name: `${username}-send`, scopes: ['mail.send'] },
    env.SG_MASTER_KEY
  );

  const encryptedKey = await encryptApiKey(keyResp.api_key, env.ENCRYPTION_KEY);

  // Assign IP pool to subuser
  await sgPostAs(
    username,
    `/ips/pools/${pool.name}`,
    {},
    env.SG_MASTER_KEY
  );

  // Persist
  await env.DB.prepare(
    `UPDATE tenants
     SET sg_username = ?, sg_api_key = ?, ip_pool_name = ?, status = 'active'
     WHERE id = ?`
  ).bind(username, encryptedKey, pool.name, tenantId).run();

  await env.DB.prepare(
    `UPDATE ip_pools SET allocated = allocated + 1 WHERE name = ?`
  ).bind(pool.name).run();
}

// ---- SendGrid helpers ----

async function sgGet<T>(path: string, key: string): Promise<T> {
  const r = await fetch(`${SG}${path}`, {
    headers: { Authorization: `Bearer ${key}` },
  });
  if (!r.ok) throw new Error(`SG GET ${path} → ${r.status}`);
  return r.json() as Promise<T>;
}

async function sgPost<T = unknown>(
  path: string, body: unknown, key: string
): Promise<T> {
  const r = await fetch(`${SG}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${key}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(`SG POST ${path} → ${r.status}: ${txt}`);
  }
  return r.json() as Promise<T>;
}

// Impersonate a subuser via On-Behalf-Of header
async function sgPostAs<T = unknown>(
  subuser: string, path: string, body: unknown, masterKey: string
): Promise<T> {
  const r = await fetch(`${SG}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${masterKey}`,
      'On-Behalf-Of': subuser,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(`SG POST as ${subuser} ${path} → ${r.status}: ${txt}`);
  }
  return r.json() as Promise<T>;
}
```

---

## 4. AES-GCM Key Encryption Helper

```typescript
// src/crypto.ts
const ALGO = { name: 'AES-GCM', length: 256 } as const;

async function importKey(rawHex: string): Promise<CryptoKey> {
  const raw = hexToBytes(rawHex);
  return crypto.subtle.importKey('raw', raw, ALGO, false, ['encrypt', 'decrypt']);
}

export async function encryptApiKey(plain: string, keyHex: string): Promise<string> {
  const key = await importKey(keyHex);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const cipher = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(plain)
  );
  const combined = new Uint8Array(iv.byteLength + cipher.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(cipher), iv.byteLength);
  return btoa(String.fromCharCode(...combined));
}

export async function decryptApiKey(encoded: string, keyHex: string): Promise<string> {
  const key = await importKey(keyHex);
  const combined = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
  const iv = combined.slice(0, 12);
  const data = combined.slice(12);
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, data);
  return new TextDecoder().decode(plain);
}

function hexToBytes(hex: string): Uint8Array {
  const arr = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2)
    arr[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  return arr;
}
```

---

## 5. Send Email via Tenant Subuser

```typescript
// src/send.ts
import { decryptApiKey } from './crypto';
import type { Env } from './types';

export async function sendAsTenant(
  tenantId: string,
  to: string,
  subject: string,
  html: string,
  env: Env
): Promise<string> {
  const tenant = await env.DB.prepare(
    `SELECT sg_api_key, ip_pool_name FROM tenants WHERE id = ? AND status = 'active'`
  ).bind(tenantId).first<{ sg_api_key: string; ip_pool_name: string }>();

  if (!tenant) throw new Error(`Tenant ${tenantId} not active`);

  const apiKey = await decryptApiKey(tenant.sg_api_key, env.ENCRYPTION_KEY);

  const payload = {
    personalizations: [{ to: [{ email: to }] }],
    from: { email: `noreply@${tenantId}.example.com` },
    subject,
    content: [{ type: 'text/html', value: html }],
    ip_pool_name: tenant.ip_pool_name,
  };

  const resp = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`SendGrid send error ${resp.status}: ${body}`);
  }

  return resp.headers.get('X-Message-Id') ?? '';
}
```

---

## Anti-patterns

- **Storing plaintext API keys in D1**: D1 is not a secrets store; always encrypt with a Worker secret.
- **Sharing one IP pool across all tenants**: A single spammer degrades deliverability for everyone.
- **Using the master API key to send mail**: Bypasses per-tenant statistics and subuser isolation.
- **Never rotating subuser API keys**: A compromised key grants permanent send access; rotate on a schedule.

## Gotchas

- `On-Behalf-Of` only works with the **parent account's** key, not a subuser key.
- IP pools must be created in advance and IPs must be provisioned on the parent account; Workers cannot provision new IPs.
- SendGrid subuser usernames are globally unique and cannot be reused after deletion.
- D1's `batch()` is not a transaction; use SQLite `BEGIN`/`COMMIT` via `exec` if atomicity matters across tables.

## Verification

```bash
# Confirm subuser exists
curl -s -H "Authorization: Bearer $SG_MASTER_KEY" \
  https://api.sendgrid.com/v3/subusers?username=tenant_abc | jq .

# Check IP pool allocation
curl -s -H "Authorization: Bearer $SG_MASTER_KEY" \
  "https://api.sendgrid.com/v3/ips/pools/pool-eu-1" | jq '.ips | length'

# Verify D1 tenant record
wrangler d1 execute email-db --command \
  "SELECT id, sg_username, ip_pool_name, status FROM tenants WHERE id='<tid>'"
```

## Related

- `sendgrid-setup.md`
- `sendgrid-resend-cloudflare-workers-integration.md`
- `email-multitenant-sender-isolation-d1-workers.md`
- `dedicated-ip-vs-shared.md`
- `email-domain-warmup-ip-pool-rotation-workers.md`

## Sources

- https://docs.sendgrid.com/api-reference/subusers-api/create-subuser
- https://docs.sendgrid.com/api-reference/ip-pools/create-an-ip-pool
- https://docs.sendgrid.com/api-reference/mail-send/mail-send (ip_pool_name field)
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
