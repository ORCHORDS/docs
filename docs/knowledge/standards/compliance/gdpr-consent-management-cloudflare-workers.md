# GDPR Consent Management on Cloudflare Workers — TCF 2.0 at the Edge

**Project:** example project (example.com) — 21+ anonymous social platform
**Author:** example.com
**Scope:** EU/US users, Cloudflare Workers, KV consent store, mobile UX
**Last reviewed:** 2025-08

---

## 1. Overview

GDPR Article 7 and Recital 32 require that consent be freely given, specific, informed, and unambiguous.
For a platform serving EU users, this obligation extends to every processing operation that relies on
consent as its lawful basis — including analytics, personalised content, and third-party integrations.

The IAB Europe Transparency and Consent Framework (TCF) 2.0 / 2.2 provides a standardised consent
string format that encodes which vendors and purposes a user has consented to. Parsing and enforcing
that string at the Cloudflare edge — before any response reaches the browser — eliminates a class of
compliance risk where JavaScript-dependent consent checks fire too late or not at all.

This article covers:
- TCF 2.0 consent string structure and edge parsing
- Cloudflare Geo for per-country consent UX
- KV as a distributed consent record store
- Mobile consent banner timing and UX hardening

---

## 2. TCF 2.0 Consent String Structure

A TCF 2.0 consent string is a URL-safe base64-encoded bit-field sequence. The first 6 bits encode the
segment type (0 = Core String). Key fields within the Core String:

| Field              | Bits  | Description                                      |
|--------------------|-------|--------------------------------------------------|
| Version            | 6     | TCF version (2 = v2.0)                           |
| Created            | 36    | Epoch deciseconds of first consent creation      |
| LastUpdated        | 36    | Epoch deciseconds of last update                 |
| CmpId              | 12    | CMP registered ID                                |
| CmpVersion         | 12    | CMP software version                             |
| ConsentScreen      | 6     | Screen number on which consent was given         |
| ConsentLanguage    | 12    | Two-letter ISO 639-1 language code               |
| VendorListVersion  | 12    | GVL version at time of consent                   |
| TcfPolicyVersion   | 6     | Policy version (4 for TCF 2.2)                   |
| PurposesConsent    | 24    | Bit-field; bit N = consent to Purpose N          |
| VendorConsent      | var   | Range-encoded or bitfield vendor consent list    |

For example project the relevant purposes are typically Purpose 1 (store/access information on device),
Purpose 3 (create personalised ads profile), and Purpose 9 (apply market research).

---

## 3. Edge Parsing in a Cloudflare Worker

Install the `@iabtcf/core` package or use a lightweight hand-rolled parser. At the edge, avoid
loading the full 200 KB GVL on every request — cache it in KV with a 1-hour TTL.

```typescript
// workers/consent-gate.ts
import { TCString, CmpApiModel } from '@iabtcf/core';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const tcString = getCookie(request, 'euconsent-v2');

    if (!tcString) {
      return enforcementResponse(request, env, 'no-consent-string');
    }

    let tc: CmpApiModel;
    try {
      tc = TCString.decode(tcString);
    } catch {
      return enforcementResponse(request, env, 'invalid-consent-string');
    }

    // Enforce Purpose 1 (store/access on device) — mandatory for session cookies
    if (!tc.purposeConsents.has(1)) {
      return enforcementResponse(request, env, 'purpose-1-denied');
    }

    // Forward with consent metadata header for downstream Workers
    const req2 = new Request(request);
    req2.headers.set('X-Consent-Purposes', serializePurposes(tc.purposeConsents));
    req2.headers.set('X-Consent-Version', String(tc.version));

    return fetch(req2);
  },
};

function getCookie(req: Request, name: string): string | null {
  const header = req.headers.get('cookie') ?? '';
  const match = header.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function serializePurposes(map: { has(n: number): boolean }): string {
  return Array.from({ length: 24 }, (_, i) => (map.has(i + 1) ? '1' : '0')).join('');
}

function enforcementResponse(req: Request, env: Env, reason: string): Response {
  // Redirect to consent collection page, preserving return URL
  const url = new URL(req.url);
  const redirect = new URL(env.CONSENT_GATE_URL);
  redirect.searchParams.set('return', url.pathname + url.search);
  redirect.searchParams.set('reason', reason);
  return Response.redirect(redirect.toString(), 302);
}
```

