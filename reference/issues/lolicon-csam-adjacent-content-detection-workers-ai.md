# Lolicon and CSAM-Adjacent Content Detection with Workers AI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Illustrated or animated content depicting minors in sexualised contexts ("lolicon", "shotacon", and related drawn formats) is not always caught by perceptual-hash CSAM databases (PhotoDNA / GIFCT TCAP) because those databases index photographic material. Platforms that admit user-generated art must separately detect drawn CSAM-adjacent content that falls outside hash matching but violates platform policy and — in many jurisdictions — applicable law.

## Context

example project runs a dual-pass detection pipeline. Pass 1 is hash-based (covered in `child-safety-perceptual-hash-matching-r2-workers.md`). Pass 2, covered here, is classifier-based and handles non-photographic media: raster illustrations, vector art, manga panels, AI-generated art, and screenshot-style content where no hash match exists.

Detection feeds a verdict stored in D1. High-confidence positives are immediately removed and referred to the NCMEC CyberTipline via the existing 877-integration Worker. Medium-confidence cases enter a human review queue with a strict 4-hour SLA. All decisions are audit-logged immutably.

Legal note: the drawn-CSAM statutory landscape varies by jurisdiction (PROTECT Act in the US; Article 9 CRC Optional Protocol; national implementations). Platform policy takes the most restrictive applicable standard regardless of upload origin.

---

## Pre-classification: Image Metadata Extraction

```typescript
// workers/lolicon-detection/metadata.ts

export interface ImageMeta {
  width: number;
  height: number;
  mimeType: string;
  sizeBytes: number;
  r2Key: string;
}

/**
 * Reads image dimensions from R2 object custom metadata set at ingest.
 * We never re-fetch from the network here — metadata is set by the
 * ingest Worker at upload time and stored as R2 object metadata.
 */
export async function getImageMeta(r2Key: string, env: Env): Promise<ImageMeta | null> {
  const obj = await env.MEDIA_BUCKET.head(r2Key);
  if (!obj) return null;

  return {
    width: parseInt(obj.customMetadata?.['x-img-width'] ?? '0', 10),
    height: parseInt(obj.customMetadata?.['x-img-height'] ?? '0', 10),
    mimeType: obj.httpMetadata?.contentType ?? 'image/jpeg',
    sizeBytes: obj.size,
    r2Key,
  };
}
```

---

## Workers AI Classification — First-Pass Safety Check

```typescript
// workers/lolicon-detection/classify.ts
import { Env } from '../../types';

export type SafetyVerdict = 'safe' | 'csam_adjacent' | 'csam_definite' | 'review';

interface ClassificationResult {
  verdict: SafetyVerdict;
  confidence: number;  // 0.0–1.0
  modelLabels: Record<string, number>;
}

/**
 * Runs the image through Workers AI image classification.
 * Uses a two-model cascade: a fast general NSFW gate, then a
 * specialist minor-detection model for flagged items.
 */
export async function classifyImage(
  r2Key: string,
  env: Env
): Promise<ClassificationResult> {
  // Fetch image bytes from R2 (max 10 MB — enforced at ingest)
  const obj = await env.MEDIA_BUCKET.get(r2Key);
  if (!obj) throw new Error(`R2 object not found: ${r2Key}`);

  const imageBytes = await obj.arrayBuffer();

  // Stage 1: general NSFW model — fast filter
  const nsfwResult = await env.AI.run(
    '@cf/falconsai/nsfw_image_detection',
    { image: [...new Uint8Array(imageBytes)] }
  ) as { label: string; score: number }[];

  const nsfwScore = nsfwResult.find(r => r.label === 'nsfw')?.score ?? 0;

  // If clearly safe, skip expensive second pass
  if (nsfwScore < 0.3) {
    return { verdict: 'safe', confidence: 1 - nsfwScore, modelLabels: { nsfw: nsfwScore } };
  }

  // Stage 2: age-ambiguity classifier
  // Uses a fine-tuned vision model via the Workers AI gateway
  const ageResult = await env.AI.run(
    '@cf/microsoft/resnet-50',   // placeholder — replace with fine-tuned model ID
    { image: [...new Uint8Array(imageBytes)] }
  ) as Array<{ label: string; score: number }>;

  const labelMap = Object.fromEntries(ageResult.map(r => [r.label, r.score]));
  const minorIndicator = (labelMap['minor_sexualised'] ?? 0);

  let verdict: SafetyVerdict;
  if (minorIndicator >= 0.85) {
    verdict = 'csam_definite';
  } else if (minorIndicator >= 0.55 || nsfwScore >= 0.85) {
    verdict = 'csam_adjacent';
  } else if (minorIndicator >= 0.3) {
    verdict = 'review';
  } else {
    verdict = 'safe';
  }

  return {
    verdict,
    confidence: minorIndicator >= 0.55 ? minorIndicator : nsfwScore,
    modelLabels: { ...labelMap, nsfw: nsfwScore },
  };
}
```

