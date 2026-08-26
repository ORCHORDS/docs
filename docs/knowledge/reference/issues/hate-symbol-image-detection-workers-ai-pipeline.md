# Hate Symbol Detection in Images — Workers AI Vision Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Users on example project upload images — profile pictures, post attachments, story frames — that contain
hate symbols, extremist insignia, or coded visual signals (e.g. numeric codes used as white-power
shorthand). Text moderation passes clean because the offending content is rasterised into the image
rather than expressed as text. Existing hash-matching (PhotoDNA / CSAM perceptual hashing) covers
known child-safety images but is blind to hate-symbol imagery unless a vetted corpus exists.

---

## Context

Hate symbol imagery spans a broad spectrum:

- **Well-known banned symbols** — swastikas, SS runes, certain cross variants used by extremist
  groups, Confederate battle flag in harassment context.
- **Coded numeric / alphanumeric** — "14 words", "88", "1488" rendered as image text.
- **Dog-whistle imagery** — pepe variants, "okay" hand gesture in specific colour/context combos,
  celtic knotwork used by specific movements.
- **Redacted or partial** — symbols partially obscured by emoji or overlays to evade pixel hashes.

Workers AI (`@cf/meta/llama-3.2-11b-vision-instruct` or `@cf/openai/clip`) can classify image
content. The pipeline chains: upload → object detection → vision-language model (VLM) prompt →
confidence scoring → queue for human review or auto-action.

Regulatory context: DSA Art. 16 requires expeditious action on illegal content; some EU member
states explicitly ban specific symbols. GIFCT hash-sharing covers terrorist imagery but not all
hate symbols.

---

## Architecture Overview

```
Upload → R2 (raw)
       → Queues (image-scan-queue)
           → Workers AI (CLIP embedding similarity)
           → Workers AI (VLM caption/classify)
           → D1 (verdicts table)
           → Queues (action-queue)
               → shadow-restrict / takedown / human-review
```

---

## Implementation

### 1. Upload Handler — enqueue for async scanning

```typescript
// src/handlers/upload.ts
import type { Env } from '../types';

export async function handleImageUpload(
  request: Request,
  env: Env,
): Promise<Response> {
  const formData = await request.formData();
  const file = formData.get('file') as File | null;
  if (!file || !file.type.startsWith('image/')) {
    return new Response('Invalid file', { status: 400 });
  }

  const imageId = crypto.randomUUID();
  const r2Key = `uploads/${imageId}`;

  // Store raw bytes in R2
  await env.IMAGES_BUCKET.put(r2Key, await file.arrayBuffer(), {
    httpMetadata: { contentType: file.type },
    customMetadata: { uploadedAt: new Date().toISOString() },
  });

  // Enqueue for hate-symbol scan (non-blocking)
  await env.IMAGE_SCAN_QUEUE.send({
    imageId,
    r2Key,
    uploader: request.headers.get('CF-Connecting-IP') ?? 'unknown',
    uploadedAt: Date.now(),
  });

  return Response.json({ imageId, status: 'pending_review' });
}
```

### 2. Queue Consumer — vision classification

```typescript
// src/consumers/image-scan.ts
import type { Env } from '../types';

interface ScanMessage {
  imageId: string;
  r2Key: string;
  uploader: string;
  uploadedAt: number;
}

// Prompt crafted to elicit structured symbol recognition
const HATE_SYMBOL_PROMPT = `
You are a content moderation classifier. Examine this image carefully.

Respond ONLY with a JSON object using this exact schema:
{
  "contains_hate_symbol": boolean,
  "symbol_description": string | null,
  "confidence": number,         // 0.0 – 1.0
  "category": "nazi" | "white_supremacist" | "extremist_numeric" | "coded_signal" | "none",
  "reasoning": string
}

Be conservative — only flag imagery that clearly depicts or prominently features hate symbols.
Partial or ambiguous occurrences should be flagged with confidence below 0.6.
`.trim();

export async function processImageScan(
  batch: MessageBatch<ScanMessage>,
  env: Env,
): Promise<void> {
  for (const msg of batch.messages) {
    try {
      await scanImage(msg.body, env);
      msg.ack();
    } catch (err) {
      console.error(`Scan failed for ${msg.body.imageId}:`, err);
      msg.retry();
    }
  }
}

async function scanImage(payload: ScanMessage, env: Env): Promise<void> {
  // Fetch image bytes from R2
  const obj = await env.IMAGES_BUCKET.get(payload.r2Key);
  if (!obj) {
    console.warn(`R2 object missing: ${payload.r2Key}`);
    return;
  }
  const imageBytes = new Uint8Array(await obj.arrayBuffer());

  // Run VLM classification
  const aiResponse = await env.AI.run(
    '@cf/meta/llama-3.2-11b-vision-instruct',
    {
      prompt: HATE_SYMBOL_PROMPT,
      image: [...imageBytes],
    },
  );

  let verdict: Record<string, unknown>;
  try {
    const raw = (aiResponse as { response: string }).response;
    verdict = JSON.parse(raw);
  } catch {
    // Fallback: treat unparseable response as inconclusive
    verdict = {
      contains_hate_symbol: false,
      confidence: 0,
      category: 'none',
      reasoning: 'parse_error',
    };
  }

  const confidence = Number(verdict.confidence ?? 0);
  const flagged = Boolean(verdict.contains_hate_symbol) && confidence >= 0.5;

  // Persist verdict to D1
  await env.DB.prepare(
    `INSERT INTO image_verdicts
       (image_id, r2_key, flagged, confidence, category, reasoning, scanned_at)
     VALUES (?, ?, ?, ?, ?, ?, unixepoch())`,
  )
    .bind(
      payload.imageId,
      payload.r2Key,
      flagged ? 1 : 0,
      confidence,
      String(verdict.category ?? 'none'),
      String(verdict.reasoning ?? ''),
    )
    .run();

  if (flagged) {
    await dispatchAction(payload.imageId, confidence, env);
  }
}

async function dispatchAction(
  imageId: string,
  confidence: number,
  env: Env,
): Promise<void> {
  // High confidence → auto-restrict immediately
  // Low-medium confidence → human review queue
  const action = confidence >= 0.85 ? 'auto_restrict' : 'human_review';
  await env.ACTION_QUEUE.send({ imageId, action, triggeredAt: Date.now() });
}
```

