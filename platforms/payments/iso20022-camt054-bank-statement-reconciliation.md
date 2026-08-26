# ISO 20022 camt.054 Bank Statement Reconciliation on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Platforms that receive payments via SEPA, SWIFT, or Open Banking feeds need to reconcile incoming bank credits against pending orders in near real-time. ISO 20022 `camt.054` (Bank-to-Customer Debit Credit Notification) is the standard message delivered by banks as an intraday or end-of-day notification.

## Context
`camt.054` XML messages are delivered by banks via EBICS, SFTP, or API (e.g. Deutsche Bank db API, ABN AMRO Tikkie). Each file contains one or more `Ntfctn` (Notification) elements grouping `TxDtls` (Transaction Detail) entries. Cloudflare Workers parse the XML, extract transaction identifiers, and reconcile against D1 order records by matching the payment reference in `RmtInf/Ustrd` or structured reference `RmtInf/Strd/CdtrRefInf/Ref`.

## Parsing camt.054 XML

Workers do not have DOM APIs; use a lightweight streaming XML parser bundled into the Worker.

```typescript
// camt054-parser.ts
// Uses txml (https://github.com/TobiasNickel/tXml) bundled as ESM

interface CamtTransaction {
  msgId: string;
  notificationId: string;
  entryRef: string;
  valueDate: string;    // YYYY-MM-DD
  creditDebit: "CRDT" | "DBIT";
  amountMinor: number;  // in minor units (cents)
  currency: string;     // ISO 4217
  remittanceUnstructured?: string;
  remittanceStructuredRef?: string;
  counterpartyName?: string;
  counterpartyIban?: string;
  endToEndId?: string;
}

export function parseCamt054(xml: string): CamtTransaction[] {
  // Minimal regex-based extraction; replace with txml for production
  const results: CamtTransaction[] = [];

  const notifBlocks = [...xml.matchAll(/<Ntfctn>([\s\S]*?)<\/Ntfctn>/g)];
  for (const [, notifBody] of notifBlocks) {
    const msgId = extract(xml, "MsgId") ?? "unknown";
    const notificationId = extract(notifBody, "Id") ?? crypto.randomUUID();

    const txBlocks = [...notifBody.matchAll(/<TxDtls>([\s\S]*?)<\/TxDtls>/g)];
    for (const [, txBody] of txBlocks) {
      const cdtDbt = extract(txBody, "CdtDbtInd") as "CRDT" | "DBIT" | undefined;
      const amtStr = extract(txBody, "Amt");
      const ccy = txBody.match(/<Amt Ccy="([A-Z]{3})">/)?.[1];
      const amountMinor = amtStr ? Math.round(parseFloat(amtStr) * 100) : 0;

      results.push({
        msgId,
        notificationId,
        entryRef: extract(txBody, "NtryRef") ?? crypto.randomUUID(),
        valueDate: extract(txBody, "ValDt") ?? extract(txBody, "Dt") ?? "",
        creditDebit: cdtDbt ?? "CRDT",
        amountMinor,
        currency: ccy ?? "EUR",
        remittanceUnstructured: extract(txBody, "Ustrd"),
        remittanceStructuredRef: extract(txBody, "Ref"),
        counterpartyName: extract(txBody, "Nm"),
        counterpartyIban: extract(txBody, "IBAN"),
        endToEndId: extract(txBody, "EndToEndId"),
      });
    }
  }

  return results;
}

function extract(xml: string, tag: string): string | undefined {
  return xml.match(new RegExp(`<${tag}[^>]*>([^<]+)<\/${tag}>`))?.[1]?.trim();
}
```

## Ingesting Notifications via Webhook or SFTP Poll

Banks can push `camt.054` files as webhooks (base64-encoded XML body) or deposit them via SFTP. The following handles a webhook delivery.

```typescript
// camt054-ingest.ts
import type { D1Database, KVNamespace } from "@cloudflare/workers-types";
import { parseCamt054 } from "./camt054-parser";

interface Env {
  BANK_WEBHOOK_SECRET: string;
  DB: D1Database;
  PROCESSED_KV: KVNamespace;   // deduplication store
}

export async function handleCamtWebhook(req: Request, env: Env): Promise<Response> {
  const authHeader = req.headers.get("Authorization") ?? "";
  if (!timingSafeEqual(authHeader, `Bearer ${env.BANK_WEBHOOK_SECRET}`)) {
    return new Response("Unauthorized", { status: 401 });
  }

  const body = await req.json<{ xmlBase64: string }>();
  const xml = atob(body.xmlBase64);

  const transactions = parseCamt054(xml);

  for (const tx of transactions) {
    if (tx.creditDebit !== "CRDT") continue;   // only process incoming credits

    // Idempotency: skip already-processed entries
    const dedupKey = `camt:${tx.notificationId}:${tx.entryRef}`;
    const already = await env.PROCESSED_KV.get(dedupKey);
    if (already) continue;

    await reconcileTransaction(tx, env.DB);
    await env.PROCESSED_KV.put(dedupKey, "1", { expirationTtl: 7_776_000 }); // 90 days
  }

  return new Response("ok");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
```

