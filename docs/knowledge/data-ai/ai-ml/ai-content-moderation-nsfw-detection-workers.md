# AI Content Moderation — NSFW Detection via Workers AI + Queue + R2 Quarantine

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project is a 21+ anonymous social platform — adult content is permitted within communities that opt in, but illegal content (CSAM, real-person non-consensual imagery) must never appear. Purely rule-based blocking (extension lists, file-size heuristics) fails against renamed or re-encoded uploads. Workers AI image classification runs at the Cloudflare edge, avoiding the latency and egress cost of sending images to a third-party moderation API while keeping classification logic inside the trust boundary.

## Context

The moderation pipeline is asynchronous: an upload Worker stores the image in R2 under a `pending/` prefix, enqueues a moderation job via Cloudflare Queues, and immediately returns a `202 Accepted` to the client. A consumer Worker dequeues the job, runs Workers AI classification, updates a D1 `moderation_status` row, and either promotes the image to `public/` or moves it to `quarantine/` in R2. The async design keeps upload latency under 150 ms regardless of model inference time.

---

## 1. Pipeline Architecture

```
 Client upload
      │ POST /upload (image bytes)
      ▼
 ┌────────────────────────┐
 │  upload.worker.ts      │
 │  1. Validate file type │
 │  2. Store → R2 pending/│
 │  3. Enqueue job        │──► Cloudflare Queue: moderation-jobs
 │  4. Return 202         │
 └────────────────────────┘

 ┌────────────────────────┐
 │  moderation.worker.ts  │◄── Queue consumer (batch size 5)
 │  1. Fetch from R2      │
 │  2. AI classify        │──► Workers AI: image classification
 │  3. Evaluate threshold │
 │  4a. PASS → R2 public/ │──► D1: status = 'approved'
 │  4b. FAIL → R2 quarant/│──► D1: status = 'quarantined'
 │  5. Notify uploader    │
 └────────────────────────┘
```

---

## 2. Upload Worker

```typescript
// src/workers/upload.ts
import { validateFileType } from '../lib/file-validation';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response(null, { status: 405 });

    const contentType = request.headers.get('Content-Type') ?? '';
    if (!contentType.startsWith('image/')) {
      return new Response('Only image uploads accepted', { status: 415 });
    }

    const bytes = await request.arrayBuffer();
    if (bytes.byteLength > 10 * 1024 * 1024) {
      return new Response('Image exceeds 10 MB limit', { status: 413 });
    }

    // Validate magic bytes — do not trust Content-Type header alone
    const mime = validateFileType(new Uint8Array(bytes));
    if (!mime) return new Response('Unsupported or invalid image format', { status: 415 });

    const uploaderId = request.headers.get('X-User-Id') ?? 'anon';
    const imageId = crypto.randomUUID();
    const r2Key = `pending/${imageId}`;

    // Store in R2 under pending/ — not yet publicly accessible
    await env.MEDIA_BUCKET.put(r2Key, bytes, {
      httpMetadata: { contentType: mime },
      customMetadata: { uploaderId, uploadedAt: Date.now().toString() },
    });

    // Enqueue moderation job
    await env.MODERATION_QUEUE.send({
      imageId,
      r2Key,
      uploaderId,
      communityId: request.headers.get('X-Community-Id') ?? '',
      mimeType: mime,
    });

    return new Response(JSON.stringify({ imageId, status: 'pending' }), {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## 3. Workers AI Image Classification

Workers AI provides image classification models that return label scores. For NSFW detection, use `@cf/microsoft/resnet-50` for coarse safe/unsafe filtering, then optionally use `@cf/llava-hf/llava-1.5-7b-hf` (vision-language model) for nuanced borderline cases.

```typescript
// src/lib/classify-image.ts
export interface ClassificationResult {
  label: string;
  score: number;
}

export async function classifyImage(
  imageBytes: ArrayBuffer,
  env: Env
): Promise<ClassificationResult[]> {
  const result = await env.AI.run('@cf/microsoft/resnet-50', {
    image: [...new Uint8Array(imageBytes)],
  });

  // result is ClassificationResult[] sorted by score descending
  return result as ClassificationResult[];
}

