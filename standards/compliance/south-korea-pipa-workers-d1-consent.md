# South Korea PIPA Compliance with Workers and D1: Consent, Purpose Limitation, and Retention

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your service processes personal information (개인정보) of South Korean users. You need to comply with the Personal Information Protection Act (PIPA / 개인정보 보호법), including obtaining valid consent tied to specific purposes, maintaining auditable consent records, enforcing the 5-year maximum retention period for consent records, and providing a withdrawal-of-consent endpoint — all using Cloudflare Workers and D1.

## Context

PIPA (most recently amended 2023, enforcement expanded 2024) is enforced by the Personal Information Protection Commission (PIPC / 개인정보보호위원회). Key obligations:

- **Article 15** — personal information may only be collected with the data subject's consent, tied to a specific and disclosed purpose.
- **Article 16** — collection must be minimised to what is necessary.
- **Article 22** — consent must be obtained separately for each purpose; bundled consent is prohibited.
- **Article 36** — data subjects may withdraw consent at any time.
- **Article 21** — personal information must be destroyed when the retention period expires.
- Fines up to KRW 3 billion (≈ USD 2.3M) or 3 % of global turnover for serious violations.

## D1 Schema — consent_records

```sql
CREATE TABLE IF NOT EXISTS consent_records (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT    NOT NULL,
  purpose      TEXT    NOT NULL,   -- PURPOSE_CODES enum value
  collected_at TEXT    NOT NULL DEFAULT (datetime('now')),
  expires_at   TEXT    NOT NULL,   -- max 5 years from collected_at
  withdrawn_at TEXT,               -- NULL = still active
  ip_hash      TEXT,               -- SHA-256 of IP for audit, not raw IP
  agent_hash   TEXT                -- SHA-256 of User-Agent
);

CREATE INDEX IF NOT EXISTS idx_consent_user
  ON consent_records(user_id, purpose, withdrawn_at);

CREATE TABLE IF NOT EXISTS consent_audit (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  consent_id INTEGER NOT NULL REFERENCES consent_records(id),
  event      TEXT    NOT NULL,  -- 'granted' | 'withdrawn' | 'expired'
  occurred_at TEXT   NOT NULL DEFAULT (datetime('now'))
);
```

## PURPOSE_CODES Enum and Consent Grant Worker

