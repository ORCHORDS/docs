# Platform Token Economy Abuse Prevention

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

example project operates an in-platform token economy where users earn tokens by creating well-received content and spend them on premium visibility, tipping, or access to exclusive spaces. Abuse manifests as wash-trading (users cycling tokens between anonymous accounts they control), hoarding (accumulating tokens through bulk automated content submission), and token-drain attacks (rapidly extracting the maximum per-day tip from a target wallet, forcing that account into a zero-balance state). Platform currency integrity collapses quickly if these vectors go unchecked.

## Context

Anonymous token economies are uniquely fragile: the absence of a real-world identity anchor means there is no KYC backstop. Abuse prevention must rely on behavioural heuristics, transaction velocity limits, and graph-based wash-trade detection — all enforced within D1 and Workers with zero external dependencies. Durable Objects provide the serialised critical section needed for atomic balance operations.

---

## 1. D1 Token Ledger Schema

```sql
CREATE TABLE IF NOT EXISTS token_accounts (
  account_hash   TEXT PRIMARY KEY,
  balance        INTEGER NOT NULL DEFAULT 0,
  lifetime_earned INTEGER NOT NULL DEFAULT 0,
  created_at     INTEGER NOT NULL,
  flagged        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS token_transactions (
  tx_id        TEXT PRIMARY KEY,
  src_hash     TEXT,              -- NULL for platform mint
  dst_hash     TEXT NOT NULL,
  amount       INTEGER NOT NULL,
  tx_type      TEXT NOT NULL,     -- 'earn' | 'tip' | 'spend' | 'refund'
  ref_id       TEXT,              -- content_id or purchase_id
  created_at   INTEGER NOT NULL
);

CREATE INDEX idx_tx_src    ON token_transactions (src_hash, created_at);
CREATE INDEX idx_tx_dst    ON token_transactions (dst_hash, created_at);
CREATE INDEX idx_tx_type   ON token_transactions (tx_type, created_at);
```

---

## 2. Durable Object — Atomic Balance Operations

Use a Durable Object to serialise balance checks and mutations, preventing double-spend races.

```typescript
// TokenWallet Durable Object
export class TokenWallet implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const { action, accountHash, amount, txType, refId } =
      await request.json<{
        action: "credit" | "debit";
        accountHash: string;
        amount: number;
        txType: string;
        refId?: string;
      }>();

    return this.state.blockConcurrencyWhile(async () => {
      const row = await this.env.DB.prepare(
        `SELECT balance FROM token_accounts WHERE account_hash = ?`,
      ).bind(accountHash).first<{ balance: number }>();

      const current = row?.balance ?? 0;

      if (action === "debit" && current < amount) {
        return new Response(JSON.stringify({ ok: false, reason: "insufficient" }), {
          status: 402,
        });
      }

      const newBalance = action === "credit" ? current + amount : current - amount;

      await this.env.DB.batch([
        this.env.DB.prepare(
          `INSERT INTO token_accounts (account_hash, balance, created_at)
           VALUES (?, ?, ?)
           ON CONFLICT(account_hash) DO UPDATE SET balance = ?`,
        ).bind(accountHash, newBalance, Date.now(), newBalance),
        this.env.DB.prepare(
          `INSERT INTO token_transactions
           (tx_id, dst_hash, amount, tx_type, ref_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?)`,
        ).bind(
          crypto.randomUUID(),
          accountHash,
          amount,
          txType,
          refId ?? null,
          Date.now(),
        ),
      ]);

      return new Response(JSON.stringify({ ok: true, newBalance }), { status: 200 });
    });
  }
}
```

---

## 3. Per-day Velocity Limits for Earning and Tipping

Apply daily caps per account to throttle automated earning and drain attacks.

```typescript
const DAILY_EARN_CAP = 500;   // tokens per account per day
const DAILY_TIP_OUT_CAP = 200; // tokens an account can send as tips per day

export async function checkVelocity(
  accountHash: string,
  txType: "earn" | "tip",
  amount: number,
  env: Env,
): Promise<{ allowed: boolean; remaining: number }> {
  const dayStart = new Date();
  dayStart.setUTCHours(0, 0, 0, 0);
  const cutoff = dayStart.getTime();

  const cap = txType === "earn" ? DAILY_EARN_CAP : DAILY_TIP_OUT_CAP;
  const column = txType === "earn" ? "dst_hash" : "src_hash";

  const row = await env.DB.prepare(
    `SELECT COALESCE(SUM(amount), 0) AS daily_total
     FROM token_transactions
     WHERE ${column} = ? AND tx_type = ? AND created_at >= ?`,
  ).bind(accountHash, txType, cutoff).first<{ daily_total: number }>();

  const used = row?.daily_total ?? 0;
  const remaining = Math.max(0, cap - used);
  return { allowed: amount <= remaining, remaining };
}
```

---

## 4. Wash-trade Detection via Round-trip Graph Analysis

Detect accounts that send tokens back and forth within a 24-hour window — a hallmark of wash-trading.

