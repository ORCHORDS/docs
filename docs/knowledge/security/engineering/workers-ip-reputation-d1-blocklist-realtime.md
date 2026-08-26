# Workers IP Reputation and D1 Blocklist for Real-Time Abuse Prevention

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project is an anonymous platform — users have no account, so traditional account-level rate limiting and banning are insufficient. A harassing actor simply clears cookies and resumes. IP-based reputation scoring, combined with a real-time D1 blocklist, lets the platform block known-bad actors at the edge before any application logic runs, without requiring a third-party IP intelligence service.

## Context

Cloudflare Workers receive the client IP via `request.headers.get("CF-Connecting-IP")` (or `CF-Pseudo-IPv4` for IPv6 duals). D1 is a SQLite-backed database accessible from Workers with sub-millisecond latency when queries are simple. Combined with Cloudflare's own threat score (`request.cf.threatScore`), the Worker can make a block/allow decision in under 2 ms without egress.

## Threat Model

IP reputation defends against:
- **Persistent harassers** who cycle anonymous sessions but reuse the same IP.
- **Automated scrapers and spam bots** originating from known-bad CIDR ranges.
- **Credential stuffing from proxies** where Cloudflare's WAF has already scored the IP.

Limitations: VPN-exiting attackers can change IP cheaply. This layer is not the only defence — it raises the cost of abuse and buys time for human moderators.

```typescript
// threat-model.ts
interface IpDecision {
  blocked: boolean;
  reason: "d1_blocklist" | "cf_threat_score" | "d1_rate_abuse" | "clean";
  score: number;
}
```

## D1 Schema and Blocklist Management

```sql
-- migrations/0001_ip_blocklist.sql
CREATE TABLE IF NOT EXISTS ip_blocks (
  ip         TEXT PRIMARY KEY,
  cidr       INTEGER NOT NULL DEFAULT 0,  -- 1 = CIDR block, 0 = exact IP
  expires_at INTEGER,                     -- NULL = permanent
  reason     TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);

CREATE INDEX IF NOT EXISTS idx_ip_blocks_expires ON ip_blocks(expires_at)
  WHERE expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS ip_abuse_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ip         TEXT NOT NULL,
  event_type TEXT NOT NULL,   -- 'spam', 'harassment', 'scrape', 'rate_abuse'
  ts         INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);

CREATE INDEX IF NOT EXISTS idx_abuse_ip_ts ON ip_abuse_events(ip, ts);
```

## Real-Time Lookup Worker

Combine the Cloudflare threat score with the D1 blocklist in a single middleware. The lookup is intentionally minimal (one indexed primary-key lookup) to stay under 1 ms.

```typescript
// ip-reputation.ts
const CF_THREAT_BLOCK_THRESHOLD = 30;  // 0-100; 30+ = suspicious proxy/bot
const ABUSE_WINDOW_MS = 60 * 60 * 1000;  // 1-hour rolling window
const ABUSE_EVENT_THRESHOLD = 10;

export interface Env {
  DB: D1Database;
}

export async function checkIpReputation(
  req: Request,
  env: Env
): Promise<IpDecision> {
  const ip = req.headers.get("CF-Connecting-IP") ?? "0.0.0.0";
  const cf = (req as any).cf ?? {};
  const threatScore: number = cf.threatScore ?? 0;

  // 1. Cloudflare native threat score (free, zero-latency)
  if (threatScore >= CF_THREAT_BLOCK_THRESHOLD) {
    return { blocked: true, reason: "cf_threat_score", score: threatScore };
  }

  // 2. D1 explicit blocklist (exact IP, permanent or time-limited)
  const blocked = await env.DB.prepare(
    `SELECT 1 FROM ip_blocks
     WHERE ip = ?
       AND (expires_at IS NULL OR expires_at > ?)
     LIMIT 1`
  ).bind(ip, Date.now()).first<{ 1: number }>();

  if (blocked) {
    return { blocked: true, reason: "d1_blocklist", score: 100 };
  }

  // 3. Rolling abuse event count
  const since = Date.now() - ABUSE_WINDOW_MS;
  const row = await env.DB.prepare(
    `SELECT COUNT(*) AS cnt FROM ip_abuse_events WHERE ip = ? AND ts > ?`
  ).bind(ip, since).first<{ cnt: number }>();

  const cnt = row?.cnt ?? 0;
  if (cnt >= ABUSE_EVENT_THRESHOLD) {
    // Auto-promote to blocklist for 24 h
    await blockIp(env.DB, ip, "auto_rate_abuse", Date.now() + 86_400_000);
    return { blocked: true, reason: "d1_rate_abuse", score: cnt * 10 };
  }

  return { blocked: false, reason: "clean", score: Math.max(threatScore, cnt) };
}

export async function blockIp(
  db: D1Database,
  ip: string,
  reason: string,
  expiresAt?: number
): Promise<void> {
  await db.prepare(
    `INSERT INTO ip_blocks (ip, reason, expires_at)
     VALUES (?, ?, ?)
     ON CONFLICT(ip) DO UPDATE SET
       reason     = excluded.reason,
       expires_at = excluded.expires_at,
       created_at = unixepoch() * 1000`
  ).bind(ip, reason, expiresAt ?? null).run();
}

export async function recordAbuseEvent(
  db: D1Database,
  ip: string,
  eventType: string
): Promise<void> {
  await db.prepare(
    `INSERT INTO ip_abuse_events (ip, event_type) VALUES (?, ?)`
  ).bind(ip, eventType).run();
}
```

