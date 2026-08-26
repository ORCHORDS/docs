# OFAC Sanctions Screening on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Payment flows need real-time OFAC/SDN list screening before funds are moved. Failing to block a sanctioned counterparty exposes the platform to civil and criminal penalties under 31 CFR §§ 500–598.

## Context
The US Treasury OFAC publishes the Specially Designated Nationals (SDN) list as a downloadable XML/CSV. Cloudflare Workers can cache a compressed, indexed version in KV and screen every payment participant at the edge in <5 ms without a round-trip to an external compliance vendor. Updates should be pulled on a Cron Trigger (daily minimum, hourly for high-risk verticals).

## Ingesting and Indexing the SDN List

Pull the OFAC consolidated list, parse names and aliases into a KV-friendly structure, and store normalised tokens for fuzzy lookup.

```typescript
// cron-sdningest.ts — runs via Cron Trigger (0 * * * *)
import type { ScheduledController, KVNamespace } from "@cloudflare/workers-types";

interface Env {
  SDN_KV: KVNamespace;
}

interface SdnEntry {
  uid: string;
  names: string[];   // primary + all aliases
  programs: string[];
  type: string;      // "individual" | "entity" | "vessel" | "aircraft"
}

const SDN_CSV_URL =
  "https://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml";

export default {
  async scheduled(_ctrl: ScheduledController, env: Env): Promise<void> {
    const res = await fetch(SDN_CSV_URL);
    if (!res.ok) throw new Error(`OFAC fetch failed: ${res.status}`);
    const xml = await res.text();

    const entries = parseSdnXml(xml);          // see parseSdnXml below
    const tokenMap: Record<string, string[]> = {};

    for (const entry of entries) {
      for (const name of entry.names) {
        for (const token of tokenise(name)) {
          if (!tokenMap[token]) tokenMap[token] = [];
          tokenMap[token].push(entry.uid);
        }
      }
    }

    // Store token → uid[] shards (KV value limit 25 MB)
    const shards: Record<string, Record<string, string[]>> = {};
    for (const [token, uids] of Object.entries(tokenMap)) {
      const shard = token.slice(0, 2);          // 2-char prefix sharding
      if (!shards[shard]) shards[shard] = {};
      shards[shard][token] = uids;
    }

    const batch = Object.entries(shards).map(([shard, data]) =>
      env.SDN_KV.put(`sdn:shard:${shard}`, JSON.stringify(data), {
        expirationTtl: 90_000,                  // 25 h — cron is hourly
      })
    );
    // Store full entry metadata separately
    const metaBatch = entries.map((e) =>
      env.SDN_KV.put(`sdn:entry:${e.uid}`, JSON.stringify(e), {
        expirationTtl: 90_000,
      })
    );
    await Promise.all([...batch, ...metaBatch]);
    await env.SDN_KV.put("sdn:updated_at", new Date().toISOString());
  },
};

function tokenise(name: string): string[] {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .split(/\s+/)
    .filter((t) => t.length >= 3);
}

function parseSdnXml(_xml: string): SdnEntry[] {
  // Real implementation: use a lightweight streaming XML parser (e.g. txml)
  // bundled into the Worker. Stubbed here for clarity.
  return [];
}
```

## Real-time Screening at Payment Intake

Screen payer and payee names before calling any payment processor. Return a structured hit report; block on any confirmed match.

```typescript
// screen.ts
export interface ScreenResult {
  blocked: boolean;
  hits: Array<{ uid: string; name: string; programs: string[]; score: number }>;
  checkedAt: string;
}

export async function screenName(
  name: string,
  env: { SDN_KV: KVNamespace }
): Promise<ScreenResult> {
  const tokens = tokenise(name);
  const shardKeys = [...new Set(tokens.map((t) => t.slice(0, 2)))];

  // Parallel KV reads — one per unique shard
  const shards = await Promise.all(
    shardKeys.map((s) => env.SDN_KV.get<Record<string, string[]>>(`sdn:shard:${s}`, "json"))
  );

  const candidateUids = new Set<string>();
  shards.forEach((shard, i) => {
    if (!shard) return;
    for (const token of tokens) {
      if (token.slice(0, 2) === shardKeys[i]) {
        (shard[token] ?? []).forEach((uid) => candidateUids.add(uid));
      }
    }
  });

  const hits: ScreenResult["hits"] = [];
  await Promise.all(
    [...candidateUids].map(async (uid) => {
      const entry = await env.SDN_KV.get<SdnEntry>(`sdn:entry:${uid}`, "json");
      if (!entry) return;
      const score = bestScore(name, entry.names);
      if (score >= 0.85) {
        hits.push({ uid, name: entry.names[0], programs: entry.programs, score });
      }
    })
  );

  return { blocked: hits.length > 0, hits, checkedAt: new Date().toISOString() };
}

function tokenise(name: string): string[] {
  return name.toLowerCase().replace(/[^a-z0-9\s]/g, "").split(/\s+/).filter((t) => t.length >= 3);
}

function bestScore(query: string, candidates: string[]): number {
  const qTokens = new Set(tokenise(query));
  return Math.max(
    ...candidates.map((c) => {
      const cTokens = new Set(tokenise(c));
      const intersection = [...qTokens].filter((t) => cTokens.has(t)).length;
      return intersection / Math.max(qTokens.size, cTokens.size);
    })
  );
}

interface SdnEntry { uid: string; names: string[]; programs: string[]; type: string }
declare const KVNamespace: unknown;
```

