# NCII: Nonconsensual Intimate Imagery Detection & Hash-Matching Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project allows image uploads as anonymous posts. A survivor contacts trust & safety reporting that intimate images of them are being shared without consent (NCII / "revenge porn"). The platform must: (1) detect and remove the reported image immediately; (2) hash it and prevent re-upload; (3) optionally submit the hash to StopNCII.org for cross-platform matching; (4) preserve evidence for law enforcement if requested; (5) comply with the UK Online Safety Act (NCII designated content, s.66), US SHIELD Act, and emerging EU requirements.

## Context

NCII is distinct from CSAM: the subjects are adults, and the content may be legal in isolation but harmful in context. This means CSAM perceptual hash databases (PhotoDNA, NCMEC) do not apply — NCII requires a separate hash corpus (StopNCII). Workers AI can assist with nudity pre-screening to reduce false-positive burden on the hash-match pipeline, but Workers AI alone must never be the sole gate — hash-match confirmation is required before takedown.

Key difference from sextortion: sextortion involves an active threat actor; NCII handling begins with a survivor report and must centre survivor agency (including the right to request hash submission or opt out of cross-platform sharing).

## 1. NCII Report Intake & Evidence Preservation

```typescript
// src/ncii/intake.ts
import type { Env } from "../types";

export async function intakeNCIIReport(
  env: Env,
  params: {
    reporterSessionId: string;
    targetPostId: string;
    reporterStatement: string;    // free text from survivor
    contactConsent: boolean;      // survivor consented to be contacted by platform
    crossPlatformConsent: boolean; // survivor consents to StopNCII hash submission
  }
): Promise<string> {
  const reportId = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO ncii_reports
       (id, reporter_session_id, target_post_id, reporter_statement,
        contact_consent, cross_platform_consent, received_at, status)
     VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_review')`
  ).bind(
    reportId,
    params.reporterSessionId,
    params.targetPostId,
    params.reporterStatement,
    params.contactConsent ? 1 : 0,
    params.crossPlatformConsent ? 1 : 0,
    Date.now()
  ).run();

  // Immediately restrict visibility pending review (not full takedown yet)
  await env.DB.prepare(
    `UPDATE posts SET visibility = 'restricted', restriction_reason = 'ncii_pending'
     WHERE id = ?`
  ).bind(params.targetPostId).run();

  // Queue for expedited human review (NCII is high-priority)
  await env.MODERATION_QUEUE.send({
    type: "ncii_review",
    reportId,
    postId: params.targetPostId,
    priority: "high",
  });

  return reportId;
}
```

## 2. D1 Schema for NCII Registry

```sql
-- migration: 0046_ncii_registry.sql
CREATE TABLE ncii_reports (
  id                   TEXT PRIMARY KEY,
  reporter_session_id  TEXT NOT NULL,
  target_post_id       TEXT NOT NULL,
  reporter_statement   TEXT NOT NULL,
  contact_consent      INTEGER NOT NULL DEFAULT 0,
  cross_platform_consent INTEGER NOT NULL DEFAULT 0,
  received_at          INTEGER NOT NULL,
  reviewed_at          INTEGER,
  reviewed_by          TEXT,
  status               TEXT NOT NULL DEFAULT 'pending_review',
  takedown_at          INTEGER,
  evidence_r2_key      TEXT
);

CREATE TABLE ncii_hash_registry (
  id             TEXT PRIMARY KEY,
  ncii_report_id TEXT NOT NULL REFERENCES ncii_reports(id),
  hash_sha256    TEXT NOT NULL UNIQUE,   -- SHA-256 of original bytes
  hash_pdq       TEXT,                   -- PDQ perceptual hash for near-duplicate matching
  stop_ncii_id   TEXT,                  -- ID returned by StopNCII API
  submitted_at   INTEGER,
  r2_key         TEXT NOT NULL          -- sealed copy for law enforcement holds
);