## Hardening — Worker Middleware Integration

Apply the reputation check at the top of the Worker fetch handler before any route parsing. Block responses must not leak the reason to avoid giving attackers feedback.

```typescript
// middleware.ts
export async function withIpReputation(
  req: Request,
  env: Env,
  next: () => Promise<Response>
): Promise<Response> {
  const decision = await checkIpReputation(req, env);

  if (decision.blocked) {
    // Log internally but return a generic 403
    console.log(JSON.stringify({
      event: "ip_blocked",
      ip: req.headers.get("CF-Connecting-IP"),
      reason: decision.reason,
      score: decision.score,
      ts: Date.now(),
    }));

    // Mimic a normal 404 to avoid confirming block status to the requester
    return new Response("Not Found", { status: 404 });
  }

  const res = await next();

  // Attach score header for downstream Workers (internal only, strip at edge)
  const headers = new Headers(res.headers);
  headers.set("X-Internal-Ip-Score", decision.score.toString());
  return new Response(res.body, { ...res, headers });
}
```

## Monitoring

Tail worker or cron trigger to prune expired blocks and emit a daily summary.

```typescript
// blocklist-ops.ts
export async function pruneExpiredBlocks(db: D1Database): Promise<number> {
  const result = await db.prepare(
    "DELETE FROM ip_blocks WHERE expires_at IS NOT NULL AND expires_at < ?"
  ).bind(Date.now()).run();
  return result.meta.changes;
}

export async function topAbusingIps(
  db: D1Database,
  since: number,
  limit = 20
): Promise<Array<{ ip: string; cnt: number }>> {
  const { results } = await db.prepare(
    `SELECT ip, COUNT(*) AS cnt
     FROM ip_abuse_events
     WHERE ts > ?
     GROUP BY ip
     ORDER BY cnt DESC
     LIMIT ?`
  ).bind(since, limit).all<{ ip: string; cnt: number }>();
  return results;
}
```

## Anti-patterns

- Blocking based solely on ASN or country — too broad for an anonymous social platform.
- Returning `403 Forbidden` with a body that says "your IP is blocked" — confirms the block and aids evasion.
- Querying D1 with a table scan (`SELECT * FROM ip_blocks`) on every request — always use the indexed primary-key lookup.
- Storing IPv6 full addresses without normalising — `::ffff:1.2.3.4` and `1.2.3.4` must be treated identically.
- Blocking localhost or RFC1918 addresses — the `CF-Connecting-IP` header should always be a public IP; validate before inserting.

## Gotchas

- `req.cf.threatScore` requires a paid Cloudflare plan; it is `undefined` on free plans — always default to 0.
- D1 is eventually consistent across primary/replica replicas; a freshly inserted block may not be visible on the nearest replica for up to 50 ms. For immediate enforcement, write blocks to primary and also push to a KV key with a 60-second TTL as a fast-path check.
- Auto-promoting IPs to the blocklist creates a D1 write on every threshold breach — debounce with a KV flag to avoid write storms when many concurrent requests hit the threshold simultaneously.
- IPv6 prefix blocking requires CIDR matching not supported natively in SQLite; store expanded /64 or /48 prefixes as separate rows until a proper CIDR library is available.
- The `CF-Connecting-IP` header can be spoofed when calling the Worker URL directly (not through the Cloudflare proxy); validate `req.cf` is present before trusting it.

## Verification

```bash
# Insert a test block
wrangler d1 execute example project-db --command \
  "INSERT INTO ip_blocks (ip, reason) VALUES ('203.0.113.1', 'test');"

# Confirm the block lookup works
wrangler d1 execute example project-db --command \
  "SELECT * FROM ip_blocks WHERE ip='203.0.113.1';"

# Hit the Worker from a test IP (use CF-Connecting-IP override in local dev)
curl -H "CF-Connecting-IP: 203.0.113.1" https://localhost:8787/

# Confirm response is 404 (blocked, disguised)
# Confirm response is 200 for a non-blocked IP
```

## Related

- /documentation/docs/policies/security/cloudflare-bot-management-abuse-prevention.md
- /documentation/docs/policies/security/rate-limiting-per-user-d1-durable-objects.md
- /documentation/docs/policies/security/cloudflare-rate-limiting-v2-api-abuse-prevention.md
- /documentation/docs/policies/security/ato-behavioral-anomaly-scoring-d1.md
- /documentation/docs/policies/security/x-forwarded-for-client-ip-spoofing.md

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/d1/
- https://owasp.org/www-project-automated-threats-to-web-applications/
- https://developers.cloudflare.com/bots/concepts/threat-score/
- https://cheatsheetseries.owasp.org/cheatsheets/Abuse_Case_Cheat_Sheet.html
