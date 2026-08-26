# Botnet Account Registration Detection with Turnstile + Fingerprinting
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project's anonymous session system is lightweight by design: a user proves they are human via
Cloudflare Turnstile, receives a short-lived session token, and can begin posting. This low-friction
onboarding is attractive to botnet operators who automate Turnstile solves (via headless browsers,
third-party CAPTCHA-solving farms, or stolen tokens) to mass-register session identities, then use
those sessions for spam, fake engagement (fake "likes" / reaction flooding), coordinated content
flooding, or to manipulate Solana tipping pools.

Indicators of botnet registration campaigns:

- Burst of session creation requests from a single /24 subnet in under 60 seconds.
- Turnstile tokens that pass server-side validation but exhibit abnormal solve-time distributions
  (< 800ms solve = no real user read the page; > 30 000ms = CAPTCHA farm solving queue delay).
- Session creation without any subsequent content interaction (sessions created but never used).
- JA4 fingerprint clusters: hundreds of sessions sharing identical TLS client hello → headless Chrome.
- Solana wallet registration rate spike correlated with airdrop or tip-pool events.

---

## Context

example project runs entirely on Cloudflare Workers. Sessions are backed by D1 and a KV namespace for
fast token validation. The Turnstile integration uses the server-side `/siteverify` endpoint.
example project does not maintain accounts — every session is anonymous. The enforcement goal is to
detect and rate-limit botnet session creation without adding friction for legitimate users.

Cloudflare Turnstile provides a `challenge_ts` field in the siteverify response (ISO 8601 timestamp
of when the challenge was issued) and a `cdata` field (a base64-encoded blob of signals collected
during the solve — available to Enterprise Turnstile customers). The `solve_time` can be inferred
from `challenge_ts` vs. the server receipt timestamp.

Residential botnets that use real browsers are the hardest to detect via Turnstile alone; behavioral
velocity signals (how fast sessions appear from a subnet, whether they ever produce content) are
necessary to catch them.

---

## Section 1 — D1 Schema

```sql
-- session_creation_log: lightweight log of all session creation attempts
CREATE TABLE IF NOT EXISTS session_creation_log (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  session_token   TEXT    NOT NULL UNIQUE,
  ip_subnet       TEXT    NOT NULL,   -- first 3 octets only (e.g. "192.168.1")
  cf_asn          INTEGER NOT NULL DEFAULT 0,
  ja4             TEXT,               -- TLS fingerprint from cf.botManagement.ja4
  turnstile_solve_ms INTEGER,         -- inferred solve time in milliseconds
  bot_score       INTEGER,
  action          TEXT    NOT NULL DEFAULT 'allowed', -- allowed | challenged | blocked
  created_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS scl_subnet_time
  ON session_creation_log (ip_subnet, created_at);
CREATE INDEX IF NOT EXISTS scl_ja4_time
  ON session_creation_log (ja4, created_at)
  WHERE ja4 IS NOT NULL;

-- botnet_subnet_bans: subnets placed under temporary creation throttle
CREATE TABLE IF NOT EXISTS botnet_subnet_bans (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ip_subnet   TEXT    NOT NULL UNIQUE,
  reason      TEXT    NOT NULL,
  ban_expires INTEGER NOT NULL,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS bsb_subnet ON botnet_subnet_bans (ip_subnet);

-- session_activity_stats: tracks whether a created session ever produced activity
CREATE TABLE IF NOT EXISTS session_activity_stats (
  session_token   TEXT    PRIMARY KEY,
  first_post_at   INTEGER,
  first_view_at   INTEGER,
  wallet_linked   INTEGER NOT NULL DEFAULT 0,
  created_at      INTEGER NOT NULL DEFAULT (unixepoch())
);
```

---

## Section 2 — Turnstile Siteverify with Solve-Time Heuristic

