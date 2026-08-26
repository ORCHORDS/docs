# Deepfake Detection Pipeline — Workers AI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Users upload profile photos, video clips, and reaction GIFs to example project A subset are
AI-generated faces or voice-cloned audio designed to impersonate real people or fabricate
consent. Left undetected, these assets fuel disinformation, romance fraud, and non-consensual
intimate imagery (NCII). Operators must intercept synthetic media at ingest before it is
distributed to followers.

## Context

Workers AI provides on-edge inference without egress to a third-party GPU farm. The pipeline
chains three signals: (1) image classifier scoring via Workers AI, (2) a metadata probe for
GAN telltale EXIF absence, and (3) a perceptual hash block-list lookup in D1. A Cloudflare
Queue absorbs upload bursts so the ingest Worker never exhausts its 30 s CPU wall-time
processing video frames synchronously.

## 1. Image Deepfake Scoring at Ingest

```typescript
// workers/deepfake-detect.ts
export interface Env {
  AI: Ai;
  DEEPFAKE_SCORES: KVNamespace;
  UPLOAD_QUEUE: Queue<{ assetId: string; r2Key: string }>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const formData = await request.formData();
    const file = formData.get('file') as File | null;
    if (!file) return new Response('Missing file', { status: 400 });

    const buffer = await file.arrayBuffer();

    // Run deepfake classification via Workers AI image classifier
    const result = await env.AI.run('@cf/microsoft/resnet-50', {
      image: [...new Uint8Array(buffer)],
    });

    // With a fine-tuned deepfake head, scores[0] is the synthetic probability
    const score = result.scores?.[0] ?? 0;
    const isSuspect = score > 0.72;

    const assetId = crypto.randomUUID();
    await env.DEEPFAKE_SCORES.put(assetId, JSON.stringify({ score, isSuspect }), {
      expirationTtl: 86400,
    });

    if (isSuspect) {
      await env.UPLOAD_QUEUE.send({ assetId, r2Key: `uploads/${assetId}` });
      return new Response(JSON.stringify({ assetId, status: 'quarantined', score }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({ assetId, status: 'approved', score }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

## 2. EXIF Metadata Probe for GAN Artifacts

GAN and diffusion outputs typically carry no camera EXIF block — a lightweight pre-filter
before the AI call.

```typescript
function hasNoCamera(buffer: ArrayBuffer): boolean {
  const view = new DataView(buffer);
  // Not a JPEG — skip probe
  if (view.getUint16(0) !== 0xffd8) return false;
  let offset = 2;
  while (offset < view.byteLength - 1) {
    const marker = view.getUint16(offset);
    const length = view.getUint16(offset + 2);
    if (marker === 0xffe1) return false; // EXIF APP1 present — real camera likely
    if (marker === 0xffda) break;        // SOS marker — stop scanning
    offset += 2 + length;
  }
  return true; // no EXIF block found → suspicious
}
```

## 3. Perceptual Hash Block-list via D1

```typescript
// workers/phash-lookup.ts
export interface Env {
  DB: D1Database;
}

async function pHashBlocked(env: Env, pHash: string): Promise<boolean> {
  const row = await env.DB.prepare(
    'SELECT 1 FROM deepfake_blocklist WHERE phash = ?1 LIMIT 1',
  ).bind(pHash).first();
  return row !== null;
}

async function recordHash(env: Env, pHash: string, assetId: string): Promise<void> {
  await env.DB.prepare(
    `INSERT OR IGNORE INTO deepfake_blocklist (phash, asset_id, detected_at)
     VALUES (?1, ?2, ?3)`,
  ).bind(pHash, assetId, new Date().toISOString()).run();
}
```

## 4. Queue Consumer for Async Frame Analysis

```typescript
// workers/deepfake-queue-consumer.ts
export interface Env {
  AI: Ai;
  BUCKET: R2Bucket;
  DB: D1Database;
}

