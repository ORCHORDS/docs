# Device Fingerprinting and Session Management with Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to bind authenticated sessions to the device that created them, detect when a session is accessed from an anomalous device (potential token theft), and do so without storing PII-heavy fingerprint data — all at the edge with sub-millisecond overhead.

## Context

Traditional session fixation and hijacking defences rely on IP binding, which is unreliable on mobile (IP changes on network switch). A privacy-safe passive fingerprint — derived from HTTP request headers that never leave the Worker — provides a stable, non-PII device signal that can be hashed and stored alongside the session in KV.

The approach:
1. Extract passive signals available on every request (no JS required).
2. Hash them into a short fingerprint identifier.
3. Store fingerprint hash alongside the session in KV.
4. On each subsequent request, recompute the hash and compare — flag or invalidate on mismatch.

## Solution

### 1. Wrangler Bindings

```toml
[[kv_namespaces]]
binding = "SESSIONS"
id      = "<your-kv-namespace-id>"

[vars]
FINGERPRINT_HMAC_SECRET_NAME = "FINGERPRINT_HMAC_SECRET"  # stored as a Worker secret
# wrangler secret put FINGERPRINT_HMAC_SECRET
```

### 2. TypeScript Types

```typescript
// src/types.ts
export interface Env {
  SESSIONS:                  KVNamespace;
  FINGERPRINT_HMAC_SECRET:   string;  // raw hex secret, 32 bytes
}

export interface SessionRecord {
  sessionId:        string;
  userId:           string;
  fingerprintHash:  string;   // HMAC-SHA256 of passive signals
  createdAt:        number;
  lastSeenAt:       number;
  anomalyCount:     number;
  ipCidr:           string;   // /24 block only — not full IP
}

export interface FingerprintSignals {
  acceptLanguage:   string;
  acceptEncoding:   string;
  platform:         string;   // extracted from Sec-CH-UA-Platform
  mobile:           boolean;  // Sec-CH-UA-Mobile
  uaBrand:          string;   // leading brand token from Sec-CH-UA
  colorScheme:      string;   // Sec-CH-Prefers-Color-Scheme
  timezone:         string;   // Sec-CH-Timezone (if sent)
  connectionType:   string;   // ECT from Network Information
}
```

### 3. Passive Signal Extraction

```typescript
// src/fingerprint.ts
import type { FingerprintSignals } from './types';

export function extractSignals(request: Request): FingerprintSignals {
  // Normalise Accept-Language to language tags only (strip quality weights)
  const acceptLanguage = (request.headers.get('Accept-Language') ?? '')
    .split(',')
    .map(l => l.split(';')[0].trim().toLowerCase())
    .slice(0, 3)    // top 3 preferences only
    .join(',');

  const acceptEncoding = (request.headers.get('Accept-Encoding') ?? '')
    .split(',')
    .map(e => e.split(';')[0].trim().toLowerCase())
    .sort()         // sort for stability across UA changes
    .join(',');

  // Client Hints (available when page sends Accept-CH response)
  const platform   = request.headers.get('Sec-CH-UA-Platform')?.replace(/"/g, '') ?? 'unknown';
  const mobileHint = request.headers.get('Sec-CH-UA-Mobile') ?? '?0';
  const mobile     = mobileHint === '?1';

  // Extract first non-"Not A Brand" brand from Sec-CH-UA
  const uaHeader  = request.headers.get('Sec-CH-UA') ?? '';
  const uaBrand   = extractLeadingBrand(uaHeader);

  const colorScheme  = request.headers.get('Sec-CH-Prefers-Color-Scheme') ?? 'unknown';
  const timezone     = request.headers.get('Sec-CH-Timezone')             ?? 'unknown';
  const connectionType = request.headers.get('ECT')                       ?? 'unknown';

  return { acceptLanguage, acceptEncoding, platform, mobile, uaBrand, colorScheme, timezone, connectionType };
}

function extractLeadingBrand(secCHUA: string): string {
  // Sec-CH-UA: "Not)A;Brand";v="99", "Chromium";v="127", "Google Chrome";v="127"
  const tokens = secCHUA.split(',').map(t => t.trim());
  for (const token of tokens) {
    const name = token.split(';')[0].replace(/"/g, '').trim();
    if (!name.includes('Not') && !name.includes('Brand') && name.length > 0) {
      return name.toLowerCase();
    }
  }
  return 'unknown';
}
```

### 4. Fingerprint Hashing with HMAC-SHA256

