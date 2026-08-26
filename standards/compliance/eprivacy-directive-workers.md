# ePrivacy Directive Compliance on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your platform serves EU/EEA users and must comply with the ePrivacy Directive (2002/58/EC as amended by 2009/136/EC) for cookies, tracking pixels, electronic direct marketing, and confidentiality of communications — independently of GDPR consent records.

## Context

The ePrivacy Directive (ePD) establishes *lex specialis* rules on top of GDPR for electronic communications: prior informed consent is required for non-essential cookies (Art. 5(3)), unsolicited direct marketing (Art. 13), and access to terminal equipment. National implementations vary (UK PECR, German TTDSG, French Loi Informatique et Libertés), but all share opt-in consent for analytics/tracking cookies and opt-out rights for marketing. Workers sit between CDN and origin — the ideal enforcement layer for cookie gating, consent state injection, and marketing suppression.

---

## 1. Cookie Categorisation and Consent Gate

On every HTML response, classify cookies set by origin and strip non-consented tracking cookies before delivery.

```typescript
// src/eprivacy-cookie-gate.ts
const ESSENTIAL_PREFIXES = ['session_', 'csrf_', 'auth_', '__Secure-'];
const ANALYTICS_COOKIES = ['_ga', '_gid', '_fbp', '_gcl_au', 'amplitude_id'];
const MARKETING_COOKIES = ['_fbp', 'IDE', 'DSID', 'fr', 'tr'];

function isEssential(name: string): boolean {
  return ESSENTIAL_PREFIXES.some(p => name.startsWith(p));
}

export function stripNonConsentedCookies(
  response: Response,
  consentCategories: Set<string>   // e.g. {'essential', 'analytics'}
): Response {
  const headers = new Headers(response.headers);
  const setCookies = headers.getSetCookie?.() ?? [];
  // Remove old header; rebuild with only consented cookies
  headers.delete('Set-Cookie');
  for (const cookie of setCookies) {
    const name = cookie.split('=')[0].trim();
    if (isEssential(name)) { headers.append('Set-Cookie', cookie); continue; }
    if (ANALYTICS_COOKIES.includes(name) && consentCategories.has('analytics')) {
      headers.append('Set-Cookie', cookie); continue;
    }
    if (MARKETING_COOKIES.includes(name) && consentCategories.has('marketing')) {
      headers.append('Set-Cookie', cookie);
    }
    // else: drop the cookie — ePrivacy Art. 5(3)
  }
  return new Response(response.body, { status: response.status, headers });
}
```

---

## 2. Consent State Resolution from KV

Read per-user consent records stored by your CMP; resolve categories before the cookie gate runs.

```typescript
// src/consent-resolver.ts
interface ConsentRecord {
  userId: string;
  categories: string[];   // ['essential', 'analytics', 'marketing']
  consentedAt: string;
  expiresAt: string;
  iabTcString?: string;
}

export async function resolveConsent(
  kv: KVNamespace,
  userId: string
): Promise<Set<string>> {
  const raw = await kv.get(`consent:${userId}`, { type: 'json' }) as ConsentRecord | null;
  if (!raw || new Date(raw.expiresAt) < new Date()) {
    return new Set(['essential']); // default: essential-only
  }
  return new Set(raw.categories);
}

export async function storeConsent(
  kv: KVNamespace,
  record: ConsentRecord
): Promise<void> {
  // Consent records must be retained as evidence — 13-month TTL matches GA4 consent window
  const ttl = 13 * 30 * 86400;
  await kv.put(`consent:${record.userId}`, JSON.stringify(record), {
    expirationTtl: ttl,
    metadata: { legalBasis: 'ePrivacy-Art5(3)', consentedAt: record.consentedAt }
  });
}
```

---

## 3. Tracking Pixel Blocking (Art. 5(3) Terminal Equipment)

Third-party tracking pixels (1×1 image beacons) are covered by Art. 5(3). Intercept and replace with a transparent stub when consent is absent.

```typescript
// src/pixel-blocker.ts
const TRACKING_PIXEL_HOSTS = [
  'pixel.facebook.com', 'px.ads.linkedin.com',
  'analytics.twitter.com', 'cm.g.doubleclick.net'
];

const TRANSPARENT_1X1 =
  'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

export async function blockTrackingPixels(request: Request): Promise<Response | null> {
  const url = new URL(request.url);
  if (TRACKING_PIXEL_HOSTS.some(h => url.hostname.endsWith(h))) {
    // Check consent header injected upstream
    const consent = request.headers.get('X-Consent-Categories') ?? 'essential';
    if (!consent.includes('marketing')) {
      return new Response(
        Buffer.from(TRANSPARENT_1X1.split(',')[1], 'base64'),
        { status: 200, headers: { 'Content-Type': 'image/gif', 'Cache-Control': 'no-store' } }
      );
    }
  }
  return null;
}
```