```typescript
// session-create-handler.ts

interface Env {
  DB: D1Database;
  SESSION_KV: KVNamespace;
  TURNSTILE_SECRET: string;
  TURNSTILE_BLOCK_KV: KVNamespace;  // fast-path botnet blocks
}

const MIN_SOLVE_MS = 800;     // Humans take at least 800ms to process a challenge page
const MAX_SOLVE_MS = 120_000; // Farm queues take >2min — stale token
const SUBNET_BURST_WINDOW_S = 60;
const SUBNET_BURST_THRESHOLD = 30;  // >30 sessions from same /24 in 60s = suspect

interface TurnstileResponse {
  success: boolean;
  challenge_ts?: string; // ISO 8601
  hostname?: string;
  error_codes?: string[];
  cdata?: string;        // Enterprise only
}

export async function handleSessionCreate(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const body = await request.json<{ turnstile_token: string }>();
  if (!body.turnstile_token) return new Response('Missing token', { status: 400 });

  const cf = request.cf as Record<string, unknown>;
  const rawIp = request.headers.get('CF-Connecting-IP') ?? '0.0.0.0';
  const subnet = rawIp.split('.').slice(0, 3).join('.');
  const asn = (cf.asn as number) ?? 0;
  const botScore = (cf.botManagement as { score?: number })?.score ?? 99;
  const ja4 = (cf.botManagement as { ja4?: string })?.ja4 ?? null;
  const receiptTime = Date.now();

  // Fast-path: check KV for subnet ban (no D1 round-trip needed)
  const subnetBanTtl = await env.TURNSTILE_BLOCK_KV.get(`subnet:${subnet}`);
  if (subnetBanTtl) {
    return new Response(JSON.stringify({ error: 'rate_limited', retry_after: parseInt(subnetBanTtl) }), {
      status: 429,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Verify Turnstile token with Cloudflare
  const verifyResp = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      secret: env.TURNSTILE_SECRET,
      response: body.turnstile_token,
      remoteip: rawIp,
    }),
  });
  const turnstile = await verifyResp.json<TurnstileResponse>();

  if (!turnstile.success) {
    return new Response(JSON.stringify({ error: 'turnstile_failed', codes: turnstile.error_codes }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Compute solve time
  let solveMs: number | null = null;
  let action = 'allowed';

  if (turnstile.challenge_ts) {
    const challengeTime = new Date(turnstile.challenge_ts).getTime();
    solveMs = receiptTime - challengeTime;

    if (solveMs < MIN_SOLVE_MS || solveMs > MAX_SOLVE_MS) {
      action = 'challenged';
    }
  }

  // Low bot score = likely bot/headless browser
  if (botScore < 10) {
    action = 'blocked';
  }

  // Subnet burst check (D1 query)
  const burstRow = await env.DB.prepare(`
    SELECT COUNT(*) as cnt FROM session_creation_log
    WHERE ip_subnet = ?
      AND created_at > unixepoch() - ?
  `).bind(subnet, SUBNET_BURST_WINDOW_S).first<{ cnt: number }>();

  const burstCount = burstRow?.cnt ?? 0;
  if (burstCount >= SUBNET_BURST_THRESHOLD) {
    action = 'blocked';
    // Write subnet ban to KV and D1 (fire-and-forget)
    ctx.waitUntil(banSubnet(subnet, 'burst_threshold', env));
  }

  // JA4 cluster check
  if (ja4) {
    const ja4ClusterRow = await env.DB.prepare(`
      SELECT COUNT(DISTINCT ip_subnet) as subnets
      FROM session_creation_log
      WHERE ja4 = ?
        AND created_at > unixepoch() - 300
    `).bind(ja4).first<{ subnets: number }>();

    if ((ja4ClusterRow?.subnets ?? 0) > 20) {
      // Same TLS fingerprint from >20 different subnets in 5 min = headless browser farm
      action = 'blocked';
    }
  }

  if (action === 'blocked') {
    ctx.waitUntil(logCreation(env.DB, 'blocked_' + crypto.randomUUID().slice(0, 8),
      subnet, asn, ja4, solveMs, botScore, 'blocked'));
    return new Response(JSON.stringify({ error: 'botnet_detected' }), { status: 429 });
  }

  // Issue session token
  const sessionToken = crypto.randomUUID();
  const sessionExpiry = 8 * 3600; // 8 hours

  await Promise.all([
    env.SESSION_KV.put(`session:${sessionToken}`, JSON.stringify({ subnet, asn, created: receiptTime }),
      { expirationTtl: sessionExpiry }),
    logCreation(env.DB, sessionToken, subnet, asn, ja4, solveMs, botScore, action),
  ]);

  return new Response(JSON.stringify({ session_token: sessionToken, expires_in: sessionExpiry }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function banSubnet(subnet: string, reason: string, env: Env): Promise<void> {
  const banDuration = 3600; // 1 hour
  const expiresAt = Math.floor(Date.now() / 1000) + banDuration;
  await Promise.all([
    env.TURNSTILE_BLOCK_KV.put(`subnet:${subnet}`, String(banDuration), { expirationTtl: banDuration }),
    env.DB.prepare(`
      INSERT INTO botnet_subnet_bans (ip_subnet, reason, ban_expires)
      VALUES (?, ?, ?)
      ON CONFLICT(ip_subnet) DO UPDATE SET reason=excluded.reason, ban_expires=excluded.ban_expires
    `).bind(subnet, reason, expiresAt).run(),
  ]);
}

async function logCreation(
  db: D1Database,
  sessionToken: string,
  subnet: string,
  asn: number,
  ja4: string | null,
  solveMs: number | null,
  botScore: number,
  action: string
): Promise<void> {
  await db.prepare(`
    INSERT INTO session_creation_log (session_token, ip_subnet, cf_asn, ja4, turnstile_solve_ms, bot_score, action)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).bind(sessionToken, subnet, asn, ja4, solveMs, botScore, action).run();
}
```

---

## Section 3 — Ghost Session Cleanup Cron

Sessions created but never used are a botnet signal. A scheduled Worker identifies ghost sessions
and feeds their subnets back into the detection model.

```typescript
// cron-ghost-session-sweep.ts
// Runs hourly

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    // Sessions created >30 min ago with no recorded activity
    const ghostRows = await env.DB.prepare(`
      SELECT scl.session_token, scl.ip_subnet, scl.ja4
      FROM session_creation_log scl
      LEFT JOIN session_activity_stats sas ON scl.session_token = sas.session_token
      WHERE scl.created_at < unixepoch() - 1800
        AND scl.action = 'allowed'
        AND sas.session_token IS NULL
      LIMIT 500
    `).all<{ session_token: string; ip_subnet: string; ja4: string | null }>();

    // Aggregate ghost counts by subnet
    const subnetGhostCounts = new Map<string, number>();
    for (const row of ghostRows.results) {
      subnetGhostCounts.set(row.ip_subnet, (subnetGhostCounts.get(row.ip_subnet) ?? 0) + 1);
    }

    // Subnets with >10 ghost sessions in the last hour are suspect
    const batch: D1PreparedStatement[] = [];
    for (const [subnet, count] of subnetGhostCounts) {
      if (count > 10) {
        const banExpiry = Math.floor(Date.now() / 1000) + 7200; // 2h ban
        batch.push(
          env.DB.prepare(`
            INSERT INTO botnet_subnet_bans (ip_subnet, reason, ban_expires)
            VALUES (?, 'ghost_session_cluster', ?)
            ON CONFLICT(ip_subnet) DO UPDATE SET ban_expires=excluded.ban_expires
          `).bind(subnet, banExpiry)
        );
        // Also write to KV for fast-path enforcement
        ctx.waitUntil(
          env.TURNSTILE_BLOCK_KV.put(`subnet:${subnet}`, '7200', { expirationTtl: 7200 })
        );
      }
    }
    if (batch.length > 0) await env.DB.batch(batch);
  }
};
```

---

## Section 4 — Solana Wallet Registration Spike Detection

```typescript
// wallet-link-monitor.ts
// Called when a session links a Solana wallet

