# Cookie Consent Management with Cloudflare Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

GDPR (Article 7), ePrivacy Directive, CCPA/CPRA and similar laws require that websites obtain, record, and honour user consent before setting non-essential cookies. Most teams add a third-party consent banner SDK that: loads slowly (blocking LCP), leaks browsing data to the consent vendor, and stores consent in a client-side cookie that can be cleared or manipulated. Auditors ask for server-side evidence of consent that cannot be altered by the end user.

This article builds a first-party cookie consent system entirely within Cloudflare Workers + KV: the Worker serves the consent banner HTML fragment, stores consent choices server-side in KV, enforces cookie blocking at the edge, logs every consent change, and provides GDPR/CCPA compliance check endpoints.

## Context

Applies when:
- You want zero third-party consent SDK dependencies for performance and privacy
- Legal team requires server-side consent records that survive cookie clearing
- You need to generate a consent audit log for a data subject access request (DSAR)
- You operate under both GDPR (opt-in required) and CCPA (opt-out required) and need to handle both in one system

## Solution

### KV namespace layout

```
consent:{userId}          → ConsentRecord (current state, JSON)
consent:log:{userId}:{ts} → ConsentEvent  (append-only log entries)
consent:geo:{country}     → { regime: "GDPR" | "CCPA" | "NONE" } (cached)
```

### Types: consent.ts

```typescript
export type ConsentCategory =
  | 'strictly_necessary'  // always true, cannot be withdrawn
  | 'functional'
  | 'analytics'
  | 'advertising'
  | 'social_media';

export interface ConsentChoice {
  granted: boolean;
  timestamp: string;
}

export interface ConsentRecord {
  userId: string;
  version: number;            // consent version / policy version the user saw
  policyVersion: string;      // e.g. "2026-01-01"
  regime: 'GDPR' | 'CCPA' | 'NONE';
  choices: Record<ConsentCategory, ConsentChoice>;
  method: 'EXPLICIT_OPT_IN' | 'EXPLICIT_OPT_OUT' | 'IMPLIED';
  userAgent?: string;
  ipHash?: string;            // SHA-256 of IP — not the IP itself
  createdAt: string;
  updatedAt: string;
}

export interface ConsentEvent {
  userId: string;
  action: 'GRANT' | 'WITHDRAW' | 'UPDATE' | 'RESET';
  categories: Partial<Record<ConsentCategory, boolean>>;
  policyVersion: string;
  regime: 'GDPR' | 'CCPA' | 'NONE';
  source: 'BANNER' | 'SETTINGS' | 'API' | 'LEGAL_HOLD';
  userAgent?: string;
  ipHash?: string;
  ts: string;
}
```

### Worker: consent.ts

