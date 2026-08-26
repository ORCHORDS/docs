# Repeat Offender Detection Across Anonymous Sessions (Privacy-Preserving)
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project is an anonymous social platform — users hold no persistent account tied to PII by design.
When a session is banned or suspended for policy violations, a repeat offender simply refreshes their
session token and reconnects, bypassing all enforcement history. Over time, the same bad actor
accumulates dozens of disposable sessions while continuing to post prohibited content, harass other
users, or attempt to circumvent age-gating.

The challenge: re-identify repeat offenders across sessions without storing PII, without creating
linkable pseudonymous profiles that regulators could classify as tracking, and without introducing
latency on the hot path of every request.

---

## Context

example project sessions are intentionally short-lived (8-hour TTL, renewed with Turnstile proof-of-work).
Users may optionally link a Solana wallet to unlock premium features, but the majority remain
fully anonymous. There is no email, phone, or device account — by design.

Privacy model constraints:
- **GDPR Article 5(1)(b)**: data collected for enforcement (ban evasion detection) must not be
  repurposed for behavioral profiling or advertising.
- **GDPR Article 25**: privacy-by-design requires minimizing the identifying power of any
  stored signal.
- **EU DSA Article 17**: automated account suspension must carry a human-reviewable reason code.
- **ePrivacy Directive**: browser fingerprinting constitutes consent-required processing in the EU.

The privacy-preserving approach: store *hashed device signal bundles* in D1, never raw signals.
A returning offender produces the same hash deterministically, linking them to their ban history
without the platform ever holding a reversible identifier.

---

## Section 1 — Signal Bundle Design

The device signal bundle is a deterministic hash of signals that a real browser provides on every
request, which a bad actor cannot trivially change between sessions without significant friction.

**Tier 1 — Network signals (no consent required under ePrivacy; not PII on their own):**
- CF ASN + /24 subnet prefix (not full IP)
- CF datacenter code (`cf.colo`)
- `cf.botManagement.ja4` (TLS client fingerprint — Cloudflare Bot Management feature)

**Tier 2 — Passive browser signals (present in headers, no JS required):**
- `Accept-Language` header (normalized to language tag only, not full locale string)
- `User-Agent` parsed to: engine family + major version + OS family (never the raw UA string)
- `Accept-Encoding` header value

**Tier 3 — Active JS signals (require Turnstile JS loaded; treated as consent-gated):**
- Canvas fingerprint hash (computed client-side, sent as a commitment)
- Screen resolution bucket (480p / 720p / 1080p / 4K — not exact dimensions)
- Timezone offset bucket (±1h granularity)

**Bundle assembly:**

```
BundleInput = ASN + "/24" + "|" + JA4 + "|" + LangFamily + "|" + UAFamily + "|" + UAMajor
BundleHash  = HMAC-SHA256(BundleInput, SITE_SECRET_KEY)  // truncated to 128 bits
```