---

## 4. Unsolicited Direct Marketing Suppression (Art. 13)

Before any email or SMS dispatch, verify the recipient has opted in or is covered by the "soft opt-in" exemption (existing customer, similar products).

```typescript
// src/marketing-suppression.ts
interface SuppressionRecord { email: string; optedOutAt: string; channel: 'email' | 'sms' }

export async function checkMarketingSuppression(
  db: D1Database,
  email: string,
  channel: 'email' | 'sms'
): Promise<boolean> {
  const row = await db.prepare(`
    SELECT opted_out_at FROM marketing_suppression
    WHERE email = ? AND channel = ? LIMIT 1
  `).bind(email.toLowerCase(), channel).first<{ opted_out_at: string }>();
  return row !== null; // true = suppressed, do not send
}

export async function recordOptOut(
  db: D1Database,
  email: string,
  channel: 'email' | 'sms'
): Promise<void> {
  await db.prepare(`
    INSERT OR REPLACE INTO marketing_suppression (email, channel, opted_out_at)
    VALUES (?, ?, ?)
  `).bind(email.toLowerCase(), channel, new Date().toISOString()).run();
}
```

---

## 5. Consent Audit Log for Regulatory Evidence

DPAs require evidence of valid consent. Log every consent grant/withdrawal with the full signal.

```typescript
// src/consent-audit.ts
export async function logConsentEvent(
  db: D1Database,
  event: {
    userId: string;
    eventType: 'grant' | 'withdraw' | 'expire';
    categories: string[];
    tcString?: string;
    userAgent: string;
    ip: string;
    at: string;
  }
): Promise<void> {
  await db.prepare(`
    INSERT INTO consent_audit_log
      (user_id, event_type, categories, tc_string, user_agent, ip_hash, occurred_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).bind(
    event.userId,
    event.eventType,
    JSON.stringify(event.categories),
    event.tcString ?? null,
    event.userAgent,
    // Hash IP for GDPR pseudonymisation; retain consent record separately
    await hashIp(event.ip),
    event.at
  ).run();
}

async function hashIp(ip: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(ip));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

---

## Anti-patterns

- **Treating ePrivacy as a subset of GDPR** — ePD Art. 5(3) consent is a *separate* legal requirement; GDPR legitimate interest cannot substitute for it.
- **Reading cookies before consent is confirmed** — even reading (not just writing) local storage for non-essential purposes requires prior consent under the CJEU Planet49 judgment.
- **Soft opt-in without meeting all conditions** — the B2C soft opt-in exemption (UK PECR Reg. 22) requires: prior customer relationship, marketing of *own* similar products, opt-out offered at point of collection, and in every subsequent message.
- **Blocking the consent check on the critical path** — use `waitUntil()` for audit logging; consent resolution must be async and fast.

---

## Gotchas

- `headers.getSetCookie()` is available in Workers with compatibility_date ≥ 2023-03-01; on older runtimes iterate `response.headers.entries()` filtering for `set-cookie`.
- The ePrivacy Regulation (draft replacement for ePD) remains in trilogue as of 2026 — national ePD implementations are still in force.
- "Consent" under Art. 5(3) must meet GDPR Art. 7 standards: freely given, specific, informed, unambiguous affirmative action — pre-ticked boxes are invalid.
- German TTDSG § 25 and French CNIL guidance have additional specificity requirements — test national DPA guidance separately.

---

## Verification

```bash
# Verify analytics cookie stripped when no consent
curl -c /tmp/cookies.txt -b "uid=test123" https://example.com/ \
  | grep -i 'set-cookie' | grep '_ga'

# Check suppression record
wrangler d1 execute DB --command \
  "SELECT * FROM marketing_suppression WHERE email='user@example.com'"

# Inspect consent audit for a user
wrangler d1 execute DB --command \
  "SELECT event_type, categories, occurred_at FROM consent_audit_log
   WHERE user_id='test123' ORDER BY occurred_at DESC LIMIT 10"
```

---

## Related

- `cookie-consent-cloudflare-pages-workers.md`
- `cookie-consent-management-platform.md`
- `tcf-2-2-consent-string-parsing-enforcement.md`
- `gdpr-consent-management-cloudflare-workers.md`
- `gdpr-lawful-basis-workers-d1-consent.md`

---

## Sources

- ePrivacy Directive 2002/58/EC (as amended) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32002L0058
- CJEU Planet49 judgment C-673/17 — https://curia.europa.eu/juris/document/document.jsf?docid=218462
- UK PECR — https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/
- German TTDSG — https://www.gesetze-im-internet.de/ttdsg/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