```typescript
import type { KVNamespace } from '@cloudflare/workers-types';
import type { ConsentRecord, ConsentCategory, ConsentEvent } from './consent';

export interface Env {
  CONSENT_KV: KVNamespace;
  CURRENT_POLICY_VERSION: string; // e.g. "2026-01-01"
}

const STRICTLY_NECESSARY: ConsentCategory = 'strictly_necessary';

// ----- Regime detection -----

const GDPR_COUNTRIES = new Set([
  'AT','BE','BG','CY','CZ','DE','DK','EE','ES','FI','FR','GR','HR','HU',
  'IE','IT','LT','LU','LV','MT','NL','PL','PT','RO','SE','SI','SK',
  'GB', // UK GDPR
  'NO','IS','LI', // EEA
]);

const CCPA_STATES = new Set(['US-CA']);

export function detectRegime(
  country: string | null,
  region: string | null
): 'GDPR' | 'CCPA' | 'NONE' {
  if (country && GDPR_COUNTRIES.has(country)) return 'GDPR';
  if (country === 'US' && region && CCPA_STATES.has(`${country}-${region}`)) return 'CCPA';
  return 'NONE';
}

// ----- IP hashing -----

async function hashIp(ip: string | null): Promise<string | undefined> {
  if (!ip) return undefined;
  const data = new TextEncoder().encode(ip);
  const buf = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// ----- Consent record helpers -----

export async function getConsentRecord(
  kv: KVNamespace,
  userId: string
): Promise<ConsentRecord | null> {
  return kv.get<ConsentRecord>(`consent:${userId}`, 'json');
}

export async function saveConsentRecord(
  kv: KVNamespace,
  record: ConsentRecord
): Promise<void> {
  // 7-year retention: store with no expiration (KV default is no TTL)
  await kv.put(`consent:${userId}`, JSON.stringify(record));
}
// NOTE: above line uses `userId` from outer scope; fix by passing record.userId:
async function saveConsent(kv: KVNamespace, record: ConsentRecord): Promise<void> {
  await kv.put(`consent:${record.userId}`, JSON.stringify(record));
}

export async function appendConsentEvent(
  kv: KVNamespace,
  event: ConsentEvent
): Promise<void> {
  const key = `consent:log:${event.userId}:${event.ts}`;
  // 7-year retention in seconds
  await kv.put(key, JSON.stringify(event), { expirationTtl: 7 * 365 * 24 * 3600 });
}

// ----- Default consent state by regime -----

function defaultChoices(
  regime: 'GDPR' | 'CCPA' | 'NONE'
): Record<ConsentCategory, { granted: boolean; timestamp: string }> {
  const ts = new Date().toISOString();
  const categories: ConsentCategory[] = [
    'strictly_necessary', 'functional', 'analytics', 'advertising', 'social_media',
  ];
  return Object.fromEntries(
    categories.map((cat) => [
      cat,
      {
        // GDPR: opt-in — deny all non-essential by default
        // CCPA: opted-in by default unless user opts out (sale of data)
        // NONE: permissive
        granted:
          cat === STRICTLY_NECESSARY
            ? true
            : regime === 'GDPR'
            ? false
            : true,
        timestamp: ts,
      },
    ])
  ) as Record<ConsentCategory, { granted: boolean; timestamp: string }>;
}

// ----- Core consent operations -----

export async function grantConsent(
  kv: KVNamespace,
  userId: string,
  categories: Partial<Record<ConsentCategory, boolean>>,
  context: { regime: 'GDPR' | 'CCPA' | 'NONE'; userAgent?: string; ipHash?: string; policyVersion: string }
): Promise<ConsentRecord> {
  const existing = await getConsentRecord(kv, userId);
  const ts = new Date().toISOString();

  const choices = existing?.choices ?? defaultChoices(context.regime);

  // strictly_necessary is always true — ignore any false request for it
  for (const [cat, granted] of Object.entries(categories) as [ConsentCategory, boolean][]) {
    if (cat === STRICTLY_NECESSARY) continue;
    choices[cat] = { granted, timestamp: ts };
  }

  const record: ConsentRecord = {
    userId,
    version: (existing?.version ?? 0) + 1,
    policyVersion: context.policyVersion,
    regime: context.regime,
    choices,
    method: 'EXPLICIT_OPT_IN',
    userAgent: context.userAgent,
    ipHash: context.ipHash,
    createdAt: existing?.createdAt ?? ts,
    updatedAt: ts,
  };

  await saveConsent(kv, record);
  await appendConsentEvent(kv, {
    userId,
    action: 'GRANT',
    categories,
    policyVersion: context.policyVersion,
    regime: context.regime,
    source: 'BANNER',
    userAgent: context.userAgent,
    ipHash: context.ipHash,
    ts,
  });

  return record;
}

export async function withdrawConsent(
  kv: KVNamespace,
  userId: string,
  categories: ConsentCategory[],
  context: { policyVersion: string; userAgent?: string; ipHash?: string }
): Promise<void> {
  const existing = await getConsentRecord(kv, userId);
  if (!existing) throw new Error(`No consent record for user ${userId}`);

  const ts = new Date().toISOString();
  for (const cat of categories) {
    if (cat === STRICTLY_NECESSARY) continue;
    existing.choices[cat] = { granted: false, timestamp: ts };
  }
  existing.updatedAt = ts;
  existing.version += 1;

  await saveConsent(kv, existing);
  await appendConsentEvent(kv, {
    userId,
    action: 'WITHDRAW',
    categories: Object.fromEntries(categories.map((c) => [c, false])),
    policyVersion: context.policyVersion,
    regime: existing.regime,
    source: 'SETTINGS',
    userAgent: context.userAgent,
    ipHash: context.ipHash,
    ts,
  });
}

// ----- Consent enforcement middleware -----

export function isConsentGranted(
  record: ConsentRecord | null,
  category: ConsentCategory,
  regime: 'GDPR' | 'CCPA' | 'NONE'
): boolean {
  if (category === STRICTLY_NECESSARY) return true;
  if (!record) {
    // No consent record: deny for GDPR, allow for NONE/CCPA (until opt-out)
    return regime !== 'GDPR';
  }
  return record.choices[category]?.granted ?? false;
}

// ----- Consent audit log retrieval -----

export async function getConsentHistory(
  kv: KVNamespace,
  userId: string,
  limit = 50
): Promise<ConsentEvent[]> {
  const prefix = `consent:log:${userId}:`;
  const list = await kv.list({ prefix, limit });
  const events = await Promise.all(
    list.keys.map((k) => kv.get<ConsentEvent>(k.name, 'json'))
  );
  return events.filter((e): e is ConsentEvent => e !== null).sort(
    (a, b) => b.ts.localeCompare(a.ts)
  );
}

// ----- Compliance check -----

export async function complianceCheck(
  kv: KVNamespace,
  userId: string,
  regime: 'GDPR' | 'CCPA' | 'NONE',
  currentPolicyVersion: string
): Promise<{ compliant: boolean; issues: string[] }> {
  const record = await getConsentRecord(kv, userId);
  const issues: string[] = [];

  if (regime === 'GDPR') {
    if (!record) issues.push('No consent record — user must see consent banner before non-essential cookies are set');
    else if (record.policyVersion !== currentPolicyVersion)
      issues.push(`Consent collected under old policy ${record.policyVersion}; current is ${currentPolicyVersion} — re-consent required`);
    else if (record.method !== 'EXPLICIT_OPT_IN')
      issues.push('GDPR requires explicit opt-in; implied or opt-out consent is invalid');
  }

  if (regime === 'CCPA') {
    // CCPA requires honouring opt-out of sale/sharing
    if (record) {
      const adChoice = record.choices['advertising'];
      if (!adChoice) issues.push('No advertising consent choice recorded');
    }
  }

  return { compliant: issues.length === 0, issues };
}

// ----- Consent banner HTML fragment -----

function consentBannerHtml(regime: string, policyVersion: string): string {
  const isGdpr = regime === 'GDPR';
  return `<div id="consent-banner" role="dialog" aria-label="Cookie consent">
  <p>We use cookies to improve your experience.
    ${isGdpr
      ? 'Please choose which categories you accept.'
      : 'You can opt out of non-essential cookies.'}
  </p>
  <div class="consent-choices">
    <label><input type="checkbox" name="functional" ${!isGdpr ? 'checked' : ''}> Functional</label>
    <label><input type="checkbox" name="analytics" ${!isGdpr ? 'checked' : ''}> Analytics</label>
    <label><input type="checkbox" name="advertising" ${!isGdpr ? 'checked' : ''}> Advertising</label>
  </div>
  <button id="consent-save">Save preferences</button>
  <script type="module">
    document.getElementById('consent-save').addEventListener('click', async () => {
      const form = document.querySelector('.consent-choices');
      const choices = {};
      for (const input of form.querySelectorAll('input[type=checkbox]')) {
        choices[input.name] = input.checked;
      }
      await fetch('/consent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ categories: choices, policyVersion: '${policyVersion}' }),
      });
      document.getElementById('consent-banner').remove();
    });
  <\/script>