### 3. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS image_verdicts (
  image_id    TEXT PRIMARY KEY,
  r2_key      TEXT NOT NULL,
  flagged     INTEGER NOT NULL DEFAULT 0,  -- boolean: 0 | 1
  confidence  REAL NOT NULL DEFAULT 0.0,
  category    TEXT NOT NULL DEFAULT 'none',
  reasoning   TEXT,
  scanned_at  INTEGER NOT NULL,
  reviewed_by TEXT,                        -- moderator ID after human review
  final_action TEXT                        -- 'approved' | 'removed' | 'escalated'
);

CREATE INDEX idx_image_verdicts_flagged ON image_verdicts(flagged, confidence DESC);
CREATE INDEX idx_image_verdicts_scanned ON image_verdicts(scanned_at DESC);
```

### 4. Types

```typescript
// src/types.ts
export interface Env {
  AI: Ai;
  DB: D1Database;
  IMAGES_BUCKET: R2Bucket;
  IMAGE_SCAN_QUEUE: Queue<ScanMessage>;
  ACTION_QUEUE: Queue<ActionMessage>;
}
```

---

## Anti-patterns

- **Synchronous classification in the upload handler** — image VLM inference can take 2–8 s; always
  defer to a Queue consumer. Returning a `200` with `status: pending_review` is correct.
- **Passing image URLs to the VLM** — the Workers AI vision endpoint requires base64 or raw bytes
  inline. Do not pass an R2 public URL; the model sandbox cannot make outbound fetch calls.
- **Single-model confidence as ground truth** — VLM outputs vary by image compression, cropping,
  and prompt phrasing. Always funnel borderline cases (0.5–0.85) to human review rather than
  auto-removing.
- **Storing full image bytes in D1** — D1 rows have a 1 MB limit and are not designed for BLOBs.
  Keep images in R2; store only the key reference in D1.

---

## Gotchas

- `llama-3.2-11b-vision-instruct` requires the `image` field to be a `number[]` (not `Uint8Array`
  directly). Spread `[...new Uint8Array(buffer)]` before passing.
- R2 `.get()` returns `null` for missing keys — always null-check before calling `.arrayBuffer()`.
- Workers AI responses are not guaranteed to be valid JSON even when you instruct JSON output.
  Always wrap `JSON.parse()` in try/catch and fall back to an inconclusive verdict.
- Queue retries on uncaught errors — ensure idempotency: check `image_verdicts` for an existing row
  before re-scanning to avoid duplicate AI inference charges.
- The 30 s CPU wall-clock limit applies per Worker invocation. A Queue consumer processing a large
  image batch may need `max_batch_size: 1` with `max_batch_timeout: 25` to stay within limits.

---

## Verification

```typescript
// Manual test: upload a known test image and poll the verdict
async function verifyPipeline(imageId: string, env: Env): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT flagged, confidence, category FROM image_verdicts WHERE image_id = ?`,
  ).bind(imageId).first<{ flagged: number; confidence: number; category: string }>();

  if (!row) {
    console.log('Verdict not yet written — queue may not have processed');
    return;
  }
  console.log('Verdict:', row);
}

// Integration test assertion
// expect(row.flagged).toBe(1);
// expect(row.confidence).toBeGreaterThan(0.7);
// expect(['nazi', 'white_supremacist']).toContain(row.category);
```

Health check query for ops dashboards:

```sql
-- Flagged images in the last 24 hours by category
SELECT category, COUNT(*) AS cnt, AVG(confidence) AS avg_confidence
FROM image_verdicts
WHERE flagged = 1 AND scanned_at > unixepoch() - 86400
GROUP BY category
ORDER BY cnt DESC;
```

---

## Related

- `hate-speech-detection-multilingual-workers-ai.md` — text-based hate speech pipeline
- `deepfake-detection-workers-ai-pipeline.md` — image authenticity checks
- `child-safety-perceptual-hash-matching-r2-workers.md` — PhotoDNA hash-matching
- `gifct-hash-sharing-terrorist-content-tcap.md` — hash-sharing with industry partners
- `dog-whistle-coded-language-detection-workers-ai.md` — coded language in text

---

## Sources

- Cloudflare Workers AI — Vision models: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Queues — Consumer configuration: https://developers.cloudflare.com/queues/configuration/
- DSA Art. 16 — Notice and action mechanism
- GIFCT Terrorist Content Analytics Platform (TCAP): https://gifct.org/tcap/
- Global Internet Forum to Counter Terrorism hash-sharing programme
