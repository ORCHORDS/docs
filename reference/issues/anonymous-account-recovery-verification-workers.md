# Anonymous Account Recovery Verification in Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

On anonymous platforms users create accounts without email or phone. When they lose access to their device — factory reset, new phone, cleared storage — their identity is permanently severed. Without a recovery mechanism the friction of losing an account discourages honest users and causes them to create fresh accounts, inflating registration numbers with duplicates. The challenge is to provide recovery without collecting PII that undermines the platform's anonymous promise.

## Context

Anonymous account recovery relies on cryptographic proof rather than identity verification. At account creation the platform issues a tamper-evident recovery token that the user stores offline (exported QR code, saved passphrase). A secondary signal — device-binding via a stable hardware attestation or Cloudflare Turnstile — provides a second factor without storing PII server-side. Recovery attempts are rate-limited in Durable Objects and logged immutably in D1 to detect takeover attacks where an adversary guesses or steals a recovery token.

## Recovery Token Issuance at Account Creation

At registration a 256-bit recovery secret is generated server-side, stored as its SHA-256 hash in D1, and returned once in plaintext to the client for out-of-band storage. The platform never stores the plaintext.

```typescript
// worker: account-create.ts
export interface Env {
  DB: D1Database;
}

interface NewAccount {
  accountId: string;
  createdAt: string;
  recoveryTokenHash: string;
}

export async function createAccountWithRecoveryToken(
  env: Env
): Promise<{ account: NewAccount; recoveryToken: string }> {
  const accountId = crypto.randomUUID();

  // 32 bytes of CSPRNG output — the only copy; user must store this
  const raw = crypto.getRandomValues(new Uint8Array(32));
  const recoveryToken = btoa(String.fromCharCode(...raw));

  const hashBuf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(recoveryToken)
  );
  const recoveryTokenHash = Array.from(new Uint8Array(hashBuf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  const createdAt = new Date().toISOString();

  await env.DB.prepare(
    `INSERT INTO accounts (account_id, recovery_token_hash, created_at, status)
     VALUES (?1, ?2, ?3, 'active')`
  ).bind(accountId, recoveryTokenHash, createdAt).run();

  return {
    account: { accountId, createdAt, recoveryTokenHash },
    recoveryToken, // returned to client ONCE — never stored plaintext server-side
  };
}
```

## Rate-Limited Recovery Attempt Enforcement

A Durable Object per recovery-attempt window prevents brute-force token guessing. At most 3 attempts per 24 hours per IP/ASN pair are permitted; further attempts are silently dropped to avoid oracle feedback.

```typescript
// durable-object: RecoveryRateLimiter.ts
export class RecoveryRateLimiter implements DurableObject {
  private state: DurableObjectState;
  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(req: Request): Promise<Response> {
    const now = Date.now();
    const window = 86_400_000; // 24 h
    const maxAttempts = 3;

    const stored = await this.state.storage.get<number[]>('attempts') ?? [];
    const recent = stored.filter((t) => now - t < window);

    if (recent.length >= maxAttempts) {
      return Response.json({ allowed: false }, { status: 429 });
    }

    recent.push(now);
    await this.state.storage.put('attempts', recent);
    return Response.json({ allowed: true });
  }
}

// Caller in recovery Worker:
async function checkRecoveryRateLimit(
  env: { RATE_LIMITER: DurableObjectNamespace },
  ip: string,
  asn: string
): Promise<boolean> {
  const key = `${asn}:${ip.split('.').slice(0, 3).join('.')}`;
  const id = env.RATE_LIMITER.idFromName(key);
  const stub = env.RATE_LIMITER.get(id);
  const res = await stub.fetch(new Request('https://do/check', { method: 'POST' }));
  const { allowed } = await res.json<{ allowed: boolean }>();
  return allowed;
}
```

## Recovery Token Verification and Session Reissue

The recovery endpoint accepts the plaintext token, hashes it, and compares against D1. On success it rotates the token (one-time use) and issues a new session, logging the recovery event immutably.