### Wrangler binding

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "CONSENT_KV"
id     = "<your-kv-namespace-id>"

[vars]
CONSENT_GATE_URL = "https://example.com/consent"
```

---

## 4. Per-Country Consent UX via Cloudflare Geo

Not all countries require the same consent UI. EEA countries (EU + Norway, Iceland, Liechtenstein)
require full TCF-compliant consent. Switzerland requires consent under nFADP. UK users fall under
UK GDPR / PECR. US states (CA, CO, CT, VA) use opt-out models, not opt-in.

Cloudflare provides `request.cf.country` in every Worker invocation at no additional cost.

```typescript
function consentRegime(request: Request): 'eea' | 'uk' | 'us-opt-out' | 'none' {
  const country = (request as any).cf?.country as string | undefined;
  if (!country) return 'eea'; // fail-safe: treat unknown as most-restrictive

  const EEA = new Set([
    'AT','BE','BG','HR','CY','CZ','DK','EE','FI','FR','DE','GR','HU',
    'IE','IT','LV','LT','LU','MT','NL','PL','PT','RO','SK','SI','ES',
    'SE','NO','IS','LI',
  ]);
  const US_OPT_OUT = new Set(['US']); // California CCPA/CPRA, etc.

  if (EEA.has(country)) return 'eea';
  if (country === 'GB') return 'uk';
  if (US_OPT_OUT.has(country)) return 'us-opt-out';
  return 'none';
}
```

Use this function early in your Worker chain to serve the correct banner variant:

| Regime       | Banner type             | Opt-in required | IAB TCF |
|--------------|-------------------------|-----------------|---------|
| `eea`        | Full CMP modal          | Yes             | Yes     |
| `uk`         | UK CMP (PECR-compliant) | Yes             | Optional|
| `us-opt-out` | GPC / opt-out banner    | No              | No      |
| `none`       | No banner               | No              | No      |

---

## 5. KV Consent Record Store

Store server-side consent records in Cloudflare KV so that backend Workers can enforce consent
without relying on the browser cookie. This is required when processing occurs in Workers that
receive API calls (e.g., from mobile apps that may not forward cookies).

### Key schema

```
consent:{userId}          → ConsentRecord (JSON)
consent:session:{sid}     → ConsentRecord (JSON, TTL = session lifetime)
```

### ConsentRecord shape

```typescript
interface ConsentRecord {
  userId:          string;          // hashed / pseudonymous
  tcString:        string;          // raw TCF string
  regime:          string;          // 'eea' | 'uk' | 'us-opt-out'
  purposes:        number[];        // consented purpose IDs
  vendors:         number[];        // consented vendor IDs
  gpc:             boolean;         // Global Privacy Control signal received
  recordedAt:      string;          // ISO 8601
  expiresAt:       string;          // ISO 8601 — max 13 months (GDPR Recital 32)
  ipCountry:       string;          // cf.country at time of recording
  userAgent:       string;          // UA at time of recording
  version:         number;          // TCF version
}
```

### Write path (consent collection Worker)

```typescript
async function recordConsent(env: Env, record: ConsentRecord): Promise<void> {
  const key = `consent:${record.userId}`;
  const ttlSeconds = Math.floor(
    (new Date(record.expiresAt).getTime() - Date.now()) / 1000
  );
  await env.CONSENT_KV.put(key, JSON.stringify(record), {
    expirationTtl: Math.max(ttlSeconds, 60),
  });
}
```

### Read path (enforcement Worker)

```typescript
async function hasConsent(env: Env, userId: string, purposeId: number): Promise<boolean> {
  const raw = await env.CONSENT_KV.get(`consent:${userId}`);
  if (!raw) return false;
  const record: ConsentRecord = JSON.parse(raw);
  if (new Date(record.expiresAt) < new Date()) return false;
  return record.purposes.includes(purposeId);
}
```

---

## 6. Mobile Cookie Consent Banner Timing

Mobile apps accessing example.com via WebView or native API calls face a different timing challenge
than desktop browsers. Key considerations:

### 6.1 WebView timing

In-app WebViews must fire the consent banner **before** any tracking scripts load. Use the
`document.addEventListener('DOMContentLoaded', ...)` hook to inject the CMP before analytics
scripts are parsed.

Avoid loading analytics tags in `<head>` unconditionally. Use a tag manager stub that reads the
`euconsent-v2` cookie before firing any vendor pixels:

```html
<!-- Stub loader: fires BEFORE any vendor tags -->
<script>
  (function() {
    var tc = document.cookie.match(/euconsent-v2=([^;]+)/);
    window.__tcfapi = window.__tcfapi || function(cmd, ver, cb) {
      if (cmd === 'getTCData') cb({ tcString: tc ? tc[1] : '' }, true);
    };
  })();
