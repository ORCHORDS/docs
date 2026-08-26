# Self-Harm and Graphic Content Image Moderation with Workers AI

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A platform that accepts user-uploaded images must prevent storage and distribution of self-harm imagery, graphic violence, and child sexual abuse material (CSAM). The inspection must happen before R2 storage so that prohibited content never persists, with a human appeal workflow for false positives and mandatory NCMEC CyberTipline reporting for CSAM detections.

## Context

The pre-storage inspection pattern places a Cloudflare Worker between the upload client and R2. The Worker:

1. Receives the image stream and classifies it using Workers AI (`@cf/microsoft/resnet-50` or a custom LoRA adapter for domain-specific content).
2. Rejects prohibited content before any write to R2.
3. Writes an audit record to D1 `content_moderation_log`.
4. Routes borderline detections to a human review queue via a Durable Object.
5. For confirmed CSAM, submits an automated CyberTipline report to NCMEC via their ESP API.

## Pre-Storage Inspection Worker

```typescript
import { Ai } from '@cloudflare/ai';

export interface Env {
  R2: R2Bucket;
  DB: D1Database;
  AI: Ai;
  REVIEW_DO: DurableObjectNamespace;
  NCMEC_API_KEY: string;         // Workers secret
  NCMEC_REPORTER_ID: string;     // Workers secret
  PLATFORM_DOMAIN: string;
}

const REJECT_THRESHOLD  = 0.80; // auto-reject above this score
const REVIEW_THRESHOLD  = 0.45; // send to human review above this

const PROHIBITED_LABELS = new Set([
  'self-harm', 'blood', 'graphic-violence', 'nudity', 'explicit',
]);

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (req.method !== 'PUT' || !new URL(req.url).pathname.startsWith('/upload/')) {
      return new Response('not found', { status: 404 });
    }

    const assetId = crypto.randomUUID();
    const uploaderUserId = req.headers.get('X-User-Id') ?? 'unknown';

    // 1. Buffer the image (limit to 10 MB)
    const MAX_BYTES = 10 * 1024 * 1024;
    const contentLength = parseInt(req.headers.get('Content-Length') ?? '0', 10);
    if (contentLength > MAX_BYTES) {
      return new Response('payload too large', { status: 413 });
    }
    const imageBytes = await req.arrayBuffer();
    if (imageBytes.byteLength > MAX_BYTES) {
      return new Response('payload too large', { status: 413 });
    }

    // 2. Classify with Workers AI
    const classifyResult = await (env.AI as any).run(
      '@cf/microsoft/resnet-50',
      { image: [...new Uint8Array(imageBytes)] },
    ) as { label: string; score: number }[];

    // Map ResNet labels to our policy categories using a lookup table
    const scoresJson = mapToPolicyScores(classifyResult);
    const maxProhibited = Math.max(
      ...Object.entries(scoresJson)
        .filter(([label]) => PROHIBITED_LABELS.has(label))
        .map(([, score]) => score),
      0,
    );

    const isCSAM    = (scoresJson['nudity'] ?? 0) > 0.9 && (scoresJson['minor'] ?? 0) > 0.7;
    const autoReject = maxProhibited >= REJECT_THRESHOLD || isCSAM;
    const sendReview = !autoReject && maxProhibited >= REVIEW_THRESHOLD;

    const action = autoReject ? 'rejected' : sendReview ? 'review' : 'approved';

    // 3. Write audit log to D1
    await env.DB.prepare(`
      INSERT INTO content_moderation_log
        (asset_id, uploader_id, model, scores_json, action, reviewed_at)
      VALUES (?, ?, '@cf/microsoft/resnet-50', ?, ?, NULL)
    `).bind(
      assetId, uploaderUserId,
      JSON.stringify(scoresJson),
      action,
    ).run();

    // 4. Store in R2 only if approved or under review
    if (!autoReject) {
      await env.R2.put(assetId, imageBytes, {
        httpMetadata: { contentType: req.headers.get('Content-Type') ?? 'application/octet-stream' },
        customMetadata: { uploader: uploaderUserId, moderation_status: action },
      });
    }

    // 5. Enqueue for human review if borderline
    if (sendReview) {
      const doId = env.REVIEW_DO.idFromName('image-review-queue');
      ctx.waitUntil(
        env.REVIEW_DO.get(doId).fetch('https://internal/enqueue', {
          method: 'POST',
          body: JSON.stringify({ asset_id: assetId, scores_json: scoresJson, uploader_id: uploaderUserId }),
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }

    // 6. NCMEC CyberTipline reporting for CSAM
    if (isCSAM) {
      ctx.waitUntil(reportToNCMEC(env, assetId, uploaderUserId, scoresJson));
    }

    if (autoReject) {
      return new Response(
        isCSAM ? 'Content violates platform policy (CSAM)' : 'Content violates platform policy',
        { status: 451 }, // 451 Unavailable For Legal Reasons
      );
    }

    return Response.json({ asset_id: assetId, status: action });
  },
};

function mapToPolicyScores(results: { label: string; score: number }[]): Record<string, number> {
  // ResNet-50 returns ImageNet labels; map to policy categories
  const mapping: Record<string, string> = {
    'Band Aid':      'self-harm',
    'knife':         'graphic-violence',
    'cleaver':       'graphic-violence',
    // extend with domain-specific LoRA adapter labels
  };
  const out: Record<string, number> = {};
  for (const { label, score } of results) {
    const mapped = mapping[label];
    if (mapped) out[mapped] = Math.max(out[mapped] ?? 0, score);
    else out[label] = score;
  }
  return out;
}

async function reportToNCMEC(
  env: Env, assetId: string, uploaderId: string, scores: Record<string, number>,
): Promise<void> {
  // NCMEC Electronic Service Provider (ESP) API
  // See: https://www.missingkids.org/gethelpnow/cybertipline/esp
  await fetch('https://api.missingkids.org/cybertipline/v1/report', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${env.NCMEC_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      reporterEspId: env.NCMEC_REPORTER_ID,
      platform: env.PLATFORM_DOMAIN,
      incidentTime: new Date().toISOString(),
      userId: uploaderId,
      contentId: assetId,
      classifierScores: scores,
    }),
  });
  // Log that a report was filed (do NOT store image content in this log)
  // The D1 content_moderation_log row written earlier with action='rejected' is the audit trail.
}
```

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS content_moderation_log (
  asset_id     TEXT PRIMARY KEY,
  uploader_id  TEXT NOT NULL,
  model        TEXT NOT NULL,
  scores_json  TEXT NOT NULL,
  action       TEXT NOT NULL,    -- approved | review | rejected
  reviewed_at  INTEGER,          -- NULL until a human moderator acts
  appeal_id    TEXT              -- set when uploader files an appeal
);