```typescript
// worker: account-recovery.ts
export interface Env {
  DB: D1Database;
  RATE_LIMITER: DurableObjectNamespace;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const cf = req.cf as Record<string, string | number | undefined>;
    const ip = req.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
    const asn = String(cf?.asn ?? 'unknown');

    const allowed = await checkRecoveryRateLimit(env, ip, asn);
    if (!allowed) {
      // Silent 200 to avoid confirming rate limit oracle
      return new Response(JSON.stringify({ status: 'processing' }), { status: 200 });
    }

    const { recoveryToken } = await req.json<{ recoveryToken: string }>();

    const hashBuf = await crypto.subtle.digest(
      'SHA-256',
      new TextEncoder().encode(recoveryToken)
    );
    const hash = Array.from(new Uint8Array(hashBuf))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');

    const row = await env.DB.prepare(
      `SELECT account_id, status FROM accounts
       WHERE recovery_token_hash = ?1 AND status = 'active' LIMIT 1`
    ).bind(hash).first<{ account_id: string; status: string }>();

    if (!row) {
      // Log failed attempt without revealing whether token exists
      await env.DB.prepare(
        `INSERT INTO recovery_audit (token_hash_prefix, ip_subnet, asn, outcome, attempted_at)
         VALUES (?1, ?2, ?3, 'fail', unixepoch())`
      ).bind(hash.slice(0, 8), ip.split('.').slice(0, 3).join('.'), asn).run();

      return new Response(JSON.stringify({ status: 'processing' }), { status: 200 });
    }

    // Rotate the recovery token — one-time use
    const newRaw = crypto.getRandomValues(new Uint8Array(32));
    const newToken = btoa(String.fromCharCode(...newRaw));
    const newHashBuf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(newToken));
    const newHash = Array.from(new Uint8Array(newHashBuf))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');

    const newSession = crypto.randomUUID();

    await env.DB.batch([
      env.DB.prepare(
        `UPDATE accounts SET recovery_token_hash = ?1 WHERE account_id = ?2`
      ).bind(newHash, row.account_id),
      env.DB.prepare(
        `INSERT INTO sessions (session_id, account_id, created_at, expires_at)
         VALUES (?1, ?2, unixepoch(), unixepoch() + 2592000)`
      ).bind(newSession, row.account_id),
      env.DB.prepare(
        `INSERT INTO recovery_audit (token_hash_prefix, ip_subnet, asn, outcome, account_id, attempted_at)
         VALUES (?1, ?2, ?3, 'success', ?4, unixepoch())`
      ).bind(hash.slice(0, 8), ip.split('.').slice(0, 3).join('.'), asn, row.account_id),
    ]);

    return Response.json({ sessionToken: newSession, newRecoveryToken: newToken });
  },
};
```

## Takeover Detection via Recovery Audit

Successful recoveries from an ASN/country combination that never appeared in the account's history are flagged as potential account takeovers and queued for Trust & Safety review.

```typescript
// worker: recovery-takeover-check.ts
export async function flagSuspiciousRecovery(
  env: Env,
  accountId: string,
  currentAsn: string,
  currentCountry: string
): Promise<void> {
  // Check whether this ASN/country appeared in the last 90 days of activity
  const history = await env.DB.prepare(
    `SELECT COUNT(*) AS cnt FROM activity_log
     WHERE account_id = ?1
       AND asn = ?2
       AND country = ?3
       AND logged_at > unixepoch() - 7776000`
  ).bind(accountId, currentAsn, currentCountry)
    .first<{ cnt: number }>();

  if (!history || history.cnt === 0) {
    await env.DB.prepare(
      `INSERT INTO takeover_flags (account_id, flagged_at, reason, reviewer_action)
       VALUES (?1, unixepoch(), 'recovery_new_geo', 'pending')`
    ).bind(accountId).run();
  }
}
```

## Anti-patterns

- Storing the plaintext recovery token server-side — if the database is compromised, every account is recoverable by the attacker; hash and compare only
- Returning a meaningful error on failed recovery (`"token not found"`) — this creates an oracle that confirms whether a guessed token is wrong; always return a neutral response
- Using a single global rate-limit key per recovery endpoint — apply rate limiting per IP /24 and ASN pair so VPN-switching does not reset the window
- Skipping token rotation after successful recovery — a stolen token is useless only if it is immediately invalidated on first use
- Accepting recovery tokens in GET query parameters — they appear in server logs and browser history; POST with a JSON body only

## Gotchas

- `btoa` in Workers accepts binary strings; pass `String.fromCharCode(...uint8array)` rather than raw `Uint8Array`
- D1 `INTEGER` columns store UNIX seconds; `unixepoch()` returns seconds — do not mix with JavaScript `Date.now()` milliseconds without dividing by 1000
- Token hashes must be compared in constant time when possible; D1 SQL `=` comparison is not constant-time, but a hex-hashed 256-bit value makes timing attacks computationally infeasible for correctly-sized tokens
- Recovery tokens displayed as QR codes should use the base64url variant (replace `+`/`/` with `-`/`_`) to avoid URL encoding issues in QR data strings
- Durable Object IDs derived from `idFromName` are deterministic — an attacker who learns the key derivation scheme (IP/ASN) can predict the DO and probe rate-limit state; add a server-side HMAC salt to the name if this is a concern

## Verification

1. Call `createAccountWithRecoveryToken` and confirm the returned `recoveryToken` is not stored in D1 plaintext (`SELECT * FROM accounts` should show only the hash).
2. Submit the plaintext token to the recovery endpoint and assert a new `sessionToken` and `newRecoveryToken` are returned.
3. Re-submit the original token immediately after — assert it fails (hash no longer matches after rotation).
4. Exhaust the rate limit (3 attempts) and confirm subsequent attempts return `200` silently without revealing the limit.
5. Insert a `recovery_audit` success row with a novel ASN/country and call `flagSuspiciousRecovery`; confirm a `takeover_flags` row is created with `reviewer_action = 'pending'`.

## Related

- `account-takeover-detection-prevention.md`
- `account-dormancy-suspicious-reactivation-d1.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `ban-evasion-device-fingerprint-detection-d1.md`
- `anonymous-user-reputation-bootstrap-d1-workers.md`

## Sources

- NIST SP 800-63B — Authentication and Lifecycle Management (recovery token guidance)
- Cloudflare Durable Objects documentation — per-key rate limiting: https://developers.cloudflare.com/durable-objects/
- Cloudflare Workers Crypto API — `crypto.subtle.digest`: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- OWASP Account Recovery Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