</script>
```

### 6.2 Native app SDK → API calls

When the native iOS/Android app calls the example.com API, it must pass the `euconsent-v2` value
as a request header (`X-TC-String`) so the edge Worker can enforce it server-side without cookies.

### 6.3 Banner re-display rules

Per TCF 2.2 Policy (Section 3.1):
- Re-display the banner if the GVL version has changed since last consent.
- Re-display if the user's consent is older than 13 months.
- Re-display if the user previously denied all and attempts an action requiring consent.

```typescript
function shouldRefreshConsent(record: ConsentRecord, currentGvlVersion: number): boolean {
  const age = Date.now() - new Date(record.recordedAt).getTime();
  const thirteenMonths = 13 * 30 * 24 * 60 * 60 * 1000;
  return age > thirteenMonths; // GVL version check handled separately
}
```

### 6.4 Interaction timeout

Mobile users often abandon the consent modal. Do not auto-close and assume consent. If the user
dismisses without choosing, treat as rejection for Purpose 1 (no cookies) and redirect to
consent-required gate on any action that requires a session.

---

## 7. Audit and Record-Keeping

GDPR Article 7(1) requires the controller to demonstrate that valid consent was obtained.

Maintain an append-only consent audit log. Write every consent event to a D1 table:

```sql
CREATE TABLE consent_audit (
  id            TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id       TEXT    NOT NULL,
  event_type    TEXT    NOT NULL,  -- 'granted' | 'withdrawn' | 'expired' | 'refreshed'
  purposes      TEXT    NOT NULL,  -- JSON array of purpose IDs
  tc_string     TEXT    NOT NULL,
  ip_country    TEXT    NOT NULL,
  user_agent    TEXT    NOT NULL,
  recorded_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  kv_key        TEXT                -- KV key for cross-reference
);
```

Never delete rows from this table — they constitute proof of consent.
Withdrawal events do not remove prior grant rows; they add a new `withdrawn` row.

---

## 8. Checklist

- [ ] TCF 2.2 CMP registered with IAB Europe
- [ ] Consent string parsed at edge Worker before any vendor tag fires
- [ ] Per-country regime detection via `request.cf.country`
- [ ] KV consent store with max 13-month TTL
- [ ] Server-side consent re-check for mobile API calls via `X-TC-String` header
- [ ] D1 audit log for every consent grant/withdrawal event
- [ ] GVL cache in KV (1-hour TTL, fallback to last known)
- [ ] Banner re-display logic for expired or stale consent
- [ ] Mobile WebView: CMP fires before DOMContentLoaded vendor tags
- [ ] GPC signal detected and stored in consent record

---

## 9. References

- GDPR Articles 6, 7, 13, 17; Recitals 32, 43, 171
- IAB Europe TCF 2.2 Technical Specification (2023)
- IAB Europe TCF Policy v2.2 (2023)
- EDPB Guidelines 05/2020 on Consent
- Cloudflare Workers KV API documentation
- Cloudflare `request.cf` object reference
- ePrivacy Directive 2002/58/EC (Cookie Law)
- UK ICO Guidance on Cookies and Similar Technologies (2023)