export default {
  async queue(batch: MessageBatch<{ assetId: string; r2Key: string }>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { assetId, r2Key } = msg.body;
      const obj = await env.BUCKET.get(r2Key);
      if (!obj) { msg.ack(); continue; }

      const buffer = await obj.arrayBuffer();
      const result = await env.AI.run('@cf/microsoft/resnet-50', {
        image: [...new Uint8Array(buffer)],
      });
      const score = result.scores?.[0] ?? 0;

      await env.DB.prepare(
        `INSERT INTO deepfake_reviews (asset_id, score, reviewed_at)
         VALUES (?1, ?2, ?3)
         ON CONFLICT (asset_id) DO UPDATE SET score = ?2`,
      ).bind(assetId, score, new Date().toISOString()).run();

      if (score > 0.9) {
        await env.DB.prepare(
          'UPDATE assets SET status = ?1 WHERE id = ?2',
        ).bind('removed', assetId).run();
      }
      msg.ack();
    }
  },
} satisfies ExportedHandler<Env>;
```

## 5. Human-Review Escalation Gate

```typescript
// Score band routing: 0.72–0.90 → human queue; >0.90 → auto-remove
async function escalateToReview(
  env: { DB: D1Database },
  assetId: string,
  score: number,
): Promise<void> {
  const tier = score > 0.9 ? 'auto_remove' : 'human_review';
  await env.DB.prepare(
    `INSERT INTO moderation_queue (asset_id, reason, tier, queued_at)
     VALUES (?1, ?2, ?3, ?4)`,
  ).bind(assetId, 'deepfake_suspect', tier, new Date().toISOString()).run();
}
```

## Anti-patterns

- Running full-image AI inference synchronously inside the ingest `fetch` handler — use Queues to offload heavy frames and avoid 30 s wall-time exhaustion.
- Trusting a single model score in isolation; GAN detectors have high false-positive rates on artistic filters — combine with EXIF probe and perceptual hash for defence-in-depth.
- Storing raw biometric embeddings in D1 without encryption — use Workers Secrets or envelope keys; embeddings are personal data under GDPR Article 9.
- Blocking uploads entirely on classifier timeout — quarantine and async-review; overly strict ingest gates destroy legitimate UX.

## Gotchas

- `@cf/microsoft/resnet-50` is a general image classifier; you must fine-tune or swap to a deepfake-specific model checkpoint for meaningful precision — the pipeline shape above is model-agnostic.
- Workers AI image input expects a `number[]` array (pixel bytes), not a `Blob` or `ReadableStream`; convert with `[...new Uint8Array(buffer)]`.
- D1 `INSERT OR IGNORE` on the block-list requires a UNIQUE constraint on `phash`; add it in your migration: `CREATE UNIQUE INDEX idx_phash ON deepfake_blocklist (phash);`
- Queue consumer CPU budget is independent of the ingest Worker; each message invocation still counts against its own 30 s CPU limit.

## Verification

```bash
# Upload a known GAN face (e.g. from a StyleGAN3 sample set)
curl -X POST https://your-worker.workers.dev/ \
  -F "file=@stylegan3_sample.jpg"
# Expect: { "status": "quarantined", "score": 0.81 }

# Confirm D1 review row after queue consumer processes the asset
wrangler d1 execute YOUR_DB --command \
  "SELECT * FROM deepfake_reviews ORDER BY reviewed_at DESC LIMIT 5;"

# Confirm block-list row
wrangler d1 execute YOUR_DB --command \
  "SELECT * FROM deepfake_blocklist ORDER BY detected_at DESC LIMIT 5;"
```

## Related

- `deepfake-detection-policy-2026.md`
- `eu-ai-act-article-50-deepfakes-2026.md`
- `hash-based-duplicate-content-detection-r2.md`
- `real-time-toxic-content-scoring-workers-ai.md`
- `emergency-content-takedown-circuit-breaker-queues.md`
- `ai-watermarking-provenance-c2pa-2026.md`

## Sources

- Cloudflare Workers AI documentation: https://developers.cloudflare.com/workers-ai/
- C2PA / Content Credentials specification: https://c2pa.org/specifications/
- FotoForensics GAN detection research: https://fotoforensics.com/research.php
- GIFCT Hash-Sharing TCAP integration: https://gifct.org/tech/
- EU AI Act Article 50 — synthetic media obligations: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689