## Payment Gate Middleware

Wire screening into the payment intake Worker. Log every check to Cloudflare D1 for audit trail.

```typescript
// payment-gate.ts
import type { D1Database, KVNamespace } from "@cloudflare/workers-types";
import { screenName } from "./screen";

interface Env {
  SDN_KV: KVNamespace;
  DB: D1Database;
}

export async function handlePaymentRequest(req: Request, env: Env): Promise<Response> {
  const body = await req.json<{ payerName: string; payeeName: string; amountUsd: number }>();

  const [payerResult, payeeResult] = await Promise.all([
    screenName(body.payerName, env),
    screenName(body.payeeName, env),
  ]);

  const blocked = payerResult.blocked || payeeResult.blocked;

  // Persist audit record (D1)
  await env.DB.prepare(
    `INSERT INTO ofac_screen_log
       (id, payer_name, payee_name, payer_blocked, payee_blocked, hit_json, checked_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(
      crypto.randomUUID(),
      body.payerName,
      body.payeeName,
      payerResult.blocked ? 1 : 0,
      payeeResult.blocked ? 1 : 0,
      JSON.stringify({ payer: payerResult.hits, payee: payeeResult.hits }),
      new Date().toISOString()
    )
    .run();

  if (blocked) {
    return Response.json({ error: "payment_blocked", reason: "ofac_match" }, { status: 403 });
  }

  // Proceed to PSP — e.g. Stripe, Adyen, etc.
  return Response.json({ status: "cleared" });
}
```

## Anti-patterns
- Caching the entire SDN list as a single KV value — exceeds the 25 MB limit and causes read timeouts.
- Relying solely on exact-match string comparison — misses transliterations, aliases, and misspellings.
- Skipping the ingest Cron Trigger and calling the OFAC download URL inline on each payment — adds 300–800 ms latency and risks rate-limiting.
- Not recording the screening result and timestamp — audit regulators require proof-of-check per transaction.
- Using a 0.5 similarity threshold — generates too many false positives and blocks legitimate payments.

## Gotchas
- The OFAC consolidated XML can be 30+ MB; parse it in the Cron Worker (128 MB memory), not the request Worker (default 128 MB but shared with request handling overhead).
- KV has eventual consistency (up to 60 s globally); critical high-value payments should also hit a secondary authoritative API (e.g. Dow Jones, Refinitiv).
- SDN programs include non-US sanctions (CYBER, IRAN, RUSSIA); ensure your legal team maps which programs apply to your jurisdiction.
- Token sharding by 2-char prefix yields ~676 shards; with ~15 000 SDN entries this is manageable, but re-evaluate if the list grows beyond 100 000 entries.

## Verification
1. Seed KV with a test entry for "FAKE SANCTIONS TESTPERSON" uid `TEST001`.
2. POST `{"payerName":"Fake Testperson","payeeName":"Acme Corp","amountUsd":100}` to the gateway — expect `403 payment_blocked`.
3. POST with an unrelated name — expect `200 cleared`.
4. Query D1 `SELECT * FROM ofac_screen_log ORDER BY checked_at DESC LIMIT 5` to confirm audit rows.
5. Trigger the Cron Worker manually via `wrangler trigger schedule` and verify `sdn:updated_at` KV key is refreshed.

## Related
- [PCI DSS Scope Reduction via Tokenization](pci-dss-scope-reduction-tokenization.md)
- [AI/ML Fraud Risk Scoring](ai-ml-fraud-risk-scoring.md)
- [Payment Audit Logging](payment-audit-logging.md)
- [AML / Authorized Push Payment Fraud](authorized-push-payment-fraud-bec.md)

## Sources
- OFAC SDN List downloads: https://ofac.treasury.gov/sanctions-list-service
- 31 CFR Part 501 — OFAC Reporting, Procedures and Penalties
- Cloudflare Workers KV limits: https://developers.cloudflare.com/kv/platform/limits/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