// For borderline cases: use VLM for contextual description
export async function describeImageForModeration(
  imageBytes: ArrayBuffer,
  env: Env
): Promise<string> {
  const result = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
    image: [...new Uint8Array(imageBytes)],
    prompt: 'Describe this image in detail. Note any explicit content, nudity, violence, or illegal activity.',
    max_tokens: 150,
  });
  return (result as { description: string }).description ?? '';
}
```

---

## 4. Threshold Calibration

ResNet-50 is a general classifier — its labels are ImageNet categories, not NSFW-specific. The moderation signal comes from **absence** of safe labels combined with a secondary LLM pass for uncertain cases.

```
Threshold strategy for example project:

┌──────────────────────────────┬───────────────┬──────────────────────────┐
│ Condition                    │ Action        │ Rationale                │
├──────────────────────────────┼───────────────┼──────────────────────────┤
│ Top label is known-safe ≥0.8 │ Auto-approve  │ High-confidence safe     │
│ Top label is known-safe <0.8 │ LLM-describe  │ Ambiguous — review       │
│ Top label is known-unsafe    │ Quarantine    │ Clear violation signal   │
│ LLM description hits keyword │ Quarantine    │ Contextual detection     │
│ LLM description is clean     │ Approve       │ LLM cleared ambiguous    │
└──────────────────────────────┴───────────────┴──────────────────────────┘

Known-safe ImageNet labels (excerpt):
  landscape, cityscape, food, animal, vehicle, sports, furniture

Known-unsafe labels trigger words (heuristic on description text):
  nude, naked, explicit, genitalia, sexual, illegal, weapon
```

```typescript
// src/lib/moderation-decision.ts
const KNOWN_SAFE_LABELS = new Set([
  'seashore', 'mountain', 'restaurant', 'pizza', 'dog', 'cat',
  'car', 'bicycle', 'laptop', 'desk', 'soccer', 'basketball',
]);

const UNSAFE_KEYWORDS = [
  /\bnude\b/i, /\bnaked\b/i, /\bexplicit\b/i, /\bgenitali/i,
  /\bsexual act/i, /\bcsam\b/i, /\bminor.*explicit/i,
];

export type ModerationDecision = 'approved' | 'quarantined' | 'needs_review';

export async function decideModerationOutcome(
  classifications: ClassificationResult[],
  env: Env,
  imageBytes: ArrayBuffer
): Promise<ModerationDecision> {
  const top = classifications[0];

  if (top && KNOWN_SAFE_LABELS.has(top.label) && top.score >= 0.8) {
    return 'approved';
  }

  // Ambiguous or unknown label — use VLM for secondary check
  const description = await describeImageForModeration(imageBytes, env);

  for (const pattern of UNSAFE_KEYWORDS) {
    if (pattern.test(description)) return 'quarantined';
  }

  return 'approved';
}
```

---

## 5. Queue Consumer Worker

```typescript
// src/workers/moderation.ts
interface ModerationJob {
  imageId: string;
  r2Key: string;
  uploaderId: string;
  communityId: string;
  mimeType: string;
}

export default {
  async queue(batch: MessageBatch<ModerationJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;

      try {
        // 1. Fetch image from R2 pending/
        const obj = await env.MEDIA_BUCKET.get(job.r2Key);
        if (!obj) {
          console.error(`R2 object not found: ${job.r2Key}`);
          msg.ack();
          continue;
        }
        const bytes = await obj.arrayBuffer();

        // 2. Classify
        const classifications = await classifyImage(bytes, env);

        // 3. Decision
        const decision = await decideModerationOutcome(classifications, env, bytes);

        if (decision === 'approved') {
          // Promote to public/
          const publicKey = `public/${job.imageId}`;
          await env.MEDIA_BUCKET.put(publicKey, bytes, {
            httpMetadata: { contentType: job.mimeType },
          });
          await env.MEDIA_BUCKET.delete(job.r2Key);
          await updateModerationStatus(env, job.imageId, 'approved', publicKey);
        } else {
          // Move to quarantine/ — strip metadata, log for human review
          const quarantineKey = `quarantine/${job.imageId}`;
          await env.MEDIA_BUCKET.put(quarantineKey, bytes, {
            customMetadata: {
              uploaderId: job.uploaderId,
              communityId: job.communityId,
              quarantinedAt: Date.now().toString(),
            },
          });
          await env.MEDIA_BUCKET.delete(job.r2Key);
          await updateModerationStatus(env, job.imageId, 'quarantined', quarantineKey);
          await notifyModerationTeam(env, job);
        }

        msg.ack();
      } catch (err) {
        console.error(`Moderation failed for ${job.imageId}:`, err);
        // Retry — do not ack; Queue retries with exponential backoff
        msg.retry();
      }
    }
  },
};