---

## Verdict Persistence and Enforcement

```typescript
// workers/lolicon-detection/enforce.ts
import { Env } from '../../types';
import type { SafetyVerdict } from './classify';

export async function enforceVerdict(
  mediaId: string,
  r2Key: string,
  verdict: SafetyVerdict,
  confidence: number,
  modelLabels: Record<string, number>,
  env: Env
): Promise<void> {
  const now = Date.now();

  // Persist to D1 audit log
  await env.DB.prepare(
    `INSERT OR REPLACE INTO media_safety_verdicts
       (media_id, r2_key, verdict, confidence, model_labels, decided_at, reviewed)
     VALUES (?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    mediaId, r2Key, verdict, confidence,
    JSON.stringify(modelLabels), now,
    verdict === 'safe' || verdict === 'review' ? 0 : 1
  ).run();

  switch (verdict) {
    case 'csam_definite':
    case 'csam_adjacent':
      // Immediate removal: replace R2 object with a placeholder
      await env.MEDIA_BUCKET.put(r2Key, new Uint8Array(0), {
        customMetadata: { 'x-removed-reason': verdict, 'x-removed-at': String(now) },
      });
      // Enqueue CyberTip referral for csam_definite
      if (verdict === 'csam_definite') {
        await env.CYBERTIP_QUEUE.send({ mediaId, r2Key, confidence, decidedAt: now });
      }
      // Enqueue human review for csam_adjacent
      if (verdict === 'csam_adjacent') {
        await env.REVIEW_QUEUE.send({ mediaId, r2Key, confidence, sla: now + 4 * 3_600_000 });
      }
      break;

    case 'review':
      await env.REVIEW_QUEUE.send({ mediaId, r2Key, confidence, sla: now + 24 * 3_600_000 });
      break;

    case 'safe':
      // No action; audit row already written
      break;
  }
}
```

---

## D1 Schema

```sql
-- D1 migration: 0018_media_safety.sql
CREATE TABLE IF NOT EXISTS media_safety_verdicts (
  media_id      TEXT PRIMARY KEY,
  r2_key        TEXT NOT NULL,
  verdict       TEXT NOT NULL CHECK(verdict IN ('safe','csam_adjacent','csam_definite','review')),
  confidence    REAL NOT NULL,
  model_labels  TEXT NOT NULL DEFAULT '{}',
  decided_at    INTEGER NOT NULL,
  reviewed      INTEGER NOT NULL DEFAULT 0,   -- 0 = pending human review
  reviewer_id   TEXT,
  reviewer_note TEXT
);

CREATE INDEX idx_msv_verdict   ON media_safety_verdicts(verdict, decided_at DESC);
CREATE INDEX idx_msv_reviewed  ON media_safety_verdicts(reviewed, decided_at ASC);
```

---

## CyberTip Referral Consumer Worker

```typescript
// workers/cybertip-consumer.ts
// Processes the CYBERTIP_QUEUE and forwards to NCMEC Electronic Submission System

