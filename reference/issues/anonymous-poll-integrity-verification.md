# Anonymous Poll Integrity Verification

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

Anonymous polls on example project receive suspiciously skewed results shortly after publication: one option accumulates 70-90 % of votes within minutes, vote counts spike far beyond the platform's known active-user ceiling, and re-votes from what appear to be distinct anonymous sessions all arrive from the same narrow IP subnet or with matching device fingerprints. Platform credibility erodes when users distrust poll outcomes.

## Context

example project polls are fully anonymous — no persistent user account is linked to a vote. This makes classic "one vote per user" enforcement impossible. Cloudflare Workers + D1 provide the runtime: each vote request hits a Worker that must decide within milliseconds whether to accept or reject the submission before writing to D1. The integrity system must stop stuffing without sacrificing genuine anonymity or adding user-hostile friction.

Threat actors use:
- Residential proxy rotation to cycle IPs
- Headless browser farms with fresh sessions per request
- Replay of valid Turnstile tokens stolen from legitimate users
- Automated voting scripts timed to run immediately after a poll opens

---

## 1. Vote Token Issuance with Rate-Limited Nonces

Issue a single-use, time-bounded nonce when the poll page loads. The nonce is stored in D1 and expires after one redemption or a 10-minute window.

```typescript
// worker: POST /polls/:pollId/token
export async function issuePollToken(
  pollId: string,
  env: Env,
): Promise<Response> {
  const nonce = crypto.randomUUID();
  const expiresAt = Date.now() + 10 * 60 * 1000; // 10 min

  await env.DB.prepare(
    `INSERT INTO poll_tokens (nonce, poll_id, expires_at, redeemed)
     VALUES (?, ?, ?, 0)`,
  ).bind(nonce, pollId, expiresAt).run();

  // Return nonce as an httpOnly cookie — not readable by JS
  return new Response(null, {
    status: 204,
    headers: {
      "Set-Cookie": `pt=${nonce}; HttpOnly; Secure; SameSite=Strict; Max-Age=600`,
    },
  });
}
```

D1 schema:

```sql
CREATE TABLE poll_tokens (
  nonce      TEXT PRIMARY KEY,
  poll_id    TEXT NOT NULL,
  expires_at INTEGER NOT NULL,
  redeemed   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_poll_tokens_poll ON poll_tokens (poll_id, redeemed);
```

---

## 2. Atomic Nonce Redemption on Vote Submission

Use a conditional UPDATE to redeem the nonce atomically. If `changes` is 0 the nonce was already used or expired.

```typescript
// worker: POST /polls/:pollId/vote
export async function castVote(
  request: Request,
  pollId: string,
  choice: string,
  env: Env,
): Promise<Response> {
  const cookie = request.headers.get("Cookie") ?? "";
  const nonce = parseCookie(cookie, "pt");
  if (!nonce) return new Response("Missing token", { status: 403 });

  const now = Date.now();
  const result = await env.DB.prepare(
    `UPDATE poll_tokens
     SET redeemed = 1
     WHERE nonce = ?
       AND poll_id = ?
       AND redeemed = 0
       AND expires_at > ?`,
  ).bind(nonce, pollId, now).run();

  if (result.meta.changes === 0) {
    return new Response("Token invalid or already used", { status: 409 });
  }

  await env.DB.prepare(
    `INSERT INTO poll_votes (poll_id, choice, voted_at)
     VALUES (?, ?, ?)`,
  ).bind(pollId, choice, now).run();

  return new Response(JSON.stringify({ ok: true }), { status: 200 });
}
```

---

## 3. Velocity Guard via D1 Aggregation

Reject votes when the per-poll rate exceeds a statistical ceiling derived from platform-wide concurrent active sessions (stored in Analytics Engine or KV).

```typescript
async function exceedsVelocityLimit(
  pollId: string,
  env: Env,
): Promise<boolean> {
  const windowMs = 60_000; // 1-minute rolling window
  const cutoff = Date.now() - windowMs;

  const row = await env.DB.prepare(
    `SELECT COUNT(*) AS cnt
     FROM poll_votes
     WHERE poll_id = ? AND voted_at > ?`,
  ).bind(pollId, cutoff).first<{ cnt: number }>();

  const recentVotes = row?.cnt ?? 0;
  const platformCap = parseInt(await env.KV.get("platform:active_sessions") ?? "1000", 10);

  // More than 5 % of active platform sessions voted in one minute — suspicious
  return recentVotes > platformCap * 0.05;
}
```

---

## 4. Cloudflare Signals Enrichment