export async function handleWalletLink(sessionToken: string, walletPubkey: string, env: Env): Promise<void> {
  // Count wallet links in the last 5 minutes
  const recentLinks = await env.DB.prepare(`
    SELECT COUNT(*) as cnt FROM session_activity_stats
    WHERE wallet_linked = 1
      AND created_at > unixepoch() - 300
  `).first<{ cnt: number }>();

  if ((recentLinks?.cnt ?? 0) > 50) {
    // Airdrop farming spike: >50 wallet links in 5 min
    // Alert the ops channel (via a Cloudflare Queues message to a Slack webhook consumer)
    await env.ALERT_QUEUE.send({
      type: 'wallet_registration_spike',
      count: recentLinks?.cnt,
      window_seconds: 300,
    });
  }

  await env.DB.prepare(`
    INSERT INTO session_activity_stats (session_token, wallet_linked)
    VALUES (?, 1)
    ON CONFLICT(session_token) DO UPDATE SET wallet_linked = 1
  `).bind(sessionToken).run();
}
```

---

## Anti-patterns

- **Hard-blocking based on solve time alone**: CAPTCHA farm solve times overlap with slow mobile
  users on congested networks. Use solve time as one signal, never as the sole gate.
- **Blocking entire /16 or /8 subnets**: CGNAT and large corporate NATs mean a /24 ban already
  affects many legitimate users. Never widen beyond /24 without a human moderation review.
- **Storing `CF-Connecting-IP` in D1 logs**: Raw IPv4 addresses are personal data under GDPR.
  Store subnet prefix only (first three octets).
- **Using KV alone for ban state**: KV is eventually consistent. A burst of requests arriving
  simultaneously before the KV write completes can all pass. The D1 burst-count query is the
  authoritative check; KV is the fast-path cache that avoids D1 round-trips on subsequent requests.
- **No appeals path for false-positive subnet bans**: A shared office or university may share a /24
  that a botnet also used. Provide a `/api/session/appeal` endpoint backed by a D1 state machine.
- **Treating `action='challenged'` as a ban**: The `challenged` action should trigger an additional
  Turnstile managed-mode challenge interstitial (served by Cloudflare automatically), not a block.

---

## Gotchas

- Cloudflare Turnstile's `challenge_ts` is the time the challenge token was *issued*, not when it
  was *rendered*. A token fetched by a bot before page load and replayed later will appear to have
  a solve time equal to the time between bot fetch and Worker receipt — which can look human.
  Always check the `hostname` field to ensure the token was issued for your domain.
- `cf.botManagement.ja4` is only populated with a paid Bot Management subscription. On the free
  Bot Fight Mode tier, this field is absent and the JA4 cluster check must be skipped.
- Turnstile tokens are single-use: the `/siteverify` endpoint returns `duplicate-token` in
  `error_codes` if the same token is verified twice. Log and block token replay attempts.
- Workers D1 `COUNT(*)` queries on `session_creation_log` will be slow if the table grows large
  without the `(ip_subnet, created_at)` composite index. The index defined in the schema above is
  essential.
- Cloudflare KV `put` with `expirationTtl` has a minimum TTL of 60 seconds. Short-duration bans
  (< 60s) must be enforced via D1 only, not KV.
- The `crypto.randomUUID()` call in Workers is available in the Workers runtime without a polyfill
  (it is part of the Web Crypto API exposed in the runtime). Do not import `uuid` from npm.

---

## Verification

```bash
# 1. Simulate burst: send >30 session-create requests from the same /24 in 60s
for i in $(seq 1 35); do
  curl -s -X POST https://example.com/api/session/create \
    -H "Content-Type: application/json" \
    -H "CF-Connecting-IP: 10.0.1.$((RANDOM % 254 + 1))" \
    -d '{"turnstile_token":"test_token"}' &