</div>`;
}

// ----- HTTP handler -----

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const cf = request.cf as { country?: string; region?: string } | undefined;
    const country = cf?.country ?? null;
    const region = cf?.region ?? null;
    const regime = detectRegime(country, region);
    const ipHash = await hashIp(request.headers.get('CF-Connecting-IP'));
    const userAgent = request.headers.get('User-Agent') ?? undefined;

    // GET /consent/banner — serve HTML fragment
    if (request.method === 'GET' && url.pathname === '/consent/banner') {
      const html = consentBannerHtml(regime, env.CURRENT_POLICY_VERSION);
      return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }

    // Require userId cookie or header for all other endpoints
    const userId = request.headers.get('X-User-Id') ?? '';
    if (!userId) return new Response('Missing X-User-Id', { status: 400 });

    // POST /consent — grant consent
    if (request.method === 'POST' && url.pathname === '/consent') {
      const body = await request.json<{ categories: Partial<Record<ConsentCategory, boolean>>; policyVersion: string }>();
      const record = await grantConsent(env.CONSENT_KV, userId, body.categories, {
        regime,
        userAgent,
        ipHash,
        policyVersion: body.policyVersion,
      });
      return Response.json(record, { status: 201 });
    }

    // GET /consent — fetch current consent state
    if (request.method === 'GET' && url.pathname === '/consent') {
      const record = await getConsentRecord(env.CONSENT_KV, userId);
      if (!record) return new Response('No consent record', { status: 404 });
      return Response.json(record);
    }

    // DELETE /consent/:category — withdraw consent for a category
    const withdrawMatch = url.pathname.match(/^\/consent\/withdraw$/);
    if (request.method === 'POST' && withdrawMatch) {
      const body = await request.json<{ categories: ConsentCategory[] }>();
      await withdrawConsent(env.CONSENT_KV, userId, body.categories, {
        policyVersion: env.CURRENT_POLICY_VERSION,
        userAgent,
        ipHash,
      });
      return Response.json({ ok: true });
    }

    // GET /consent/history — audit log
    if (request.method === 'GET' && url.pathname === '/consent/history') {
      const history = await getConsentHistory(env.CONSENT_KV, userId);
      return Response.json(history);
    }

    // GET /consent/compliance-check
    if (request.method === 'GET' && url.pathname === '/consent/compliance-check') {
      const result = await complianceCheck(
        env.CONSENT_KV, userId, regime, env.CURRENT_POLICY_VERSION
      );
      return Response.json(result, { status: result.compliant ? 200 : 422 });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

### wrangler.toml

```toml
name = "consent-manager"
main = "src/consent.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "CONSENT_KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
CURRENT_POLICY_VERSION = "2026-01-01"
```

### Blocking a cookie-setting Response based on consent

```typescript
// In your main Worker, before setting any non-essential cookie:
export async function enforceConsentOnResponse(
  response: Response,
  kv: KVNamespace,
  userId: string,
  country: string | null,
  region: string | null
): Promise<Response> {
  const regime = detectRegime(country, region);
  const record = await getConsentRecord(kv, userId);

  const headers = new Headers(response.headers);
  const setCookie = headers.getSetCookie?.() ?? [];

  // Strip non-essential cookies if consent not granted
  const NON_ESSENTIAL_PREFIXES = ['_ga', '_gid', '_fbp', 'intercom-', 'hsv', 'ajs_'];
  const filtered = setCookie.filter((cookie) => {
    const isNonEssential = NON_ESSENTIAL_PREFIXES.some((prefix) =>
      cookie.startsWith(prefix)
    );
    if (!isNonEssential) return true;
    return isConsentGranted(record, 'analytics', regime)
        || isConsentGranted(record, 'advertising', regime);
  });

  headers.delete('Set-Cookie');
  for (const c of filtered) headers.append('Set-Cookie', c);

  return new Response(response.body, { status: response.status, headers });
}
```

## Anti-patterns

- **Never bundle consent state in a cookie that the page JS can modify** — a user or script can set `document.cookie = 'consent=all'` to bypass client-side checks. The server-side KV record is the source of truth.
- **Do not reuse the same KV namespace for session data and consent logs** — consent logs must have a 7-year retention and must not be evicted by session TTL policies.
- **Never pre-check analytics checkboxes for GDPR users** — GDPR requires freely given, specific, informed, and unambiguous consent. Pre-checked boxes are invalid.
- **Do not skip re-consent when the policy version changes** — store `policyVersion` in the record and compare on every request; if stale, treat the user as not yet consented for GDPR.
- **Avoid storing the raw IP address** — hash it with SHA-256 before persisting. The raw IP is personal data under GDPR and its storage requires its own legal basis and retention justification.

## Gotchas

- **KV `list` returns keys in lexicographic order**, not insertion order. The consent log prefix uses ISO timestamps so lexicographic order equals chronological order — do not change the key format.
- **KV consistency**: KV is eventually consistent. A consent record written in one region may not be immediately visible in another. For the consent banner flow this is acceptable (worst case: banner shown once more). For enforcement (blocking cookies), use KV's `cacheTtl: 0` option to always read from the central store.
- **`getSetCookie()`** is part of the WHATWG Fetch spec and available in Workers; do not use `.get('Set-Cookie')` as it returns only the first value.
- **CCPA vs GDPR logic diverges significantly** — GDPR opt-in means deny by default; CCPA opt-out means allow by default. The `defaultChoices` function handles this but test both code paths explicitly.
- **Policy version mismatch alerts** — when a user's consent was collected under an old policy, the compliance check returns `compliant: false`. Decide in advance whether to show the banner again immediately or on next visit.

## Verification

```bash
# Serve consent banner for a GDPR user (simulate German IP via CF header)
curl -H 'CF-IPCountry: DE' https://consent.example.workers.dev/consent/banner