```typescript
// src/fingerprint.ts (continued)
import type { FingerprintSignals, Env } from './types';

export async function hashFingerprint(
  signals: FingerprintSignals,
  hmacSecret: string,
): Promise<string> {
  // Canonical serialisation — alphabetical key order for stability
  const canonical = JSON.stringify({
    ae:  signals.acceptEncoding,
    al:  signals.acceptLanguage,
    brand: signals.uaBrand,
    cs:  signals.colorScheme,
    ct:  signals.connectionType,
    mob: signals.mobile,
    pf:  signals.platform,
    tz:  signals.timezone,
  });

  const secretBytes = hexToBytes(hmacSecret);
  const key = await crypto.subtle.importKey(
    'raw',
    secretBytes,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );

  const sig = await crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(canonical),
  );

  // Return first 16 bytes as hex (128-bit fingerprint)
  return Array.from(new Uint8Array(sig).slice(0, 16))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}
```

### 5. Session Creation

```typescript
// src/session.ts
import type { Env, SessionRecord } from './types';
import { extractSignals, hashFingerprint } from './fingerprint';

export async function createSession(
  request: Request,
  env: Env,
  userId: string,
): Promise<{ sessionId: string; cookieValue: string }> {
  const sessionId = crypto.randomUUID();
  const signals   = extractSignals(request);
  const fpHash    = await hashFingerprint(signals, env.FINGERPRINT_HMAC_SECRET);

  // Store only the /24 CIDR, not the full IP
  const ip     = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
  const ipCidr = ipToCidr24(ip);

  const record: SessionRecord = {
    sessionId,
    userId,
    fingerprintHash: fpHash,
    createdAt:       Date.now(),
    lastSeenAt:      Date.now(),
    anomalyCount:    0,
    ipCidr,
  };

  await env.SESSIONS.put(
    `sess:${sessionId}`,
    JSON.stringify(record),
    { expirationTtl: 60 * 60 * 24 * 30 }, // 30-day session lifetime
  );

  // Return a signed session token (bare UUID here; sign with HMAC in production)
  return { sessionId, cookieValue: `sid=${sessionId}; HttpOnly; Secure; SameSite=Lax; Path=/` };
}

function ipToCidr24(ip: string): string {
  const parts = ip.split('.');
  if (parts.length !== 4) return ip; // IPv6 — store as-is
  return `${parts[0]}.${parts[1]}.${parts[2]}.0/24`;
}
```

### 6. Session Validation and Anomaly Detection

```typescript
// src/session.ts (continued)
export type SessionCheckResult =
  | { ok: true;  record: SessionRecord }
  | { ok: false; reason: 'not_found' | 'expired' | 'anomaly' };

export async function validateSession(
  request: Request,
  env: Env,
  sessionId: string,
): Promise<SessionCheckResult> {
  const raw = await env.SESSIONS.get(`sess:${sessionId}`);
  if (!raw) return { ok: false, reason: 'not_found' };

  const record = JSON.parse(raw) as SessionRecord;

  // Recompute fingerprint
  const signals    = extractSignals(request);
  const currentFp  = await hashFingerprint(signals, env.FINGERPRINT_HMAC_SECRET);

  if (currentFp !== record.fingerprintHash) {
    record.anomalyCount++;

    if (record.anomalyCount >= 3) {
      // Three consecutive anomalies — invalidate session
      await env.SESSIONS.delete(`sess:${sessionId}`);
      console.warn(`Session ${sessionId} invalidated after 3 fingerprint anomalies`);
      return { ok: false, reason: 'anomaly' };
    }

    // Soft anomaly — allow but log and increment counter
    await env.SESSIONS.put(`sess:${sessionId}`, JSON.stringify(record), {
      expirationTtl: 60 * 60 * 24 * 30,
    });

    // Still return ok — let the app decide whether to step up auth
    return { ok: true, record };
  }

  // Happy path — refresh TTL and update lastSeenAt
  record.lastSeenAt  = Date.now();
  record.anomalyCount = 0; // Reset on clean check
  await env.SESSIONS.put(`sess:${sessionId}`, JSON.stringify(record), {
    expirationTtl: 60 * 60 * 24 * 30,
  });

  return { ok: true, record };
}
```

### 7. Worker Entry Point

```typescript
// src/index.ts
import type { Env } from './types';
import { createSession, validateSession } from './session';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/auth/login' && request.method === 'POST') {
      const { userId } = await request.json<{ userId: string }>();
      const { sessionId, cookieValue } = await createSession(request, env, userId);
      return new Response(JSON.stringify({ sessionId }), {
        headers: {
          'Content-Type': 'application/json',
          'Set-Cookie':   cookieValue,
        },
      });
    }

    // All other routes: validate session
    const cookie    = request.headers.get('Cookie') ?? '';
    const sessionId = parseCookie(cookie, 'sid');

    if (!sessionId) return new Response('Unauthorised', { status: 401 });

    const result = await validateSession(request, env, sessionId);
    if (!result.ok) {
      return new Response(
        JSON.stringify({ error: result.reason }),
        { status: 401, headers: { 'Content-Type': 'application/json' } },
      );
    }

    // Downstream handler receives validated session info via a header
    const downstreamRequest = new Request(request, {
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        'X-User-Id':    result.record.userId,
        'X-Session-Id': result.record.sessionId,
        'X-Anomaly':    String(result.record.anomalyCount > 0),
      }),
    });

    // Pass to origin or next middleware
    return fetch(downstreamRequest);
  },
};

function parseCookie(cookieHeader: string, name: string): string | null {
  const entry = cookieHeader.split(';').find(c => c.trim().startsWith(`${name}=`));
  return entry ? entry.trim().slice(name.length + 1) : null;
}
```

