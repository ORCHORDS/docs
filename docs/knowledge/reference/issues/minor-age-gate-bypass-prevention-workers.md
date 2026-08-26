# Preventing Minor Age-Gate Bypass via Shared Accounts and Proxies

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Age-verified sessions are being shared between adults and minors, and VPN-shifted logins
are reusing age-verification tokens from a different geographic jurisdiction, giving
underage users access to age-gated content without triggering re-verification.

## Context
Anonymous platforms face a unique bypass vector: because identity is weak, an age-verified
session cookie or JWT can be handed to a minor with no detectable account switch. Cloudflare
Workers can detect behavioral mismatches between the age-verified session's baseline
(device fingerprint, timezone, typing cadence) and the current request, then issue a silent
re-challenge via Turnstile or a hard KYC re-gate. Compliance pressure comes from the UK
Online Safety Act 2023 (age assurance duties), EU DSA recital 71 (protection of minors),
and multiple US state laws (KOSA, California AB 2273).

## Session Fingerprint Binding on Age-Verification Completion

At the moment a user completes age verification, capture a lightweight fingerprint and
store it alongside the age-verified flag in a Durable Object. Any future request that
deviates too far triggers re-challenge.

```typescript
// src/lib/age-session-fingerprint.ts
export interface AgeSessionFingerprint {
  cfCountry:   string;   // from CF-IPCountry header
  cfTimezone:  string;   // from X-Timezone header set by client JS
  uaPlatform:  string;   // User-Agent OS platform token
  screenClass:  string;  // 'mobile' | 'tablet' | 'desktop' — from Sec-CH-UA-Mobile + viewport hint
  verifiedAt:  number;   // unix seconds
}

export function extractFingerprint(req: Request): AgeSessionFingerprint {
  const ua         = req.headers.get('User-Agent') ?? '';
  const mobile     = req.headers.get('Sec-CH-UA-Mobile') === '?1';

  return {
    cfCountry:  req.headers.get('CF-IPCountry') ?? 'XX',
    cfTimezone: req.headers.get('X-Timezone')   ?? 'UTC',
    uaPlatform: parsePlatform(ua),
    screenClass: mobile ? 'mobile' : 'desktop',
    verifiedAt: Math.floor(Date.now() / 1000),
  };
}

function parsePlatform(ua: string): string {
  if (/iPhone|iPad/.test(ua))   return 'ios';
  if (/Android/.test(ua))       return 'android';
  if (/Windows/.test(ua))       return 'windows';
  if (/Mac OS X/.test(ua))      return 'macos';
  if (/Linux/.test(ua))         return 'linux';
  return 'unknown';
}

export function fingerprintMismatchScore(
  stored: AgeSessionFingerprint,
  current: Omit<AgeSessionFingerprint, 'verifiedAt'>,
): number {
  let score = 0;
  if (stored.cfCountry  !== current.cfCountry)   score += 40;  // VPN / geo shift
  if (stored.uaPlatform !== current.uaPlatform)  score += 30;  // different device class
  if (stored.screenClass !== current.screenClass) score += 20; // phone → desktop switch
  if (stored.cfTimezone !== current.cfTimezone)  score += 10;  // timezone drift
  return score;  // 0–100
}
```

## Durable Object: Age Verification State

```typescript
// src/durable-objects/AgeVerificationSession.ts
import { extractFingerprint, fingerprintMismatchScore, AgeSessionFingerprint } from '../lib/age-session-fingerprint';

export class AgeVerificationSession implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(req: Request): Promise<Response> {
    const url    = new URL(req.url);
    const action = url.searchParams.get('action');

    if (action === 'complete') {
      return this.completeVerification(req);
    }
    if (action === 'check') {
      return this.checkRequest(req);
    }
    return new Response('Not Found', { status: 404 });
  }

  private async completeVerification(req: Request): Promise<Response> {
    const fingerprint = extractFingerprint(req);
    await this.state.storage.put<AgeSessionFingerprint>('fingerprint', fingerprint);
    await this.state.storage.put('verified', true);
    return Response.json({ verified: true });
  }

  private async checkRequest(req: Request): Promise<Response> {
    const verified   = await this.state.storage.get<boolean>('verified');
    if (!verified) return Response.json({ verified: false, action: 'hard_gate' });

    const stored  = await this.state.storage.get<AgeSessionFingerprint>('fingerprint');
    if (!stored)  return Response.json({ verified: false, action: 'hard_gate' });

    const current    = extractFingerprint(req);
    const score      = fingerprintMismatchScore(stored, current);

    if (score >= 70) {
      // High confidence session sharing or device hand-off — require re-verification
      await this.state.storage.put('verified', false);
      return Response.json({ verified: false, action: 'hard_gate', mismatch_score: score });
    }
    if (score >= 30) {
      // Soft suspicion — issue a silent Turnstile challenge on next page load
      return Response.json({ verified: true, action: 'soft_challenge', mismatch_score: score });
    }
    return Response.json({ verified: true, action: 'pass' });
  }
}
```