CREATE INDEX IF NOT EXISTS idx_cml_action ON content_moderation_log (action, rowid DESC);
```

## Human Review Queue (Durable Object)

```typescript
export class ImageReviewQueue {
  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/enqueue') {
      const item = await req.json();
      const queue: unknown[] = (await this.state.storage.get('queue')) ?? [];
      queue.push({ ...item, enqueued_at: Date.now() });
      await this.state.storage.put('queue', queue);
      return Response.json({ ok: true, depth: queue.length });
    }

    if (url.pathname === '/next') {
      const queue: unknown[] = (await this.state.storage.get('queue')) ?? [];
      const item = queue.shift();
      await this.state.storage.put('queue', queue);
      return Response.json({ item: item ?? null, remaining: queue.length });
    }

    if (url.pathname === '/resolve') {
      // Moderator POSTs { asset_id, verdict: 'approved' | 'rejected' }
      const { asset_id, verdict } = await req.json<{ asset_id: string; verdict: string }>();
      await this.env.DB.prepare(
        'UPDATE content_moderation_log SET action = ?, reviewed_at = unixepoch() WHERE asset_id = ?',
      ).bind(verdict, asset_id).run();

      if (verdict === 'rejected') {
        await this.env.R2.delete(asset_id); // remove from storage on rejection
      }
      return Response.json({ ok: true });
    }

    return new Response('not found', { status: 404 });
  }
}
```

## Appeal Workflow

Uploaders who believe a rejection is incorrect can file an appeal:

1. Client POSTs to `/appeal` with `asset_id` and a short statement.
2. Worker creates an `appeal_id`, sets `appeal_id` in `content_moderation_log`, and re-enqueues the asset in the Durable Object review queue with the appeal context attached.
3. A human moderator reviews the original AI scores alongside the appeal statement and calls `/resolve` with `approved` or `rejected`.
4. The uploader is notified via email (MailChannels) with the outcome.

## Anti-patterns

- **Classifying after R2 write** — prohibited content will be stored even briefly; always classify in the upload stream before any write.
- **Using only ResNet-50 for CSAM detection** — ResNet-50 is a general-purpose classifier, not a CSAM detector; combine with PhotoDNA or a purpose-built model and treat CSAM thresholds very conservatively.
- **Logging the image bytes in D1** — `content_moderation_log` must contain only metadata and scores, never image data.
- **Auto-approving appeals** — appeals must go to a human queue; do not let the AI model auto-approve its own false positives.

## Gotchas

- ResNet-50 expects images as a flat `number[]` (pixel array); convert `ArrayBuffer` using `new Uint8Array(imageBytes)` spread into an array.
- NCMEC reporting is legally mandatory in the US under 18 U.S.C. § 2258A for ESP operators who obtain actual knowledge of CSAM; failure to report is a criminal offense.
- Durable Object storage is limited to 128 KB per key; for large review queues, paginate with multiple keys or use a D1 queue table instead.
- R2 `delete` in the resolve handler is idempotent but returns no error if the object does not exist — safe to call.
- The 451 HTTP status code ("Unavailable For Legal Reasons") is the recommended response for content blocked for legal compliance per RFC 7725.

## Verification

```bash
# Check moderation action distribution
wrangler d1 execute example project-db --command \
  "SELECT action, COUNT(*) AS cnt FROM content_moderation_log GROUP BY action;"

# Find items awaiting human review
wrangler d1 execute example project-db --command \
  "SELECT asset_id, scores_json, appeal_id FROM content_moderation_log WHERE action = 'review' ORDER BY rowid DESC LIMIT 20;"

# Confirm rejected objects not in R2
wrangler r2 object get example project-uploads <asset_id_of_rejected>
# Expected: R2StorageError: The specified key does not exist.
```

## Related

- `mental-health-crisis-escalation-pipeline-workers-ai.md`
- Cloudflare R2 — pre-storage inspection pattern
- Cloudflare Durable Objects — queue patterns
- NCMEC CyberTipline ESP program

## Sources

- Cloudflare Workers AI: https://developers.cloudflare.com/workers-ai/
- Cloudflare R2: https://developers.cloudflare.com/r2/
- NCMEC CyberTipline for ESPs: https://www.missingkids.org/gethelpnow/cybertipline/esp
- 18 U.S.C. § 2258A — CSAM reporting obligation
- RFC 7725 — HTTP 451 Unavailable For Legal Reasons