export default {
  async queue(batch: MessageBatch<CyberTipMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { mediaId, r2Key, confidence, decidedAt } = msg.body;

      try {
        // Retrieve media bytes for attachment (NCMEC ESS requires the file)
        const obj = await env.MEDIA_BUCKET.get(r2Key);
        if (!obj || obj.size === 0) {
          // Already purged or placeholder — send metadata-only tip
          await submitMetadataOnlyTip({ mediaId, confidence, decidedAt }, env);
        } else {
          const bytes = await obj.arrayBuffer();
          await submitFullTip({ mediaId, bytes, confidence, decidedAt }, env);
        }

        msg.ack();
      } catch (err) {
        // Retry up to 3 times; after that, alert on-call via PagerDuty webhook
        if (msg.attempts >= 3) {
          await env.ONCALL_QUEUE.send({ type: 'cybertip_failed', mediaId, error: String(err) });
          msg.ack(); // ack to avoid infinite loop; manual follow-up required
        } else {
          msg.retry();
        }
      }
    }
  },
};
```

---

## Anti-patterns

- **Relying solely on perceptual hash matching for illustrated content.** Hash databases index photographs; drawn content requires classifier-based detection running in parallel.
- **Blocking upload synchronously in the request path.** Classifier inference adds 200–800 ms. Run detection asynchronously post-upload; serve the asset as "pending review" until cleared.
- **Logging raw model label vectors in user-facing audit trails.** Keep raw classifier output in internal D1 tables only; surface only the final verdict in user-visible takedown notices.
- **Treating `csam_adjacent` and `csam_definite` identically in the enforcement path.** Adjacent content may still be legal in some jurisdictions; preserve a review queue so human reviewers can reverse misclassifications before the CyberTip is filed.

---

## Gotchas

- Workers AI image models accept images as `number[]` (byte array), not `ArrayBuffer` or `Uint8Array` directly. Spread with `[...new Uint8Array(buf)]`.
- R2 objects modified (zeroed) during removal retain their ETag and metadata. Downstream CDN caches may serve stale content for up to the object's Cache-Control TTL. Issue a Cache-Purge API call immediately after removal.
- The `@cf/falconsai/nsfw_image_detection` model is trained on photographic data and has lower precision on flat-colour illustrations. Treat its score as a tier-1 gate, not a final verdict.
- NCMEC ESS has a maximum file size of 50 MB per attachment. Enforce a 10 MB cap at upload time to stay well within the limit and leave headroom for HTTP envelope overhead.

---

## Verification

```bash
# Check verdict distribution over last 7 days
wrangler d1 execute example project-prod --command \
  "SELECT verdict, COUNT(*) as n FROM media_safety_verdicts
    WHERE decided_at > (strftime('%s','now') - 604800) * 1000
    GROUP BY verdict"

# Confirm no csam_definite rows remain unacked in CYBERTIP_QUEUE
wrangler queues consumer status cybertip-queue --env production

# Spot-check that removed objects are zeroed in R2
wrangler r2 object head example project-media-prod <r2_key_of_removed_item>
```

---

## Related

- `877-csam-vendor-integration.md`
- `child-safety-perceptual-hash-matching-r2-workers.md`
- `ncii-nonconsensual-intimate-imagery-detection-workers-ai.md`
- `age-verification-cloudflare-workers-kyc.md`
- `underage-user-detection-behavioral-signals.md`

---

## Sources

- NCMEC CyberTip Electronic Submission System — https://www.missingkids.org/gethelpnow/cybertipline
- GIFCT Hash-Sharing Database (TCAP) — https://gifct.org/tech/
- Cloudflare Workers AI image models — https://developers.cloudflare.com/workers-ai/models/
- PROTECT Act (18 U.S.C. § 1466A) — https://www.law.cornell.edu/uscode/text/18/1466A
- example project internal media-safety runbook v5 (internal wiki, 2026-Q1)
