# GIFCT Hash Sharing and Terrorist Content TCAP Compliance

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A platform receives uploaded images and videos that may contain terrorist or violent extremist content. Membership in GIFCT (Global Internet Forum to Counter Terrorism) and compliance with the EU Terrorist Content Action Protocol (TCAP / Regulation 2021/784) require hash-matching against a shared database and removal within one hour of a verified referral.

## Context
GIFCT maintains a shared hash database (PDQ for images, TMK+PDQF for video) of terrorist content. On upload, each asset is hashed and checked against the GIFCT Hash Sharing Database (HSDB). EU Regulation 2021/784 additionally mandates that platforms act on removal orders from competent national authorities within 60 minutes, with audit logs proving timely action. This pipeline handles both proactive HSDB matching and reactive TCAP order processing on Cloudflare Workers.

## Perceptual Hash Computation at Upload

GIFCT recommends PDQ (Facebook's perceptual difference hash) for images. A WASM build of the PDQ reference implementation runs inside the Worker to produce a 256-bit hex hash without egress to a third-party service.

```typescript
// worker: upload-hash.ts
import { computePDQ } from "./pdq-wasm"; // WASM module bundled via wrangler

export interface Env {
  DB: D1Database;
  UPLOAD_BUCKET: R2Bucket;
  HASH_QUEUE: Queue;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const formData = await req.formData();
    const file = formData.get("file") as File;
    if (!file) return new Response("missing file", { status: 400 });

    const buffer = await file.arrayBuffer();
    const pdqHash = await computePDQ(new Uint8Array(buffer));
    const assetId = crypto.randomUUID();

    // Store asset and hash atomically
    await Promise.all([
      env.UPLOAD_BUCKET.put(assetId, buffer, {
        httpMetadata: { contentType: file.type },
        customMetadata: { pdqHash },
      }),
      env.DB.prepare(
        `INSERT INTO asset_hashes (asset_id, pdq_hash, uploaded_at, status)
         VALUES (?, ?, ?, 'pending_check')`
      ).bind(assetId, pdqHash, new Date().toISOString()).run(),
    ]);

    await env.HASH_QUEUE.send({ assetId, pdqHash });
    return Response.json({ assetId, status: "pending" });
  },
};
```

## GIFCT HSDB Lookup via Queue Consumer

The hash check runs asynchronously in a Queue consumer that calls the GIFCT HSDB API (mTLS-authenticated). Matches trigger immediate asset withholding and a NCMEC/Europol referral record.

```typescript
// worker: hsdb-checker.ts
export interface Env {
  DB: D1Database;
  UPLOAD_BUCKET: R2Bucket;
  GIFCT_API_KEY: string; // secret binding
}

interface HashJob {
  assetId: string;
  pdqHash: string;
}

export default {
  async queue(batch: MessageBatch<HashJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { assetId, pdqHash } = msg.body;

      const hsdbRes = await fetch("https://api.gifct.org/v1/hash/check", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GIFCT_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ hash: pdqHash, algorithm: "PDQ" }),
      });

      const { matched, confidence, category } = await hsdbRes.json<{
        matched: boolean;
        confidence: number;
        category: string;
      }>();

      if (matched && confidence >= 0.9) {
        // Withhold asset and log referral
        await env.DB.prepare(
          `UPDATE asset_hashes SET status = 'withheld', category = ?, detected_at = ?
           WHERE asset_id = ?`
        ).bind(category, new Date().toISOString(), assetId).run();

        await env.DB.prepare(
          `INSERT INTO tcap_referrals (asset_id, pdq_hash, category, reported_at, status)
           VALUES (?, ?, ?, ?, 'pending')`
        ).bind(assetId, pdqHash, category, new Date().toISOString()).run();

        // Delete from public R2 path immediately
        await env.UPLOAD_BUCKET.delete(`public/${assetId}`);
      } else {
        await env.DB.prepare(
          `UPDATE asset_hashes SET status = 'clear' WHERE asset_id = ?`
        ).bind(assetId).run();
      }

      msg.ack();
    }
  },
};
```

## TCAP Removal Order Ingestion (EU Regulation 2021/784)

National competent authorities send removal orders via a standardised API endpoint. The Worker validates the authority's token, records the order, and must complete removal within 60 minutes. An alarm is set via Durable Objects to fail-safe if human operators have not confirmed action in time.

```typescript
// worker: tcap-order.ts
export interface Env {
  DB: D1Database;
  UPLOAD_BUCKET: R2Bucket;
  ORDER_DO: DurableObjectNamespace;
  AUTHORITY_TOKENS: KVNamespace;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const authToken = <redacted-secret>"X-Authority-Token") ?? "";
    const authorityId = await env.AUTHORITY_TOKENS.get(authToken);
    if (!authorityId) return new Response("Unauthorized", { status: 401 });

    const { orderId, assetIds, issuedAt } = await req.json<{
      orderId: string;
      assetIds: string[];
      issuedAt: string;
    }>();

    const deadline = new Date(issuedAt);
    deadline.setMinutes(deadline.getMinutes() + 55); // 5-min safety buffer

    for (const assetId of assetIds) {
      await env.UPLOAD_BUCKET.delete(`public/${assetId}`);
      await env.DB.prepare(
        `UPDATE asset_hashes SET status = 'tcap_removed', removed_at = ?
         WHERE asset_id = ?`
      ).bind(new Date().toISOString(), assetId).run();
    }

    await env.DB.prepare(
      `INSERT INTO tcap_orders (order_id, authority_id, asset_count, issued_at, complied_at)
       VALUES (?, ?, ?, ?, ?)`
    ).bind(orderId, authorityId, assetIds.length, issuedAt, new Date().toISOString()).run();

    // Set a Durable Object alarm to alert if audit log is incomplete
    const stub = env.ORDER_DO.get(env.ORDER_DO.idFromName(orderId));
    await stub.fetch(
      new Request(`https://do/alarm?orderId=${orderId}&deadline=${deadline.toISOString()}`)
    );

    return Response.json({ orderId, status: "complied" });
  },
};
```

## Audit Log Export for Regulatory Submission

Regulators require a machine-readable audit trail. A cron worker exports all TCAP order compliance records to a signed R2 object that authorities can retrieve.

```typescript
// worker: tcap-audit-export.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const { results } = await env.DB.prepare(
      `SELECT order_id, authority_id, asset_count, issued_at, complied_at,
              (julianday(complied_at) - julianday(issued_at)) * 1440 AS minutes_to_comply
       FROM tcap_orders
       WHERE DATE(issued_at) = DATE('now', '-1 day')`
    ).all();

    const reportKey = `tcap-audit/${new Date().toISOString().slice(0, 10)}.json`;
    await env.UPLOAD_BUCKET.put(reportKey, JSON.stringify(results, null, 2), {
      httpMetadata: { contentType: "application/json" },
    });
  },
};
```

## Anti-patterns
- Storing original terrorist content anywhere on-platform "for evidence" without an isolated evidence vault — even temporarily retained copies must be encrypted, access-logged, and air-gapped from the public bucket
- Using exact cryptographic hashes (MD5/SHA-256) instead of perceptual hashes — perpetrators re-encode content to defeat exact matching
- Processing TCAP orders synchronously in the ingest worker — use a Queue to decouple and ensure the order is acknowledged even if removal takes multiple steps
- Silently discarding HSDB API errors — treat an HSDB API failure as a circuit-breaker condition and halt uploads until the service recovers

## Gotchas
- PDQ hashes are distance-compared (Hamming distance ≤ 31), not equality-compared — the GIFCT API handles this server-side, but your local pre-filter must not use `===`
- The GIFCT HSDB API returns HTTP 429 during high-load events; implement exponential backoff with jitter in the Queue consumer
- TCAP orders must be responded to within 1 hour of *receipt*, not of the issue timestamp — log `received_at` separately from `issued_at`
- Deleting from R2 is eventually consistent; CDN cache for the public URL may still serve the asset for up to the configured TTL — send a Cache Purge API call immediately after deletion

## Verification
1. Submit a test image whose PDQ hash is pre-registered in a staging HSDB endpoint; confirm `status = 'withheld'` in D1 and the R2 key is deleted.
2. POST a synthetic TCAP order and verify `complied_at` is within 60 seconds of `issued_at` in the audit log.
3. Run the audit export cron and confirm a JSON file appears in the R2 bucket with correct `minutes_to_comply` values.
4. Simulate an HSDB 429 response and assert the Queue message is nacked and retried.

## Related
- [`877-csam-vendor-integration.md`](877-csam-vendor-integration.md)
- [`hash-based-duplicate-content-detection-r2.md`](hash-based-duplicate-content-detection-r2.md)
- [`emergency-content-takedown-circuit-breaker-queues.md`](emergency-content-takedown-circuit-breaker-queues.md)
- [`platform-audit-log-immutable-d1-workers.md`](platform-audit-log-immutable-d1-workers.md)

## Sources
- EU Regulation 2021/784 on addressing the dissemination of terrorist content online (TCAP)
- GIFCT Hash-Sharing Database technical specification v2.1 (2024)
- PDQ perceptual hash algorithm — Meta Research (https://github.com/faizann24/pdq)
- Cloudflare R2 Cache Purge API documentation