CREATE INDEX idx_ncii_hash ON ncii_hash_registry (hash_sha256);
CREATE INDEX idx_ncii_pdq  ON ncii_hash_registry (hash_pdq);
```

## 3. Hash Computation & Upload Pre-Screening Worker

```typescript
// src/ncii/hash-and-screen.ts
export async function hashAndScreen(
  env: Env,
  imageBytes: ArrayBuffer,
  postId: string,
  nciiReportId: string
): Promise<{ matchFound: boolean; hashSha256: string }> {

  // 1. SHA-256 exact hash
  const hashBuf = await crypto.subtle.digest("SHA-256", imageBytes);
  const hashSha256 = Array.from(new Uint8Array(hashBuf))
    .map(b => b.toString(16).padStart(2, "0")).join("");

  // 2. Check against local NCII hash registry first (fast path)
  const existing = await env.DB.prepare(
    "SELECT id FROM ncii_hash_registry WHERE hash_sha256 = ?"
  ).bind(hashSha256).first();

  if (existing) {
    await takedownPost(env, postId, nciiReportId, hashSha256);
    return { matchFound: true, hashSha256 };
  }

  // 3. Workers AI nudity pre-screen (triage only — not a takedown gate)
  const aiResult = await env.AI.run("@cf/microsoft/resnet-50", {
    image: [...new Uint8Array(imageBytes)],
  }) as Array<{ label: string; score: number }>;

  const nudityScore = aiResult.find(r =>
    r.label.toLowerCase().includes("swim") ||
    r.label.toLowerCase().includes("bikini")
  )?.score ?? 0;

  // Flag for expedited human review if AI suggests explicit content
  if (nudityScore > 0.6) {
    await env.DB.prepare(
      `UPDATE ncii_reports SET status = 'expedited_review' WHERE id = ?`
    ).bind(nciiReportId).run();
  }

  // 4. Seal the image in R2 under legal hold regardless
  const r2Key = `ncii/sealed/${nciiReportId}/${hashSha256}.bin`;
  await env.LEGAL_BUCKET.put(r2Key, imageBytes, {
    customMetadata: { nciiReportId, postId, hashSha256 },
  });

  await env.DB.prepare(
    `INSERT INTO ncii_hash_registry (id, ncii_report_id, hash_sha256, r2_key)
     VALUES (?, ?, ?, ?)`
  ).bind(crypto.randomUUID(), nciiReportId, hashSha256, r2Key).run();

  return { matchFound: false, hashSha256 };
}

