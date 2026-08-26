# GDPR Lawful Basis — Workers D1 Consent Event Log & Consent Gate Middleware

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Anonymous social platform (example project / example.com) processes user-generated content, push
notifications, analytics, and optional personalisation features. Without a documented
lawful basis for each processing activity, any EU supervisory authority audit results in
an Article 83 fine. Engineers ask: "when do we need consent vs legitimate interest, and
how do we wire that into Workers + D1?"

## Context

GDPR Article 6 lists six lawful bases. For a consumer social app:

- **Consent (Art. 6(1)(a))** is required for non-essential cookies, targeted advertising,
  and optional analytics.
- **Legitimate Interest (Art. 6(1)(f))** may cover security logging, fraud prevention,
  and core service improvement — only after a three-part LIA (purpose, necessity,
  balancing test) is documented and stored.
- **Contract (Art. 6(1)(b))** covers data strictly needed to deliver the service the user
  signed up for (e.g. routing posts to followers).

example project is anonymous-first: no real name, optional pseudonym. Consent strings must be
persisted independently of any user account so that withdrawal is honoured even for
guest sessions. Cloudflare Workers + D1 handles edge consent gating; KV provides fast
reads for hot paths.

## Lawful Basis Decision Matrix

```
+----------------------------------+-------------------+-------------------+
| Processing Activity              | Basis             | Requires Consent? |
+----------------------------------+-------------------+-------------------+
| Deliver posts to followers       | Contract 6(1)(b)  | No                |
| Security & abuse logging         | Leg. Interest (f) | No (LIA required) |
| Non-essential analytics          | Consent (a)       | Yes               |
| Push notifications (marketing)   | Consent (a)       | Yes               |
| Content personalisation ML       | Consent (a)       | Yes               |
| CSAM detection (mandatory)       | Legal oblig. (c)  | No                |
| Fraud / spam detection           | Leg. Interest (f) | No (LIA required) |
+----------------------------------+-------------------+-------------------+
```

## D1 Consent Event Log Schema

```sql
-- migrations/0010_consent_events.sql
CREATE TABLE consent_events (
  id            TEXT      PRIMARY KEY,          -- UUIDv7
  session_token TEXT      NOT NULL,             -- HMAC-SHA256(device_id, salt)
  purpose_id    TEXT      NOT NULL,             -- 'analytics' | 'push' | 'personalisation'
  action        TEXT      NOT NULL CHECK(action IN ('grant','withdraw','refresh')),
  lawful_basis  TEXT      NOT NULL DEFAULT 'consent',
  tcf_string    TEXT,                           -- IAB TCF v2.2 string if applicable
  ip_hash       TEXT,                           -- SHA-256 truncated to 12 bytes, hex
  user_agent_ua TEXT,
  recorded_at   INTEGER   NOT NULL,             -- Unix ms, UTC
  expires_at    INTEGER                         -- NULL = until withdrawn
);

CREATE INDEX idx_ce_session ON consent_events(session_token, purpose_id, recorded_at DESC);
CREATE INDEX idx_ce_purpose  ON consent_events(purpose_id, recorded_at DESC);

-- Legitimate interest assessments (one row per LIA)
CREATE TABLE lia_register (
  purpose_id    TEXT      PRIMARY KEY,
  description   TEXT      NOT NULL,
  necessity_ok  INTEGER   NOT NULL CHECK(necessity_ok IN (0,1)),
  balancing_ok  INTEGER   NOT NULL CHECK(balancing_ok IN (0,1)),
  reviewer      TEXT      NOT NULL,
  reviewed_at   INTEGER   NOT NULL,
  next_review   INTEGER   NOT NULL
);
```

## Workers Consent Gate Middleware

```typescript
// workers/src/middleware/consent-gate.ts
import { D1Database, ExecutionContext } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  CONSENT_KV: KVNamespace;
  CONSENT_SALT: string;
}

const PURPOSE_BASIS: Record<string, 'consent' | 'legitimate_interest' | 'contract'> = {
  analytics:       'consent',
  push:            'consent',
  personalisation: 'consent',
  security_log:    'legitimate_interest',
  fraud_detect:    'legitimate_interest',
  post_delivery:   'contract',
};

async function hmacSession(deviceId: string, salt: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(salt),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(deviceId));
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2,'0')).join('');
}

export async function consentGate(
  purpose: string,
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<{ allowed: boolean; basis: string }> {
  const basis = PURPOSE_BASIS[purpose] ?? 'consent';

  // Contract & LI bases bypass consent check (LIA must be pre-documented in lia_register)
  if (basis !== 'consent') return { allowed: true, basis };

  const deviceId = request.headers.get('X-Device-Id') ?? 'anonymous';
  const sessionToken = await hmacSession(deviceId, env.CONSENT_SALT);
  const cacheKey = `consent:${sessionToken}:${purpose}`;

  // Fast path: KV cache (TTL 300 s)
  const cached = await env.CONSENT_KV.get(cacheKey);
  if (cached !== null) return { allowed: cached === 'grant', basis };

  // Slow path: D1 authoritative record
  const row = await env.DB.prepare(`
    SELECT action FROM consent_events
    WHERE session_token = ? AND purpose_id = ?
    ORDER BY recorded_at DESC LIMIT 1
  `).bind(sessionToken, purpose).first<{ action: string }>();

  const allowed = row?.action === 'grant';
  ctx.waitUntil(env.CONSENT_KV.put(cacheKey, allowed ? 'grant' : 'deny', { expirationTtl: 300 }));
  return { allowed, basis };
}

// Record consent event
export async function recordConsent(
  purpose: string,
  action: 'grant' | 'withdraw' | 'refresh',
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<void> {
  const deviceId = request.headers.get('X-Device-Id') ?? 'anonymous';
  const sessionToken = await hmacSession(deviceId, env.CONSENT_SALT);
  const id = crypto.randomUUID();
  const now = Date.now();

  ctx.waitUntil(
    env.DB.prepare(`
      INSERT INTO consent_events
        (id, session_token, purpose_id, action, lawful_basis, ip_hash, recorded_at)
      VALUES (?, ?, ?, ?, 'consent', ?, ?)
    `).bind(id, sessionToken, purpose, action, ipHash(request), now).run()
  );
  // Invalidate KV cache on change
  ctx.waitUntil(env.CONSENT_KV.delete(`consent:${sessionToken}:${purpose}`));
}

function ipHash(req: Request): string {
  const ip = req.headers.get('CF-Connecting-IP') ?? '';
  // truncated hash for minimal retention
  return ip.slice(0, 6) + '****';
}
```