```typescript
// Scheduled Worker — wrangler.toml: [triggers] crons = ["0 */4 * * *"]
export async function detectWashTrades(env: Env): Promise<void> {
  const window = Date.now() - 24 * 60 * 60 * 1000;

  // Find (A→B, B→A) pairs within 24 h
  const pairs = await env.DB.prepare(
    `SELECT a.src_hash AS node_a,
            a.dst_hash AS node_b,
            SUM(a.amount) AS a_to_b,
            SUM(b.amount) AS b_to_a
     FROM token_transactions a
     JOIN token_transactions b
       ON a.src_hash = b.dst_hash
      AND a.dst_hash = b.src_hash
      AND b.tx_type = 'tip'
     WHERE a.tx_type = 'tip'
       AND a.created_at > ?
       AND b.created_at > ?
     GROUP BY node_a, node_b
     HAVING a_to_b > 0 AND b_to_a > 0`,
  ).bind(window, window).all<{
    node_a: string;
    node_b: string;
    a_to_b: number;
    b_to_a: number;
  }>();

  const flagStmts = pairs.results
    .filter(({ a_to_b, b_to_a }) => Math.min(a_to_b, b_to_a) >= 50) // minimum cycle size
    .map(({ node_a, node_b, a_to_b, b_to_a }) =>
      env.DB.prepare(
        `INSERT OR REPLACE INTO wash_trade_flags
         (node_a, node_b, a_to_b, b_to_a, flagged_at)
         VALUES (?, ?, ?, ?, ?)`,
      ).bind(node_a, node_b, a_to_b, b_to_a, Date.now()),
    );

  if (flagStmts.length > 0) await env.DB.batch(flagStmts);
}
```

Schema:

```sql
CREATE TABLE IF NOT EXISTS wash_trade_flags (
  node_a     TEXT NOT NULL,
  node_b     TEXT NOT NULL,
  a_to_b     INTEGER NOT NULL,
  b_to_a     INTEGER NOT NULL,
  flagged_at INTEGER NOT NULL,
  actioned   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (node_a, node_b)
);
```

---

## 5. Anomalous Earn Velocity — Bulk Content Submission Detection

Accounts earning tokens at a superhuman rate signal automated posting.

```typescript
export async function detectBulkEarner(
  accountHash: string,
  env: Env,
): Promise<boolean> {
  const hourCutoff = Date.now() - 60 * 60 * 1000;

  const row = await env.DB.prepare(
    `SELECT COUNT(*) AS earn_events
     FROM token_transactions
     WHERE dst_hash = ?
       AND tx_type = 'earn'
       AND created_at > ?`,
  ).bind(accountHash, hourCutoff).first<{ earn_events: number }>();

  // More than 20 earn events in one hour is implausible for a human
  const HUMAN_HOURLY_CEILING = 20;
  return (row?.earn_events ?? 0) > HUMAN_HOURLY_CEILING;
}
```

---

## Anti-patterns

- **Client-side balance display as the source of truth**: always read balance from D1 inside the Durable Object; never trust a balance value sent from the client.
- **Allowing negative balances as temporary credit**: negative balances create a drain path; enforce `current >= amount` before any debit.
- **Global daily caps without per-account caps**: a single global ledger lock becomes a bottleneck; enforce caps per account hash in D1.
- **Storing raw account hashes without salting**: if the hash function is known, collision attacks can map hashes to known users; use HMAC with a platform-level secret.
- **Reversing flagged transactions retroactively in bulk**: bulk reversals disrupt legitimate adjacent users; flag and freeze first, then individually review before reversal.

## Gotchas

- `blockConcurrencyWhile` in Durable Objects is synchronous within the DO instance but still subject to the DO's CPU time limit (30 s); keep the critical section lean.
- D1's self-JOIN in the wash-trade query can be slow if `token_transactions` is large; always include the time-window filter on both sides of the JOIN to exploit the `created_at` index.
- `COALESCE(SUM(amount), 0)` is necessary in velocity queries — `SUM` of zero rows returns `NULL` in SQLite, which would incorrectly pass any `amount <= NULL` check.
- The Durable Object stub URL must be derived deterministically from `accountHash` so all requests for the same account route to the same DO instance; use `env.WALLET_DO.idFromName(accountHash)`.
- Wash-trade detection via self-JOIN will also match legitimate back-and-forth tipping between friends; set the minimum cycle size threshold high enough (50+ tokens) to exclude small reciprocal tips.

## Verification

1. Debit a balance below zero via the Durable Object; confirm HTTP 402 and no D1 mutation occurs.
2. Submit 21 earn transactions in under an hour for a test account; confirm `detectBulkEarner` returns `true`.
3. Insert a (A→B 100, B→A 100) tip pair within 24 h; run `detectWashTrades` and confirm a `wash_trade_flags` row appears.
4. Confirm the daily earn cap blocks a 501st token credit on a test account for the current UTC day.
5. Verify concurrent debit requests for the same Durable Object instance are serialised (only one succeeds when balance = exactly the debit amount).

## Related

- `platform-abuse-rate-velocity-d1-workers.md`
- `financial-fraud-detection-digital-goods.md`
- `cryptocurrency-fraud-detection-workers.md`
- `sock-puppet-network-detection.md`
- `anonymous-poll-integrity-verification.md`

## Sources

- Cloudflare Durable Objects documentation — `blockConcurrencyWhile`
- Cloudflare D1 documentation — batched statements
- "Token Economy Manipulation in Anonymous Social Platforms" — IEEE S&P 2025 workshop
- FATF Guidance on Virtual Assets — wash-trading definitions and red flags (2023)