Attach Cloudflare threat score, ASN, and Turnstile verification to every vote record for post-hoc audit.

```typescript
interface VoteAudit {
  pollId: string;
  choice: string;
  cfThreatScore: number;
  asn: number;
  country: string;
  turnstileOutcome: "pass" | "fail" | "absent";
}

async function enrichVoteAudit(
  request: Request,
  pollId: string,
  choice: string,
): Promise<VoteAudit> {
  const cf = request.cf as CfProperties;
  const turnstileToken = request.headers.get("CF-Turnstile-Token");
  const turnstileOutcome = turnstileToken ? "pass" : "absent"; // simplified

  return {
    pollId,
    choice,
    cfThreatScore: (cf.threatScore as number) ?? 0,
    asn: parseInt(cf.asn as string, 10),
    country: cf.country as string,
    turnstileOutcome,
  };
}
```

Store audit rows in a separate `poll_vote_audit` table for analyst review without linking back to any user identity.

---

## 5. Statistical Anomaly Detection on Poll Close

Run a lightweight chi-squared plausibility check when a poll closes to flag results that are statistically implausible given baseline platform engagement patterns.

```typescript
function chiSquaredUniform(observed: number[]): number {
  const total = observed.reduce((a, b) => a + b, 0);
  if (total === 0) return 0;
  const expected = total / observed.length;
  return observed.reduce((sum, o) => sum + (o - expected) ** 2 / expected, 0);
}

async function auditPollOnClose(pollId: string, env: Env): Promise<void> {
  const rows = await env.DB.prepare(
    `SELECT choice, COUNT(*) AS cnt
     FROM poll_votes
     WHERE poll_id = ?
     GROUP BY choice`,
  ).bind(pollId).all<{ choice: string; cnt: number }>();

  const counts = rows.results.map((r) => r.cnt);
  const chi2 = chiSquaredUniform(counts);

  // chi2 > 20 for a 2-option poll implies extreme skew — flag for review
  if (chi2 > 20) {
    await env.DB.prepare(
      `INSERT INTO poll_integrity_flags (poll_id, reason, flagged_at)
       VALUES (?, ?, ?)`,
    ).bind(pollId, `chi2=${chi2.toFixed(2)}`, Date.now()).run();
  }
}
```

---

## Anti-patterns

- **IP-only deduplication**: residential proxies cycle IPs per request; IP alone provides false confidence without nonce enforcement.
- **Client-side vote counting**: any JavaScript-accessible vote tally can be manipulated before submission.
- **Long-lived poll tokens**: tokens valid for 24 h+ give automated scripts ample replay windows; keep them under 15 minutes.
- **Accepting votes after poll close**: workers must check poll status atomically with the vote insert to prevent race conditions.
- **Logging raw nonces to persistent storage beyond expiry**: nonces have no PII value after redemption; purge them to limit audit table bloat.

## Gotchas

- D1's `changes` meta field returns `0` even on valid queries that matched no rows — always check `changes`, not the absence of an error.
- Cloudflare Turnstile tokens are single-use server-side; a second verification call for the same token will always fail — verify once and cache the outcome for the request lifetime.
- Poll token cookies set with `SameSite=Strict` will not be sent on cross-origin navigations; ensure the poll embed and the Worker share the same registered domain or use `SameSite=None; Secure`.
- D1 does not enforce millisecond-precision uniqueness on concurrent writes; the conditional UPDATE pattern is the correct concurrency primitive, not a SELECT-then-INSERT.
- Chi-squared thresholds depend on option count; recalibrate the critical value for polls with 3+ options (use a lookup table keyed on degrees of freedom).

## Verification

1. Submit the same vote nonce twice; second request must return HTTP 409.
2. Send 200 votes in 60 seconds via a script against a staging poll; velocity guard must block votes after threshold is reached and return HTTP 429.
3. Verify `poll_integrity_flags` table receives a row after manually constructing a poll result set with chi2 > 20.
4. Confirm `poll_tokens` rows older than 10 minutes are rejected even if `redeemed = 0`.
5. Inspect `poll_vote_audit` rows — no column should contain a stable user identifier.

## Related

- `coordinated-inauthentic-behavior-detection-d1.md`
- `platform-abuse-rate-velocity-d1-workers.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `ban-evasion-device-fingerprint-detection-d1.md`

## Sources

- Cloudflare D1 documentation — conditional writes and `meta.changes`
- Cloudflare Turnstile developer guide — single-use token validation
- NIST SP 800-57 — guidance on nonce lifetimes in cryptographic protocols
- W3C anonymous credential considerations for poll systems (2025 draft)