## Implementation Details

- **HMAC over plain hash**: Using HMAC-SHA256 with a server secret ensures that even if an attacker knows the fingerprint algorithm, they cannot forge a valid hash without the secret key. Rotate the secret to invalidate all sessions if the key is compromised.
- **128-bit truncation**: Storing the first 16 bytes of the HMAC output (32 hex chars) is sufficient for collision resistance across billions of sessions (birthday bound is 2^64).
- **Soft anomaly threshold**: A single fingerprint change (network switch, OS upgrade) should not immediately terminate a session. The threshold of 3 consecutive anomalies balances security with usability. Tune based on your user base's mobility patterns.
- **`/24` CIDR storage**: Storing only the `/24` block of the connecting IP is a privacy-preserving alternative to full IP binding. It catches subnet-level anomalies without persisting a unique IP that could identify an individual under GDPR.
- **KV TTL refresh**: Each successful validation resets the KV `expirationTtl` to 30 days, implementing a rolling session window. Sessions expire 30 days after last activity.
- **Client Hints acceptance**: Send `Accept-CH: Sec-CH-UA, Sec-CH-UA-Mobile, Sec-CH-UA-Platform, Sec-CH-Prefers-Color-Scheme, Sec-CH-Timezone` in your first response. These are low-entropy hints that browsers send freely.

## Anti-patterns

- **Do not** store the raw User-Agent string in KV — it changes with browser updates and is unnecessarily verbose. The HMAC hash of signals is sufficient.
- **Do not** use `CF-Connecting-IP` as the primary fingerprint signal — mobile IPs change constantly. Use it only for coarse anomaly detection as done here.
- **Do not** immediately invalidate on the first fingerprint mismatch — legitimate users change networks constantly (home Wi-Fi to cellular).
- **Do not** log raw fingerprint signals — they can contain quasi-PII (language preferences, timezone). Log only the hash.
- **Do not** use the session cookie value as the KV key directly without prefixing (`sess:`) — it prevents accidental collisions with other KV data and allows future namespacing.

## Gotchas

- `Sec-CH-UA-*` headers are only sent on HTTPS and only after the server has sent `Accept-CH`. The first request to a new origin will not carry these headers — fall back gracefully.
- iOS Safari does not support most Client Hints. The fingerprint for iOS users will be based primarily on `Accept-Language` and `Accept-Encoding`, which is coarser but still useful.
- KV `get` on a non-existent key returns `null` — never `undefined`. Always check for `null`.
- If the Worker handles multiple tenants, prefix the session key with the tenant ID: `sess:{tenantId}:{sessionId}` to prevent cross-tenant session collisions.
- The `crypto.randomUUID()` function is available in Workers without imports and produces RFC 4122 v4 UUIDs.

## Verification

1. POST `/auth/login` with a userId — confirm the `Set-Cookie` header contains `sid=<uuid>; HttpOnly; Secure`.
2. GET any protected route with the session cookie — confirm `X-User-Id` is forwarded correctly.
3. Simulate a fingerprint change: alter the `Accept-Language` header and resend 3 times — confirm the session is deleted from KV on the third anomaly.
4. Verify KV entry: `wrangler kv:key get --namespace-id=<id> sess:<sessionId>` — confirm `anomalyCount` increments on mismatch.
5. Verify the KV TTL resets: check `expirationTtl` in the KV entry metadata after a successful validation.

## Related

- `workers-offline-sync-conflict-resolution.md` — device ID derived from the same session for vector clocks
- `workers-web-push-vapid-notifications.md` — push subscription associated with the session record
- Cloudflare Workers KV docs: https://developers.cloudflare.com/kv/
- Client Hints spec: https://www.w3.org/TR/client-hints-infrastructure/

## Sources

- IETF RFC 6265 — HTTP State Management Mechanism (cookies)
- W3C Client Hints Infrastructure specification
- OWASP Session Management Cheat Sheet
- Cloudflare Workers KV Workers Binding API documentation
- GDPR Article 4 — definition of personal data (fingerprint hashing rationale)
