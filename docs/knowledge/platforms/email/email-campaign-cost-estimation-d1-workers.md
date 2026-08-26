# Email Campaign Cost Estimation — D1 + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You send email through multiple ESPs (MailChannels, Resend, SendGrid) with different per-message or per-GB pricing, and you have no single view of what each campaign costs before or after send. Finance wants monthly accruals. Engineering wants pre-flight budget checks that block campaigns exceeding a cost threshold. You need a system that estimates send cost from list size and ESP pricing, records actuals as sends complete, and exposes both in a D1-backed reporting API.

## Context

ESP pricing models vary widely: some charge per 1000 emails, others per GB of outbound data, others per recipient per month. Accurately modelling this requires knowing your list size, average message size (HTML + attachments), and the current rate card for each ESP. Workers handle cost calculation at pre-flight time and record actuals after each batch, with D1 as the source of truth for budget vs. actuals.

---

## 1. D1 schema

```sql
CREATE TABLE esp_rate_cards (
  id          TEXT PRIMARY KEY,
  esp_name    TEXT NOT NULL,             -- 'mailchannels' | 'resend' | 'sendgrid'
  model       TEXT NOT NULL,             -- 'per_message' | 'per_gb' | 'per_recipient_month'
  unit_cost   REAL NOT NULL,             -- USD per unit
  unit        TEXT NOT NULL,             -- 'message' | 'gb' | 'recipient'
  effective   TEXT NOT NULL,             -- ISO date rate card becomes active
  UNIQUE(esp_name, effective)
);

CREATE TABLE campaign_cost_estimates (
  campaign_id   TEXT PRIMARY KEY,
  esp_name      TEXT NOT NULL,
  recipient_count INTEGER NOT NULL,
  avg_message_bytes INTEGER NOT NULL,
  estimated_cost REAL NOT NULL,
  budget_limit  REAL,
  approved      INTEGER NOT NULL DEFAULT 0,  -- boolean
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE campaign_cost_actuals (
  id            TEXT PRIMARY KEY,
  campaign_id   TEXT NOT NULL,
  batch_id      TEXT NOT NULL,
  messages_sent INTEGER NOT NULL DEFAULT 0,
  bytes_sent    INTEGER NOT NULL DEFAULT 0,
  cost_incurred REAL NOT NULL DEFAULT 0,
  recorded_at   TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (campaign_id) REFERENCES campaign_cost_estimates(campaign_id)
);

CREATE INDEX idx_actuals_campaign ON campaign_cost_actuals(campaign_id);
```

## 2. Seed the rate card

```typescript
async function upsertRateCard(
  db: D1Database,
  esp: string,
  model: "per_message" | "per_gb",
  unitCost: number,
  unit: string
): Promise<void> {
  await db.prepare(`
    INSERT INTO esp_rate_cards (id, esp_name, model, unit_cost, unit, effective)
    VALUES (?, ?, ?, ?, ?, date('now'))
    ON CONFLICT(esp_name, effective) DO UPDATE SET unit_cost = excluded.unit_cost
  `).bind(crypto.randomUUID(), esp, model, unitCost, unit).run();
}

// MailChannels free tier → 0; Resend: $0.80/1000; SendGrid $0.0006/email
await upsertRateCard(db, "resend",    "per_message", 0.0008, "message");
await upsertRateCard(db, "sendgrid",  "per_message", 0.0006, "message");
await upsertRateCard(db, "mailchannels", "per_message", 0.0, "message");
```

## 3. Pre-flight cost estimate

```typescript
interface CostEstimate {
  estimatedCost: number;
  withinBudget: boolean;
  breakdown: {
    recipientCount: number;
    avgMessageBytes: number;
    unitCost: number;
    model: string;
  };
}

async function estimateCampaignCost(
  db: D1Database,
  campaignId: string,
  espName: string,
  recipientCount: number,
  sampleHtml: string,
  budgetLimit?: number
): Promise<CostEstimate> {
  const card = await db.prepare(`
    SELECT * FROM esp_rate_cards
    WHERE esp_name = ? AND effective <= date('now')
    ORDER BY effective DESC LIMIT 1
  `).bind(espName).first<EspRateCard>();

  if (!card) throw new Error(`No rate card found for ${espName}`);

  const avgBytes = new TextEncoder().encode(sampleHtml).length;
  let estimatedCost = 0;

  if (card.model === "per_message") {
    estimatedCost = recipientCount * card.unit_cost;
  } else if (card.model === "per_gb") {
    const totalGb = (recipientCount * avgBytes) / (1024 ** 3);
    estimatedCost = totalGb * card.unit_cost;
  }

  await db.prepare(`
    INSERT INTO campaign_cost_estimates
      (campaign_id, esp_name, recipient_count, avg_message_bytes, estimated_cost, budget_limit)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(campaign_id) DO UPDATE SET
      estimated_cost = excluded.estimated_cost,
      budget_limit = excluded.budget_limit
  `).bind(campaignId, espName, recipientCount, avgBytes, estimatedCost, budgetLimit ?? null).run();

  return {
    estimatedCost,
    withinBudget: budgetLimit == null || estimatedCost <= budgetLimit,
    breakdown: { recipientCount, avgMessageBytes: avgBytes, unitCost: card.unit_cost, model: card.model },
  };
}
```