## Age-Gate Middleware in the Main Worker

```typescript
// src/middleware/age-gate.ts
import type { Env } from '../env';

const AGE_GATED_PREFIXES = ['/content/adult/', '/live/', '/store/premium/'];

export async function ageGateMiddleware(
  req: Request,
  env: Env,
  ctx: ExecutionContext,
  next: () => Promise<Response>,
): Promise<Response> {
  const url = new URL(req.url);
  const isGated = AGE_GATED_PREFIXES.some(p => url.pathname.startsWith(p));
  if (!isGated) return next();

  const sessionToken = req.headers.get('Authorization')?.replace('Bearer ', '');
  if (!sessionToken) return ageGateResponse(url);

  // Derive DO ID from session token (HMAC-derived, not the raw token)
  const sessionId = await deriveSessionId(sessionToken, env.SESSION_SECRET);
  const doId      = env.AGE_VERIFICATION_SESSION.idFromName(sessionId);
  const stub      = env.AGE_VERIFICATION_SESSION.get(doId);

  const checkRes  = await stub.fetch(
    new Request(`https://internal/age?action=check`, { headers: req.headers }),
  );
  const { verified, action } = await checkRes.json<{ verified: boolean; action: string; mismatch_score?: number }>();

  if (!verified || action === 'hard_gate') {
    return ageGateResponse(url);
  }

  const response = await next();

  if (action === 'soft_challenge') {
    // Instruct client to show Turnstile on next navigation
    const headers = new Headers(response.headers);
    headers.set('X-Age-Recheck', 'turnstile');
    return new Response(response.body, { status: response.status, headers });
  }

  return response;
}

function ageGateResponse(url: URL): Response {
  return Response.redirect(`/verify-age?return=${encodeURIComponent(url.pathname)}`, 302);
}

async function deriveSessionId(token: string, secret: string): Promise<string> {
  const key  = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  );
  const sig  = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(token));
  return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## Anti-patterns
- Trusting a long-lived cookie as proof of age without any ongoing behavioral validation
- Flagging every country change — VPN users legitimately travel; use multi-signal scoring
- Logging the raw Turnstile token in analytics — it's a one-time-use credential
- Hard-failing on `CF-IPCountry: T1` (Tor) without offering an alternative verification path
- Using device fingerprint as the sole age signal — it is a bypass-resistance measure, not a legal basis for age assurance

## Gotchas
- `Sec-CH-UA-Mobile` requires the site to send `Accept-CH: Sec-CH-UA-Mobile` on prior response; absent that, the header is omitted and every device looks desktop
- Durable Object storage is regional — pin `AgeVerificationSession` to the user's home region if cross-region latency is a concern
- The Online Safety Act (UK) and KOSA (US) require "age assurance," not just age assertion — a checked-checkbox is not sufficient; a DO that only stores a boolean is only a first layer
- Re-challenge via Turnstile is a bot gate, not an age gate; do not conflate the two in compliance documentation
- Some jurisdictions (Germany, France) require the age-verification provider to be accredited — track which verification method was used per user in D1

## Verification

```bash
# Simulate a country shift and confirm re-gate fires
curl -H "Authorization: Bearer <token>" \
     -H "CF-IPCountry: DE" \
     -H "X-Timezone: Europe/Berlin" \
     https://platform.example/content/adult/feed
# Expected: 302 redirect to /verify-age
```

```sql
-- Audit re-gate events over the last 7 days
SELECT DATE(event_at, 'unixepoch') as day,
       action,
       COUNT(*) as count
FROM age_gate_events
WHERE event_at > unixepoch() - 604800
GROUP BY day, action
ORDER BY day DESC, count DESC;
```

## Related
- `age-verification-cloudflare-workers-kyc.md` — initial KYC-backed age verification flow
- `underage-user-detection-behavioral-signals.md` — behavioral signals that a user may be underage
- `ban-evasion-device-fingerprint-detection-d1.md` — fingerprint techniques also used for ban evasion
- `vpn-proxy-detection-geo-restrictions.md` — detecting VPN use for geographic bypasses

## Sources
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/turnstile/
- https://www.legislation.gov.uk/ukpga/2023/50/contents (Online Safety Act 2023)
- https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202120220AB2273 (CAADCA)
- https://www.congress.gov/bill/118th-congress/senate-bill/1409 (KOSA)