done; wait
# After 30 requests: subsequent ones should return 429

# 2. Verify subnet ban in KV
wrangler kv:key get --binding TURNSTILE_BLOCK_KV "subnet:10.0.1"

# 3. Verify D1 botnet_subnet_bans entry
wrangler d1 execute example project-prod --command \
  "SELECT * FROM botnet_subnet_bans ORDER BY created_at DESC LIMIT 5;"

# 4. Simulate ghost session sweep (manual trigger)
wrangler d1 execute example project-prod --command \
  "SELECT scl.ip_subnet, COUNT(*) as ghosts
   FROM session_creation_log scl
   LEFT JOIN session_activity_stats sas ON scl.session_token = sas.session_token
   WHERE scl.created_at < unixepoch() - 1800
     AND sas.session_token IS NULL
   GROUP BY scl.ip_subnet
   HAVING ghosts > 10;"

# 5. Verify Turnstile token replay rejection
TOKEN=$(curl -s -X POST https://example.com/api/session/create \
  -d '{"turnstile_token":"valid_token_once"}' | jq -r .session_token)
# Second request with same turnstile_token should fail with duplicate-token
```

---

## Related

- `platform-trust-score-cloudflare-signals.md`
- `repeat-offender-detection-anonymous-sessions.md`
- `rate-limit-abuse-tor-exit-node-detection.md`
- `anonymous-platform-abuse-prevention.md`
- `platform-manipulation-brigading-detection.md`
- `cryptocurrency-regulatory-risk-platform.md`
- `spam-post-detection-cloudflare-workers-ai.md`

---

## Sources

- Cloudflare Turnstile siteverify API — https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- Cloudflare Bot Management JA4 signals — https://developers.cloudflare.com/bots/concepts/ja4-signals/
- Cloudflare Workers KV (consistency model) — https://developers.cloudflare.com/kv/reference/how-kv-works/
- GDPR Article 4(1) — definition of personal data including IP — https://gdpr-info.eu/art-4-gdpr/
- CAPTCHA solving farms: academic overview — Zhang et al., "CAPTCHA Solving Services: A Survey" (IEEE 2022)
- Cloudflare Turnstile managed challenge vs. non-interactive — https://developers.cloudflare.com/turnstile/concepts/widget-types/