async function takedownPost(
  env: Env, postId: string, reportId: string, reason: string
): Promise<void> {
  const now = Date.now();
  await env.DB.prepare(
    `UPDATE posts SET visibility = 'taken_down', takedown_reason = 'ncii_hash_match'
     WHERE id = ?`
  ).bind(postId).run();
  await env.DB.prepare(
    `UPDATE ncii_reports SET status = 'taken_down', takedown_at = ? WHERE id = ?`
  ).bind(now, reportId).run();
}
```

## 4. StopNCII Hash Submission (With Survivor Consent Gate)

```typescript
// src/ncii/stopncii-submit.ts
export async function submitToStopNCII(
  env: Env,
  nciiReportId: string
): Promise<void> {
  const report = await env.DB.prepare(
    `SELECT r.*, h.hash_sha256, h.hash_pdq
     FROM ncii_reports r
     JOIN ncii_hash_registry h ON h.ncii_report_id = r.id
     WHERE r.id = ?`
  ).bind(nciiReportId).first<NCIIReportWithHash>();

  if (!report) throw new Error(`Report ${nciiReportId} not found`);
  if (!report.cross_platform_consent) {
    console.info("StopNCII submission skipped: survivor did not consent", nciiReportId);
    return;
  }

  const resp = await fetch("https://api.stopncii.org/v1/hashes", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.STOPNCII_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      hashValue: report.hash_sha256,
      hashType: "SHA256",
      sourceId: env.STOPNCII_SOURCE_ID,
    }),
  });

  if (!resp.ok) throw new Error(`StopNCII API error: ${resp.status}`);
  const { hashId } = await resp.json<{ hashId: string }>();

  await env.DB.prepare(
    `UPDATE ncii_hash_registry
     SET stop_ncii_id = ?, submitted_at = ?
     WHERE ncii_report_id = ?`
  ).bind(hashId, Date.now(), nciiReportId).run();
}
```

## 5. Re-Upload Prevention Gate

```typescript
// src/middleware/ncii-upload-gate.ts
export async function blockKnownNCIIHash(
  env: Env,
  imageBytes: ArrayBuffer
): Promise<{ blocked: boolean }> {
  const hashBuf = await crypto.subtle.digest("SHA-256", imageBytes);
  const hashSha256 = Array.from(new Uint8Array(hashBuf))
    .map(b => b.toString(16).padStart(2, "0")).join("");

  const hit = await env.DB.prepare(
    "SELECT id FROM ncii_hash_registry WHERE hash_sha256 = ?"
  ).bind(hashSha256).first();

  if (hit) {
    // Log re-upload attempt — pattern of re-uploads is evidence of coordinated abuse
    await env.DB.prepare(
      `INSERT INTO ncii_reupload_attempts (id, hash_sha256, attempted_at)
       VALUES (?, ?, ?)`
    ).bind(crypto.randomUUID(), hashSha256, Date.now()).run();
    return { blocked: true };
  }
  return { blocked: false };
}
```

## Anti-patterns

- **Auto-takedown on Workers AI nudity score alone** — AI classifiers produce false positives on swimwear, medical imagery, and art; always require hash-match or human confirmation.
- **Sharing the hash to StopNCII without survivor consent** — consent is legally required and survivor-agency is a core principle of NCII response.
- **Storing the image inline in D1** — D1 is not suitable for binary blobs; always use R2 with a sealed key.
- **Deleting the sealed image on takedown** — law enforcement requests and civil litigation may require preservation; keep in R2 under legal hold TTL.

## Gotchas

- `@cf/microsoft/resnet-50` classifies ImageNet categories, not explicit content per se — use label pattern matching as a rough proxy only.
- SHA-256 exact matching catches re-uploads of the exact binary; minor re-encoding (JPEG quality change) defeats it. PDQ perceptual hashing requires a C library not available in Workers — compute PDQ offline (e.g., in a Node.js Durable Object or external microservice) and store in `hash_pdq`.
- StopNCII API requires platform registration and a signed data-sharing agreement before keys are issued — initiate this process at legal@stopncii.org, not via the website form.
- UK OSA s.66 NCII designated content requires takedown within 24 hours of report for in-scope services; build SLA monitoring into `ncii_reports.received_at` vs `takedown_at`.

## Verification

```bash
# Confirm NCII hash registry exists
wrangler d1 execute example project-db --command \
  "SELECT COUNT(*) AS hashes FROM ncii_hash_registry;"

# Test re-upload blocking for a known hash
curl -X POST https://example project.example.com/api/upload \
  -F "file=@known_hash_test.jpg" | jq '.blocked'
# Expected: true

# SLA compliance check: reports not taken down within 24 h
wrangler d1 execute example project-db --command \
  "SELECT id, received_at, takedown_at,
     (takedown_at - received_at) / 3600000.0 AS hours_to_takedown
   FROM ncii_reports
   WHERE takedown_at IS NOT NULL AND (takedown_at - received_at) > 86400000;"
```

## Related

- `sextortion-detection-response-workers-ai-d1.md`
- `child-safety-perceptual-hash-matching-r2-workers.md`
- `877-csam-vendor-integration.md`
- `legal-hold-evidence-preservation-d1-r2.md`
- `grooming-pattern-detection-dms-workers-ai.md`

## Sources

- StopNCII — https://stopncii.org / API at https://api.stopncii.org
- UK Online Safety Act 2023, s.66 — NCII designated content
- US SHIELD Act 2019, H.R.2896
- CCRI (Cyber Civil Rights Initiative) — Best Practices for Platforms
- Meta Intimate Image Sharing Protocol (cross-platform hash sharing reference)
- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