```typescript
// workers/pipa-consent.ts
import { Env } from './types';

/** PIPC-aligned processing purpose categories (Article 15 / Article 22) */
export const PURPOSE_CODES = {
  SERVICE_PROVISION:      'SERVICE_PROVISION',      // 서비스 제공
  MARKETING:              'MARKETING',              // 마케팅 및 광고
  ANALYTICS:              'ANALYTICS',              // 서비스 개선 및 통계
  THIRD_PARTY_SHARING:    'THIRD_PARTY_SHARING',    // 제3자 제공
  SENSITIVE_BIOMETRIC:    'SENSITIVE_BIOMETRIC',    // 고유식별정보(바이오)
  SENSITIVE_HEALTH:       'SENSITIVE_HEALTH',       // 민감정보(건강)
  CROSS_BORDER_TRANSFER:  'CROSS_BORDER_TRANSFER',  // 국외 이전
} as const;

export type PurposeCode = keyof typeof PURPOSE_CODES;

/** Retention: 5 years maximum per PIPA Article 21 guidance */
const RETENTION_YEARS = 5;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/consent/grant') {
      return handleGrant(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/consent/withdraw') {
      return handleWithdraw(request, env);
    }
    if (request.method === 'GET' && url.pathname === '/consent/status') {
      return handleStatus(request, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function handleGrant(request: Request, env: Env): Promise<Response> {
  const { userId, purposes } = await request.json<{
    userId: string;
    purposes: PurposeCode[];
  }>();

  if (!userId || !Array.isArray(purposes) || purposes.length === 0) {
    return new Response(JSON.stringify({ error: 'userId and purposes required' }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  // Validate all purpose codes
  const invalid = purposes.filter(p => !(p in PURPOSE_CODES));
  if (invalid.length > 0) {
    return new Response(JSON.stringify({ error: `Unknown purposes: ${invalid}` }), {
      status: 400, headers: { 'Content-Type': 'application/json' },
    });
  }

  const expiresAt = new Date();
  expiresAt.setFullYear(expiresAt.getFullYear() + RETENTION_YEARS);
  const expiresAtStr = expiresAt.toISOString();

  const ipHash = await sha256(request.headers.get('CF-Connecting-IP') ?? '');
  const agentHash = await sha256(request.headers.get('User-Agent') ?? '');

  const results: { purpose: PurposeCode; consentId: number }[] = [];

  for (const purpose of purposes) {
    const ins = await env.DB.prepare(
      `INSERT INTO consent_records (user_id, purpose, expires_at, ip_hash, agent_hash)
       VALUES (?, ?, ?, ?, ?)`
    ).bind(userId, purpose, expiresAtStr, ipHash, agentHash).run();

    const consentId = ins.meta.last_row_id as number;

    await env.DB.prepare(
      `INSERT INTO consent_audit (consent_id, event) VALUES (?, 'granted')`
    ).bind(consentId).run();

    results.push({ purpose, consentId });
  }

  return new Response(JSON.stringify({ granted: results, expires_at: expiresAtStr }), {
    status: 201, headers: { 'Content-Type': 'application/json' },
  });
}

async function handleWithdraw(request: Request, env: Env): Promise<Response> {
  const { userId, purpose } = await request.json<{
    userId: string;
    purpose: PurposeCode;
  }>();

  const row = await env.DB.prepare(
    `SELECT id FROM consent_records
     WHERE user_id = ? AND purpose = ? AND withdrawn_at IS NULL
     LIMIT 1`
  ).bind(userId, purpose).first<{ id: number }>();

  if (!row) {
    return new Response(JSON.stringify({ error: 'Active consent not found' }), {
      status: 404, headers: { 'Content-Type': 'application/json' },
    });
  }

  await env.DB.prepare(
    `UPDATE consent_records SET withdrawn_at = datetime('now') WHERE id = ?`
  ).bind(row.id).run();

  await env.DB.prepare(
    `INSERT INTO consent_audit (consent_id, event) VALUES (?, 'withdrawn')`
  ).bind(row.id).run();

  return new Response(JSON.stringify({ withdrawn: true, consentId: row.id }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  });
}

async function handleStatus(request: Request, env: Env): Promise<Response> {
  const userId = new URL(request.url).searchParams.get('userId');
  if (!userId) return new Response('userId required', { status: 400 });

  const { results } = await env.DB.prepare(
    `SELECT purpose, collected_at, expires_at, withdrawn_at
     FROM consent_records WHERE user_id = ?`
  ).bind(userId).all();

  return new Response(JSON.stringify({ consents: results }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  });
}

async function sha256(input: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(input));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## Cron Trigger — 5-Year Retention Purge

PIPA Article 21 requires destruction of personal information when the retention period lapses. A scheduled Worker runs nightly to purge expired consent records.

```typescript
// workers/pipa-purge.ts  (scheduled handler)
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Mark expired
    await env.DB.prepare(
      `UPDATE consent_records
       SET withdrawn_at = datetime('now')
       WHERE expires_at < datetime('now') AND withdrawn_at IS NULL`
    ).run();

    // Audit
    await env.DB.prepare(
      `INSERT INTO consent_audit (consent_id, event)
       SELECT id, 'expired' FROM consent_records
       WHERE expires_at < datetime('now')
         AND id NOT IN (SELECT consent_id FROM consent_audit WHERE event = 'expired')`
    ).run();

    // Hard-delete records expired more than 90 days ago
    await env.DB.prepare(
      `DELETE FROM consent_records
       WHERE expires_at < datetime('now', '-90 days')`
    ).run();
  },
};
```

```toml
# wrangler.toml
[triggers]
crons = ["0 1 * * *"]   # 01:00 UTC daily
```

## Anti-patterns

- Bundling all purposes into a single consent checkbox — PIPA Article 22 requires separate consent per purpose.
- Storing raw IP addresses in consent records — hash them; raw IPs constitute personal information under PIPA.
- Never running the purge job — expired data left in D1 constitutes a retention violation.
- Recording consent without logging the specific purposes disclosed to the user at collection time.

## Gotchas

- PIPA distinguishes **sensitive information** (health, biometrics, political opinion) which requires **explicit separate consent** and heightened security measures.
- Cross-border transfers require either PIPC adequacy recognition or data subject consent — `CROSS_BORDER_TRANSFER` purpose code must be collected separately.
- The 2023 amendments align PIPA more closely with GDPR; `PURPOSE_CODES.ANALYTICS` still requires opt-in consent (unlike some GDPR legitimate interest interpretations).
- PIPC can impose fines of up to 3 % of annual turnover for violations of consent requirements.

## Verification

```bash
# Check active consents for a user
wrangler d1 execute example project-db --command \
  "SELECT purpose, collected_at, expires_at FROM consent_records \
   WHERE user_id = 'u_001' AND withdrawn_at IS NULL;"

# Confirm purge job ran
wrangler d1 execute example project-db --command \
  "SELECT * FROM consent_audit WHERE event = 'expired' ORDER BY occurred_at DESC LIMIT 5;"

# Test withdrawal endpoint
curl -X POST https://privacy.example.com/consent/withdraw \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u_001","purpose":"MARKETING"}'
```

## Related

- `documentation/categories/compliance/australia-privacy-act-workers-d1.md`
- `documentation/categories/compliance/indonesia-pdp-law-workers-d1.md`
- `documentation/categories/compliance/hong-kong-pdpo-workers-d1.md`

## Sources

- Personal Information Protection Act (PIPA): https://www.law.go.kr/engLsSc.do?menuId=1&subMenuId=21&tabMenuId=117
- PIPC official site: https://www.pipc.go.kr/
- PIPA 2023 Amendment summary: https://www.pipc.go.kr/np/cop/bbs/selectBoardArticle.do
- Cloudflare Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