Using HMAC with a site-level secret means that even if D1 is compromised, the hash cannot be
reversed to reconstruct device signals. Rotating the secret key invalidates all stored hashes
(acceptable for ban evasion — old bans don't follow a key rotation).

---

## Section 2 — D1 Schema

```sql
-- offender_hashes: stores hashed signal bundles for banned sessions
CREATE TABLE IF NOT EXISTS offender_hashes (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  bundle_hash     TEXT    NOT NULL,   -- HMAC-SHA256 truncated to 32 hex chars
  tier            INTEGER NOT NULL DEFAULT 1,  -- 1=network, 2=browser, 3=active
  ban_reason_code TEXT    NOT NULL,
  ban_expires_at  INTEGER,            -- NULL = permanent
  strike_count    INTEGER NOT NULL DEFAULT 1,
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  last_seen_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE UNIQUE INDEX IF NOT EXISTS offender_hashes_bundle
  ON offender_hashes (bundle_hash);

CREATE INDEX IF NOT EXISTS offender_hashes_expires
  ON offender_hashes (ban_expires_at)
  WHERE ban_expires_at IS NOT NULL;

-- offender_sessions: links banned sessions to their hashes (for audit trail)
CREATE TABLE IF NOT EXISTS offender_sessions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  session_token   TEXT    NOT NULL,   -- already-expired short-lived token
  bundle_hash     TEXT    NOT NULL,
  violation_code  TEXT    NOT NULL,
  actioned_by     TEXT    NOT NULL DEFAULT 'system', -- system | moderator_id
  created_at      INTEGER NOT NULL DEFAULT (unixepoch()),
  FOREIGN KEY (bundle_hash) REFERENCES offender_hashes(bundle_hash)
);
```

---

## Section 3 — Worker: Hash Computation and Ban Check

```typescript
// repeat-offender.ts

interface Env {
  DB: D1Database;
  SITE_SECRET: string; // set via wrangler secret
}

interface DeviceSignals {
  asn: number;
  subnetPrefix: string;   // first 3 octets of IP
  ja4: string;
  langFamily: string;
  uaFamily: string;
  uaMajor: string;
}

async function hmacSha256(key: string, data: string): Promise<string> {
  const enc = new TextEncoder();
  const cryptoKey = await crypto.subtle.importKey(
    'raw', enc.encode(key), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, enc.encode(data));
  const bytes = new Uint8Array(sig);
  // Truncate to 128 bits (16 bytes = 32 hex chars)
  return Array.from(bytes.slice(0, 16)).map(b => b.toString(16).padStart(2, '0')).join('');
}

export function extractDeviceSignals(request: Request): DeviceSignals {
  const cf = request.cf as Record<string, unknown>;
  const rawIp = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
  const subnetPrefix = rawIp.split('.').slice(0, 3).join('.');

  const ua = request.headers.get('User-Agent') ?? '';
  const { family: uaFamily, major: uaMajor } = parseUA(ua);

  const acceptLang = request.headers.get('Accept-Language') ?? '';
  const langFamily = acceptLang.split(',')[0]?.split('-')[0]?.toLowerCase() ?? 'en';

  return {
    asn: (cf.asn as number) ?? 0,
    subnetPrefix,
    ja4: (cf.botManagement as { ja4?: string })?.ja4 ?? '',
    langFamily,
    uaFamily,
    uaMajor,
  };
}

function parseUA(ua: string): { family: string; major: string } {
  // Minimal UA parser — family detection only, no library dependency
  if (/Firefox\/(\d+)/i.test(ua)) return { family: 'firefox', major: ua.match(/Firefox\/(\d+)/i)![1] };
  if (/Chrome\/(\d+)/i.test(ua) && !/Edg\//i.test(ua)) return { family: 'chrome', major: ua.match(/Chrome\/(\d+)/i)![1] };
  if (/Safari\/(\d+)/i.test(ua) && !/Chrome\//i.test(ua)) return { family: 'safari', major: ua.match(/Version\/(\d+)/i)?.[1] ?? '0' };
  if (/Edg\/(\d+)/i.test(ua)) return { family: 'edge', major: ua.match(/Edg\/(\d+)/i)![1] };
  return { family: 'other', major: '0' };
}

export async function computeBundleHash(signals: DeviceSignals, secret: string): Promise<string> {
  const input = [
    `${signals.asn}/${signals.subnetPrefix}`,
    signals.ja4,
    signals.langFamily,
    signals.uaFamily,
    signals.uaMajor,
  ].join('|');
  return hmacSha256(secret, input);
}

export async function checkRepeatOffender(
  bundleHash: string,
  env: Env
): Promise<{ isBanned: boolean; reason?: string; expiresAt?: number; strikeCount?: number }> {
  const row = await env.DB.prepare(`
    SELECT ban_reason_code, ban_expires_at, strike_count
    FROM offender_hashes
    WHERE bundle_hash = ?
      AND (ban_expires_at IS NULL OR ban_expires_at > unixepoch())
  `).bind(bundleHash).first<{
    ban_reason_code: string;
    ban_expires_at: number | null;
    strike_count: number;
  }>();

  if (!row) return { isBanned: false };

  return {
    isBanned: true,
    reason: row.ban_reason_code,
    expiresAt: row.ban_expires_at ?? undefined,
    strikeCount: row.strike_count,
  };
}

export async function recordOffender(
  sessionToken: string,
  bundleHash: string,
  violationCode: string,
  banDurationSeconds: number | null,
  env: Env
): Promise<void> {
  const banExpiresAt = banDurationSeconds
    ? Math.floor(Date.now() / 1000) + banDurationSeconds
    : null;

  await env.DB.batch([
    env.DB.prepare(`
      INSERT INTO offender_hashes (bundle_hash, ban_reason_code, ban_expires_at, strike_count, last_seen_at)
      VALUES (?, ?, ?, 1, unixepoch())
      ON CONFLICT(bundle_hash) DO UPDATE SET
        ban_reason_code = excluded.ban_reason_code,
        ban_expires_at  = excluded.ban_expires_at,
        strike_count    = strike_count + 1,
        last_seen_at    = unixepoch()
    `).bind(bundleHash, violationCode, banExpiresAt),
    env.DB.prepare(`
      INSERT INTO offender_sessions (session_token, bundle_hash, violation_code)
      VALUES (?, ?, ?)
    `).bind(sessionToken, bundleHash, violationCode),
  ]);
}
```

---

## Section 4 — Graduated Escalation Policy

```typescript
// escalation-policy.ts
// Strike count → ban duration and escalation tier

export function getBanDuration(strikeCount: number, violationCode: string): number | null {
  // Returns ban duration in seconds; null = permanent
  const BASE_DURATIONS: Record<string, number[]> = {
    spam:                [3600, 86400, 604800, 2592000],  // 1h, 1d, 7d, 30d
    harassment:          [86400, 604800, 2592000, null as unknown as number],
    underage_bypass:     [604800, null as unknown as number],  // escalates fast
    csam_adjacent:       [null as unknown as number],          // immediate permanent
    coordinated_abuse:   [604800, 2592000, null as unknown as number],
  };

  const durations = BASE_DURATIONS[violationCode] ?? [86400, 604800, 2592000];
  const idx = Math.min(strikeCount - 1, durations.length - 1);
  return durations[idx] ?? null;
}
```

---

## Anti-patterns

- **Storing raw IPs or exact device fingerprints**: Creates a GDPR-classified personal data record.
  Always hash with HMAC+secret before writing to D1.
- **Cross-session behavioral linking beyond enforcement**: The hash may only be used for ban-evasion
  detection. Using it to build interest profiles, ad targeting, or "power user" analytics is a
  purpose-limitation violation under GDPR Art. 5(1)(b).
- **Indefinite retention of offender hashes**: Implement a scheduled cleanup Worker that deletes
  rows where `ban_expires_at < unixepoch()` and `last_seen_at < unixepoch() - 7776000` (90 days).
- **Single-signal hash (IP-only)**: IP addresses rotate frequently for residential users and are
  shared on NAT/CGNAT. A hash containing only IP yields unacceptable false-positive rates.
- **No key rotation plan**: If `SITE_SECRET` is compromised, all hashes become linkable.
  Maintain a KV-stored key version and rotate on a 90-day schedule; invalidate old hashes on rotation.
- **Treating the ban-check as a primary authentication gate**: The hash check is a secondary
  enforcement layer. It is not a substitute for Turnstile proof-of-work on session creation.

---

## Gotchas

- JA4 fingerprints (`cf.botManagement.ja4`) change when a user upgrades their browser or switches
  TLS libraries. Build tolerance: Tier 1 (network-only) bans are enforced regardless of JA4 match;
  Tier 2/3 bans additionally require two additional matching signals.
- Workers `crypto.subtle` is synchronous-looking but returns Promises — always `await` every
  `subtle.importKey` and `subtle.sign` call. Forgetting `await` silently returns a Promise object,
  producing different HMAC output on every run.
- D1's `ON CONFLICT DO UPDATE` requires the conflicting column to be declared `UNIQUE` (or be the
  PRIMARY KEY). A missing `UNIQUE INDEX` on `bundle_hash` causes the upsert to insert a duplicate
  row instead of updating, inflating `strike_count` incorrectly.
