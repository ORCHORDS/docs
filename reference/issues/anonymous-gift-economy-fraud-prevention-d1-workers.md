# Anonymous Gift Economy Fraud Prevention — D1 + Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

example project allows anonymous users to send digital gifts (stickers, boosts, tokens) to posts and
profiles. Fraudsters exploit anonymity to generate fake gift loops — creating throwaway
accounts that gift each other in circles to inflate apparent reputation without spending real
value. Classic fraud signals (email, phone, device) are unavailable, so detection must rely
entirely on transaction graph structure and timing.

---

## Context

Gift economy fraud on anonymous platforms takes three forms:
- **Ring fraud** – A → B → C → A loops that mutually inflate all participants.
- **Wash gifting** – A single actor controls multiple anonymous sessions and gifts between
  them to drain or inflate platform credit balances.
- **Gift sybil amplification** – A botnet gifts a target account to boost it into the
  trending algorithm, then the operator monetises or sells the inflated account.

All three share a structural property: the gift graph has abnormally high reciprocity and
low diameter among the colluding cluster. D1 stores the gift ledger; Workers run heuristic
checks synchronously at gift-time and schedule graph analysis asynchronously.

---

## Schema: Gift Ledger in D1

```sql
CREATE TABLE gifts (
  id          TEXT PRIMARY KEY,
  from_anon   TEXT NOT NULL,   -- hashed session token
  to_anon     TEXT NOT NULL,   -- recipient anon id
  amount      INTEGER NOT NULL,
  gift_type   TEXT NOT NULL,
  created_at  INTEGER NOT NULL, -- unix ms
  flagged     INTEGER DEFAULT 0
);

CREATE INDEX idx_gifts_from ON gifts (from_anon, created_at);
CREATE INDEX idx_gifts_to   ON gifts (to_anon, created_at);
```

---

## 1. Velocity Check at Gift Time

Reject gifts that exceed per-sender limits within a sliding window — catches wash gifting
before it reaches the ledger.

```typescript
async function checkGiftVelocity(
  db: D1Database,
  fromAnon: string,
  windowMs = 3_600_000,
  maxGifts = 20
): Promise<{ allow: boolean; reason?: string }> {
  const since = Date.now() - windowMs;
  const { results } = await db
    .prepare(
      `SELECT COUNT(*) AS cnt, SUM(amount) AS total
       FROM gifts WHERE from_anon = ? AND created_at > ?`
    )
    .bind(fromAnon, since)
    .all<{ cnt: number; total: number }>();

  const row = results[0];
  if ((row?.cnt ?? 0) >= maxGifts) {
    return { allow: false, reason: "gift_velocity_count" };
  }
  if ((row?.total ?? 0) >= 500) {
    return { allow: false, reason: "gift_velocity_amount" };
  }
  return { allow: true };
}
```

---

## 2. Reciprocity Detection

A direct A→B / B→A exchange within a short window is a strong wash-gifting signal.

```typescript
async function hasRecentReciprocal(
  db: D1Database,
  fromAnon: string,
  toAnon: string,
  windowMs = 86_400_000
): Promise<boolean> {
  const since = Date.now() - windowMs;
  const { results } = await db
    .prepare(
      `SELECT 1 FROM gifts
       WHERE from_anon = ? AND to_anon = ? AND created_at > ?
       LIMIT 1`
    )
    .bind(toAnon, fromAnon, since)
    .all();
  return results.length > 0;
}
```

---

## 3. Ring Detection via Reachability (Async Job)

Run periodically via a Cloudflare Cron Trigger to find gift rings of length ≤ 4.