## Mobile Consent Flow UX

```
[App cold start]
      |
      v
Is this first launch or consent_version < current?
      | YES
      v
Show Consent Modal (full-screen, no dark patterns)
  +-------------------------------------------+
  | example project uses your data for:                  |
  |  [ ] Analytics (optional)                  |
  |  [ ] Personalisation (optional)            |
  |  Push Notifications: separate OS prompt   |
  |                                           |
  | [Accept selected]   [Reject all]          |
  +-------------------------------------------+
      |
      v
POST /api/consent { purposes: [...], action: "grant"|"deny" }
      |
      v
Server records consent_events row, returns consent_token
      |
      v
App stores consent_token in SecureStorage
      |
      v
App attaches X-Device-Id header on all subsequent requests
```

Rules enforced:
- Modal cannot be dismissed without an explicit choice.
- "Reject all" is as prominent as "Accept selected".
- Granular toggles default to OFF for non-essential purposes.
- Consent version bumped whenever processing purposes change; re-prompt required.

## Anti-patterns

- Storing consent by user account ID only — anonymous sessions lose their consent
  state on logout; tie to device-level pseudonymous token instead.
- Bundling legitimate interest and consent purposes in one toggle — each lawful basis
  must be independently documented and presented.
- Using a single `consented: boolean` column — must capture purpose, timestamp, version,
  and withdrawal separately for audit trail completeness.
- Skipping LIA documentation and relying on "we have a legitimate interest" verbally —
  Art. 6(1)(f) requires a written balancing test kept in the `lia_register`.
- Invalidating the KV cache only on grant, not on withdraw — creates a window where
  a withdrawn consent is still honoured.

## Gotchas

- **Art. 7(3) withdrawal must be as easy as giving consent** — the mobile UI must expose
  a one-tap "Withdraw consent" in Settings, not buried three menus deep.
- **Children**: if a user is or may be under 16 (EU default), consent requires parental
  authorisation; fall back to contract/LI-only bases for that cohort.
- **Consent refresh**: if more than 12 months have elapsed since the last `grant` event,
  re-prompt the user even if no purpose has changed (good-practice benchmark).
- **KV TTL and Durable Objects**: if you use DO for state, be careful not to cache
  consent decisions in DO memory beyond the KV TTL.
- **D1 replication lag** (~150 ms p99): always write consent events via `waitUntil` and
  never block the response on the write completing.

## Verification

```bash
# Confirm consent event was written
wrangler d1 execute example project-prod \
  --command "SELECT purpose_id, action, recorded_at FROM consent_events \
             ORDER BY recorded_at DESC LIMIT 10;"

# Check LIA register is populated
wrangler d1 execute example project-prod \
  --command "SELECT purpose_id, necessity_ok, balancing_ok, next_review FROM lia_register;"

# Smoke-test consent gate returns 403 for non-consented analytics
curl -X GET https://example.com/api/analytics/events \
  -H "X-Device-Id: test-device-no-consent" \
  -w "\nHTTP %{http_code}\n"
# Expected: HTTP 403

# Verify KV cache invalidation after withdrawal
wrangler kv key list --namespace-id $CONSENT_KV_ID | grep "test-device"
```

## Related

- `gdpr-consent-management.md`
- `gdpr-legitimate-interest-assessment.md`
- `cookie-consent-cloudflare-pages-workers.md`
- `data-minimization-workers-d1-pii-redaction.md`
- `gdpr-data-retention-policy.md`

## Sources

- GDPR Art. 6, 7, 13 — EUR-Lex
- EDPB Guidelines 05/2020 on consent (v1.1)
- EDPB Guidelines 06/2020 on legitimate interest (adopted 2024)
- Cloudflare D1 documentation — developers.cloudflare.com/d1
- Cloudflare Workers KV — developers.cloudflare.com/kv
- IAB Europe TCF v2.2 specification