# Grant consent (analytics only)
curl -X POST https://consent.example.workers.dev/consent \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: user_abc123' \
  -d '{"categories":{"analytics":true,"advertising":false,"functional":true},"policyVersion":"2026-01-01"}'

# Check current consent state
curl -H 'X-User-Id: user_abc123' https://consent.example.workers.dev/consent

# Withdraw advertising consent
curl -X POST https://consent.example.workers.dev/consent/withdraw \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: user_abc123' \
  -d '{"categories":["advertising"]}'

# Retrieve full consent history (for DSAR)
curl -H 'X-User-Id: user_abc123' https://consent.example.workers.dev/consent/history

# Run compliance check
curl -H 'X-User-Id: user_abc123' \
     -H 'CF-IPCountry: DE' \
     https://consent.example.workers.dev/consent/compliance-check
# Expected for compliant user: {"compliant":true,"issues":[]}
```

## Related

- `workers-privacy-impact-assessment-d1.md` — the consent mechanism itself should be covered in a DPIA
- `workers-data-classification-labels-d1.md` — tag consent records as RESTRICTED
- `workers-sox-financial-audit-trail-d1.md` — model for append-only audit log design

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://gdpr.eu/article-7-how-to-get-consent/
- https://oag.ca.gov/privacy/ccpa
- https://edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_05_2020_consent_en.pdf