```typescript
// scheduled handler — wrangler.toml: [triggers] crons = ["*/15 * * * *"]
export async function detectGiftRings(db: D1Database): Promise<void> {
  // Pull last-24h gift edges
  const since = Date.now() - 86_400_000;
  const { results } = await db
    .prepare(
      `SELECT DISTINCT from_anon AS src, to_anon AS dst FROM gifts
       WHERE created_at > ? AND flagged = 0 LIMIT 10000`
    )
    .bind(since)
    .all<{ src: string; dst: string }>();

  // Build adjacency map
  const adj = new Map<string, Set<string>>();
  for (const { src, dst } of results) {
    if (!adj.has(src)) adj.set(src, new Set());
    adj.get(src)!.add(dst);
  }

  // DFS up to depth 4 looking for back-edges (cycles)
  const ringedNodes = new Set<string>();
  const dfs = (start: string, current: string, depth: number, path: string[]) => {
    if (depth > 4) return;
    for (const neighbor of adj.get(current) ?? []) {
      if (neighbor === start && path.length >= 2) {
        path.forEach((n) => ringedNodes.add(n));
        return;
      }
      if (!path.includes(neighbor)) {
        dfs(start, neighbor, depth + 1, [...path, neighbor]);
      }
    }
  };

  for (const node of adj.keys()) dfs(node, node, 1, [node]);

  if (ringedNodes.size === 0) return;

  // Flag all gifts involving ring participants
  const placeholders = [...ringedNodes].map(() => "?").join(",");
  await db
    .prepare(
      `UPDATE gifts SET flagged = 1
       WHERE (from_anon IN (${placeholders}) OR to_anon IN (${placeholders}))
         AND created_at > ?`
    )
    .bind(...ringedNodes, ...ringedNodes, since)
    .run();
}
```

---

## 4. Freezing Flagged Balances

Before crediting a recipient, verify the incoming gift chain is clean.

```typescript
async function creditGift(
  db: D1Database,
  giftId: string,
  toAnon: string,
  amount: number
): Promise<void> {
  const gift = await db
    .prepare(`SELECT flagged FROM gifts WHERE id = ?`)
    .bind(giftId)
    .first<{ flagged: number }>();

  if (!gift || gift.flagged) {
    // Park in escrow — do not credit yet
    await db
      .prepare(`INSERT INTO gift_escrow (gift_id, to_anon, amount) VALUES (?,?,?)`)
      .bind(giftId, toAnon, amount)
      .run();
    return;
  }

  await db
    .prepare(`UPDATE balances SET tokens = tokens + ? WHERE anon_id = ?`)
    .bind(amount, toAnon)
    .run();
}
```

---

## Anti-patterns

- **Trusting client-reported gift amounts** — always validate server-side against the ledger.
- **Only checking at insert time** — ring fraud reveals itself in aggregate; you need async
  graph analysis in addition to per-gift checks.
- **Flagging and immediately voiding** — park in escrow first; false positives on legitimate
  users must be recoverable.
- **Unbounded DFS** — without a depth cap the ring detection can stack-overflow on dense graphs.

---

## Gotchas

- D1 `IN` clauses with large arrays (>100 nodes) should be batched.
- `ringedNodes.size` can explode if the gift graph has low-diameter organic clusters (e.g.,
  a tight-knit community with lots of mutual gifting). Tune `windowMs` and depth accordingly.
- Cron triggers fire at most once per minute; keep the ring-detection job idempotent so
  retries are safe.
- Anonymous session tokens that rotate on each visit defeat `from_anon` linkage — pair with
  a short-lived device fingerprint (see `ban-evasion-device-fingerprint-detection-d1.md`).

---

## Verification

```typescript
// Unit test
const db = await createTestD1();
// Seed ring: A→B, B→C, C→A
await seedGifts(db, [["A","B",10],["B","C",10],["C","A",10]]);
await detectGiftRings(db);
const { results } = await db.prepare(`SELECT flagged FROM gifts`).all();
assert(results.every((r: any) => r.flagged === 1), "all ring gifts should be flagged");
```

Manual: create three anonymous sessions, complete a gift loop, wait for the cron job, then
confirm all three accounts have their gifts frozen in `gift_escrow`.

---

## Related

- `coordinated-inauthentic-behavior-detection-d1.md`
- `platform-token-economy-abuse-prevention.md`
- `ban-evasion-device-fingerprint-detection-d1.md`
- `anonymous-user-reputation-bootstrap-d1-workers.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- "Graph-Based Fraud Detection" — IEEE S&P 2023 proceedings
- example project internal gift ledger design spec v2.1