## Reconciliation Logic

Match incoming credits to pending orders using the payment reference, then update order state.

```typescript
// reconcile.ts
import type { D1Database } from "@cloudflare/workers-types";
import type { CamtTransaction } from "./camt054-parser";

interface OrderRow {
  id: string;
  expected_amount_minor: number;
  currency: string;
  status: string;
}

export async function reconcileTransaction(
  tx: CamtTransaction,
  db: D1Database
): Promise<void> {
  // Extract order reference from unstructured remittance (e.g. "ORDER-8472")
  const ref = tx.remittanceStructuredRef
    ?? extractOrderRef(tx.remittanceUnstructured ?? "");

  if (!ref) {
    await flagUnmatched(tx, db, "no_reference");
    return;
  }

  const order = await db.prepare(
    "SELECT id, expected_amount_minor, currency, status FROM orders WHERE payment_ref = ? AND status = 'pending_payment'"
  )
    .bind(ref)
    .first<OrderRow>();

  if (!order) {
    await flagUnmatched(tx, db, "no_matching_order");
    return;
  }

  if (order.currency !== tx.currency) {
    await flagUnmatched(tx, db, "currency_mismatch");
    return;
  }

  const amountOk = Math.abs(tx.amountMinor - order.expected_amount_minor) <= 1; // ±1 cent rounding
  if (!amountOk) {
    await flagUnmatched(tx, db, "amount_mismatch");
    return;
  }

  await db.batch([
    db.prepare("UPDATE orders SET status = 'paid', paid_at = CURRENT_TIMESTAMP WHERE id = ?")
      .bind(order.id),
    db.prepare(
      `INSERT INTO bank_credits (entry_ref, notification_id, order_id, amount_minor,
         currency, value_date, counterparty_iban, matched_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
    ).bind(tx.entryRef, tx.notificationId, order.id, tx.amountMinor, tx.currency,
           tx.valueDate, tx.counterpartyIban ?? null),
  ]);
}

async function flagUnmatched(
  tx: CamtTransaction,
  db: D1Database,
  reason: string
): Promise<void> {
  await db.prepare(
    `INSERT OR IGNORE INTO unmatched_credits
       (entry_ref, notification_id, amount_minor, currency, reason, received_at)
     VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)`
  )
    .bind(tx.entryRef, tx.notificationId, tx.amountMinor, tx.currency, reason)
    .run();
}

function extractOrderRef(remittance: string): string | null {
  const m = remittance.match(/ORDER-([A-Z0-9]{4,12})/i);
  return m ? `ORDER-${m[1].toUpperCase()}` : null;
}
```

## Anti-patterns
- Parsing `camt.054` with a full DOM parser (DOMParser) — not available in Workers; always bundle a lightweight XML parser.
- Matching solely on amount — amounts are not unique; always combine amount + reference + currency.
- Not storing unmatched credits — they represent real incoming money that must be manually reconciled or refunded.
- Processing the same notification file twice — use KV deduplication keyed on `MsgId + NtryRef`.
- Treating `Dt` (booking date) as value date — use `ValDt` when present for accurate settlement day accounting.

## Gotchas
- `camt.054` and `camt.053` (statement) have overlapping but not identical schemas; confirm with your bank which message type they send intraday vs. end-of-day.
- Some banks send one file per transaction, others batch thousands; the parser must handle both.
- German IBAN format includes spaces in human-readable form (`DE89 3704 0044 ...`); normalise before matching by stripping spaces.
- The `<Amt Ccy="...">` attribute carries the currency, not a child element — regex must parse the attribute, not a child tag.

## Verification
1. Generate a synthetic `camt.054` XML with two CRDT entries matching existing `orders` rows.
2. POST the base64-encoded XML to the ingest endpoint; confirm `orders.status = 'paid'` for both rows.
3. Re-POST the same file — confirm no duplicate processing (KV deduplication).
4. Post a file with a CRDT entry referencing a non-existent order reference — confirm row appears in `unmatched_credits`.
5. Query: `SELECT reason, COUNT(*) FROM unmatched_credits GROUP BY reason` to monitor ongoing match rates.

## Related
- [Payment Reconciliation and Settlement](payment-reconciliation-settlement.md)
- [SEPA Direct Debit Return Handling](sepa-direct-debit-return-handling.md)
- [Double Entry Ledger for Payments](double-entry-ledger-payments.md)
- [Open Banking Pay-by-Bank Integration](open-banking-pay-by-bank-integration.md)

## Sources
- ISO 20022 camt.054 message definition: https://www.iso20022.org/iso-20022-message-definitions?search=camt.054
- Deutsche Bundesbank EBICS specification: https://www.ebics.de/en/
- txml lightweight XML parser: https://github.com/TobiasNickel/tXml
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