## 4. Record actuals after each batch

```typescript
async function recordBatchCost(
  db: D1Database,
  campaignId: string,
  batchId: string,
  messagesSent: number,
  totalBytes: number,
  espName: string
): Promise<void> {
  const card = await db.prepare(`
    SELECT * FROM esp_rate_cards WHERE esp_name = ?
    ORDER BY effective DESC LIMIT 1
  `).bind(espName).first<EspRateCard>();

  const costIncurred = card?.model === "per_message"
    ? messagesSent * (card?.unit_cost ?? 0)
    : (totalBytes / 1024 ** 3) * (card?.unit_cost ?? 0);

  await db.prepare(`
    INSERT INTO campaign_cost_actuals
      (id, campaign_id, batch_id, messages_sent, bytes_sent, cost_incurred)
    VALUES (?, ?, ?, ?, ?, ?)
  `).bind(crypto.randomUUID(), campaignId, batchId, messagesSent, totalBytes, costIncurred).run();
}
```

## 5. Cost summary API

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const campaignId = url.searchParams.get("campaignId");
    const month = url.searchParams.get("month"); // YYYY-MM

    if (campaignId) {
      const estimate = await env.DB.prepare(
        "SELECT * FROM campaign_cost_estimates WHERE campaign_id = ?"
      ).bind(campaignId).first();

      const actuals = await env.DB.prepare(`
        SELECT
          SUM(messages_sent)  AS total_messages,
          SUM(bytes_sent)     AS total_bytes,
          SUM(cost_incurred)  AS total_cost
        FROM campaign_cost_actuals WHERE campaign_id = ?
      `).bind(campaignId).first();

      return Response.json({ estimate, actuals });
    }

    if (month) {
      // Monthly rollup
      const rollup = await env.DB.prepare(`
        SELECT
          e.esp_name,
          COUNT(DISTINCT a.campaign_id)   AS campaigns,
          SUM(a.messages_sent)            AS total_messages,
          SUM(a.cost_incurred)            AS total_cost
        FROM campaign_cost_actuals a
        JOIN campaign_cost_estimates e ON e.campaign_id = a.campaign_id
        WHERE strftime('%Y-%m', a.recorded_at) = ?
        GROUP BY e.esp_name
      `).bind(month).all();

      return Response.json(rollup.results);
    }

    return new Response("Provide campaignId or month param", { status: 400 });
  },
};
```

---

## Anti-patterns

- **Computing costs from live ESP billing APIs on every preflight** — those APIs are slow and rate-limited; use a local D1 rate card updated nightly via cron.
- **Blocking sends on cost estimates alone without an approval gate** — the `approved` flag in `campaign_cost_estimates` should require an explicit operator sign-off for campaigns above a threshold.
- **Storing costs only at campaign level** — batch-level granularity lets you detect mid-campaign anomalies (e.g. a retry storm doubling costs).
- **Not accounting for markup from sub-account pass-through** — if you resell email services, store a `markup_multiplier` on `esp_rate_cards` and apply it in the estimate.

## Gotchas

- Message byte counts vary with personalisation — sample five random recipients, average their rendered sizes, and use that for estimates; do not use the bare template size.
- ESP rate cards change without notice; automate a weekly scrape of your ESP's pricing page and diff against the stored card.
- D1's `REAL` type stores IEEE 754 doubles — for financial precision in large campaigns, store cost in microdollars (`INTEGER`) and divide at display time.
- MailChannels is free on Workers but has volume limits; include a fallback ESP in your model to capture cost if volume overflows to a paid relay.

## Verification

1. Create an estimate for a known list of 10,000 recipients at $0.0008/message; confirm `estimated_cost = 8.00`.
2. Record two batches of 5,000 each; confirm `total_cost` in the actuals query equals the estimate.
3. Check monthly rollup for the current month returns correct ESP breakdown.
4. Confirm that an `estimated_cost` exceeding `budget_limit` returns `withinBudget: false` without blocking the insert.

## Related

- `email-batch-sending.md`
- `email-campaign-throttling-queues.md`
- `email-esp-failover-health-check-workers.md`
- `email-resend-batch-broadcast-workers-queues.md`

## Sources

- https://resend.com/pricing
- https://sendgrid.com/pricing/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