async function updateModerationStatus(
  env: Env,
  imageId: string,
  status: string,
  r2Key: string
): Promise<void> {
  await env.DB.prepare(
    `UPDATE media_uploads SET moderation_status = ?, r2_key = ?, moderated_at = ?
     WHERE image_id = ?`
  ).bind(status, r2Key, Date.now(), imageId).run();
}
```

---

## 6. R2 Access Control for Quarantined Content

```typescript
// Public-facing image Worker: block access to quarantine/ prefix
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1); // strip leading /

    // Strict prefix enforcement
    if (!key.startsWith('public/')) {
      return new Response('Not found', { status: 404 });
    }

    const obj = await env.MEDIA_BUCKET.get(key);
    if (!obj) return new Response('Not found', { status: 404 });

    return new Response(obj.body, {
      headers: {
        'Content-Type': obj.httpMetadata?.contentType ?? 'application/octet-stream',
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });
  },
};
```

Quarantine R2 objects are readable only via a separate admin Worker that requires a valid moderator JWT. Public media Worker never serves `pending/` or `quarantine/` keys.

---

## Anti-Patterns

- **Synchronous moderation on the upload path** — inference can take 500 ms–3 s; blocking the upload response causes timeouts on mobile.
- **Trusting `Content-Type` header for file type** — attackers submit `image/jpeg` headers with PDF or executable content; always validate magic bytes.
- **Deleting from R2 before D1 is updated** — if D1 write fails after R2 delete, the image is lost with no moderation record; always write D1 first.
- **Storing quarantined content without metadata** — losing uploader ID makes legal compliance (NCMEC reporting) impossible.
- **No retry budget** — Queue message that fails must be retried (don't `ack()` on error), but add a dead-letter queue after 5 attempts to avoid infinite loops.
- **Using the same R2 bucket path for pending and public** — a race between a slow moderation job and a public image request can expose a not-yet-approved image.

## Gotchas

- Workers AI `@cf/microsoft/resnet-50` expects `image: number[]` (Uint8Array spread), not a base64 string or URL.
- ResNet-50 was trained on ImageNet, not an adult-content dataset. Its labels are not NSFW-specific — the pipeline must use it as a coarse filter and rely on the VLM secondary pass for sexually explicit detection.
- Cloudflare Queues deliver messages **at least once** — the consumer must be idempotent. Use `image_id` as the idempotency key and check D1 status before re-processing.
- R2 `delete()` is **eventually consistent** — a brief window exists after delete where a GET of the old key may still return data. Do not rely on delete being instantaneous.
- `@cf/llava-hf/llava-1.5-7b-hf` has a **2 048-token input limit** including the image tokens. For images larger than ~1 MB, resize before passing to the VLM.

## Verification

```bash
# 1. Upload a test image
IMAGE_ID=$(curl -s -X POST https://api.example.com/upload \
  -H 'X-User-Id: test-user' \
  -H 'X-Community-Id: test-community' \
  -H 'Content-Type: image/jpeg' \
  --data-binary @test-safe.jpg | jq -r .imageId)

echo "Uploaded: $IMAGE_ID"

# 2. Poll moderation status (should resolve within ~5s)
sleep 5
curl -s "https://api.example.com/media/status/$IMAGE_ID" | jq .

# Expected for safe image:
# { "status": "approved", "r2Key": "public/<uuid>" }

# 3. Confirm public image is accessible
curl -I "https://media.example.com/public/$IMAGE_ID.jpg"
# Expected: HTTP 200

# 4. Confirm pending is gone
curl -I "https://media.example.com/pending/$IMAGE_ID.jpg"
# Expected: HTTP 404
```

## Related

- `ai-content-moderation-pipeline.md` — text moderation pipeline
- `workers-ai-text-classification-moderation.md` — text classification with Workers AI
- `ai-output-filtering.md` — filtering AI-generated content
- `cloudflare-workers-ai-streaming-inference.md` — Workers AI binding patterns
- `ai-safety-guardrails-implementation.md` — broader safety pipeline

## Sources

- Cloudflare Workers AI image models: developers.cloudflare.com/workers-ai/models
- Cloudflare Queues: developers.cloudflare.com/queues
- Cloudflare R2: developers.cloudflare.com/r2
- NCMEC CyberTipline reporting requirements: missingkids.org/gethelpnow/cybertipline
- ImageNet label taxonomy: image-net.org/challenges/LSVRC/2012