- Cloudflare Workers do not guarantee `request.cf.botManagement` is populated in all edge locations
  when using the free Bot Fight Mode (as opposed to paid Bot Management). Treat JA4 as optional
  and fall back to Tier 1 signals when it is absent.
- CGNAT (Carrier-Grade NAT) means many mobile users share the same /24 prefix. A subnet-prefix-only
  ban will block entire ISP neighborhoods. Always require two corroborating non-IP signals before
  a Tier 1 ban.

---

## Verification

```bash
# 1. Compute a test hash and verify it is deterministic
wrangler dev --test
# POST /api/internal/compute-hash with known signals → same hash on repeated calls

# 2. Verify ban check gate
wrangler d1 execute example project-prod --command \
  "INSERT INTO offender_hashes (bundle_hash, ban_reason_code, strike_count)
   VALUES ('aabbccdd11223344aabbccdd11223344', 'spam', 3);"
# Then make a request whose computed hash matches; verify 403 response

# 3. Verify strike increment
wrangler d1 execute example project-prod --command \
  "SELECT strike_count FROM offender_hashes
   WHERE bundle_hash = 'aabbccdd11223344aabbccdd11223344';"
# Should increment by 1 on each new violation recording

# 4. Verify expired bans are not enforced
wrangler d1 execute example project-prod --command \
  "UPDATE offender_hashes SET ban_expires_at = unixepoch() - 1
   WHERE bundle_hash = 'aabbccdd11223344aabbccdd11223344';"
# Request should now pass ban check

# 5. Cleanup cron dry-run
wrangler d1 execute example project-prod --command \
  "SELECT COUNT(*) FROM offender_hashes
   WHERE ban_expires_at < unixepoch() AND last_seen_at < unixepoch() - 7776000;"
```

---

## Related

- `anonymous-platform-abuse-prevention.md`
- `platform-trust-score-cloudflare-signals.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `underage-user-detection-behavioral-signals.md`
- `content-moderation-appeals-workflow.md`
- `gdpr-article-22-automated-decisions-2026.md`

---

## Sources

- GDPR Article 5(1)(b) purpose limitation — https://gdpr-info.eu/art-5-gdpr/
- GDPR Article 25 data protection by design — https://gdpr-info.eu/art-25-gdpr/
- ePrivacy Directive 2002/58/EC Article 5(3) (cookie/fingerprint consent) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32002L0058
- Cloudflare JA4 TLS fingerprinting — https://developers.cloudflare.com/bots/concepts/ja4-signals/
- Web Crypto API (Workers runtime) — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- EU DSA Article 17 (statement of reasons for restriction) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
