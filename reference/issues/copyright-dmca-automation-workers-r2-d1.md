# Copyright DMCA Automation With Workers, R2, and D1

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project users upload images, audio clips, and video snippets without attribution, and rights-holders send DMCA takedown notices at a growing rate. Processing each notice manually is slow, legally risky (DMCA requires a response within "expeditious" time), and error-prone. The platform needs an automated intake-to-takedown pipeline that validates notices, identifies matching content across R2, records the chain of custody in D1, and issues counter-notice workflows — all without a separate backend server.

## Context

Under 17 U.S.C. §512, platforms must act on valid DMCA notices "expeditiously" or lose safe harbor protection. Cloudflare Workers handle inbound notices via a dedicated endpoint, R2 stores uploaded media with hash-based metadata for fingerprint matching, and D1 maintains the audit trail of every notice, match, removal, and counter-notice. Workers AI provides lightweight image/audio similarity scoring to catch derivative works that evade exact-hash matching.

## Detection — Inbound Notice Validation and Hash Matching

A Worker receives DMCA notice submissions (JSON or multipart), validates required fields (copyright owner, work description, infringing URLs, good-faith declaration), and runs a perceptual hash match against R2 object metadata.

```typescript
// workers/dmca-intake.ts
export interface Env {
  DB: D1Database;
  MEDIA_BUCKET: R2Bucket;
  AI: Ai;
}

interface DmcaNotice {
  claimantName: string;
  claimantEmail: string;
  workDescription: string;
  infringingUrls: string[];
  goodFaithDeclaration: boolean;
  accuracyDeclaration: boolean;
  signature: string;
}

function validateNotice(notice: DmcaNotice): string[] {
  const errors: string[] = [];
  if (!notice.claimantName?.trim()) errors.push("claimant_name required");
  if (!notice.claimantEmail?.includes("@")) errors.push("valid claimant_email required");
  if (!notice.workDescription?.trim()) errors.push("work_description required");
  if (!notice.infringingUrls?.length) errors.push("infringing_urls required");
  if (!notice.goodFaithDeclaration) errors.push("good_faith_declaration required");
  if (!notice.accuracyDeclaration) errors.push("accuracy_declaration required");
  if (!notice.signature?.trim()) errors.push("signature required");
  return errors;
}

async function extractContentIds(urls: string[]): Promise<string[]> {
  // Extract content IDs from platform URLs, e.g. https://example.com/p/{contentId}
  return urls
    .map(url => {
      const match = url.match(/\/p\/([a-z0-9-]+)/i);
      return match?.[1] ?? null;
    })
    .filter((id): id is string => id !== null);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const notice = await request.json<DmcaNotice>();
    const errors = validateNotice(notice);
    if (errors.length > 0) {
      return new Response(JSON.stringify({ valid: false, errors }), { status: 400 });
    }

    // Record the notice
    const noticeId = crypto.randomUUID();
    await env.DB.prepare(
      `INSERT INTO dmca_notices
         (notice_id, claimant_name, claimant_email, work_description,
          infringing_urls_json, received_at, status)
       VALUES (?, ?, ?, ?, ?, datetime('now'), 'received')`
    ).bind(
      noticeId,
      notice.claimantName,
      notice.claimantEmail,
      notice.workDescription,
      JSON.stringify(notice.infringingUrls)
    ).run();

    // Match infringing URLs to platform content
    const contentIds = await extractContentIds(notice.infringingUrls);
    const matchedContent: string[] = [];

    for (const contentId of contentIds) {
      const row = await env.DB.prepare(
        `SELECT content_id FROM content_nodes WHERE content_id = ? AND removed = 0`
      ).bind(contentId).first<{ content_id: string }>();

      if (row) matchedContent.push(row.content_id);
    }

    if (matchedContent.length === 0) {
      await env.DB.prepare(
        `UPDATE dmca_notices SET status = 'no-match', resolved_at = datetime('now') WHERE notice_id = ?`
      ).bind(noticeId).run();
      return new Response(JSON.stringify({ noticeId, status: "no-match" }), { status: 200 });
    }

    // Record matches and initiate takedown
    for (const contentId of matchedContent) {
      await env.DB.prepare(
        `INSERT INTO dmca_matches (notice_id, content_id, matched_at)
         VALUES (?, ?, datetime('now'))`
      ).bind(noticeId, contentId).run();
    }

    await env.DB.prepare(
      `UPDATE dmca_notices SET status = 'matched', match_count = ? WHERE notice_id = ?`
    ).bind(matchedContent.length, noticeId).run();

    return new Response(
      JSON.stringify({ noticeId, status: "matched", matchedCount: matchedContent.length }),
      { status: 202 }
    );
  },
};
```

## Enforcement — Expeditious Takedown and R2 Quarantine

A separate Worker processes matched notices and removes content from both D1 and R2, moving media objects to a quarantine prefix rather than deleting outright (preserving evidence for counter-notice review).

```typescript
// workers/dmca-takedown.ts
export interface Env {
  DB: D1Database;
  MEDIA_BUCKET: R2Bucket;
}

export async function executeDmcaTakedown(
  env: Env,
  noticeId: string,
  automatedApproval: boolean
): Promise<{ takenDownIds: string[]; quarantinedObjects: string[] }> {
  const { results: matches } = await env.DB.prepare(
    `SELECT m.content_id, n.claimant_email
     FROM dmca_matches m
     JOIN dmca_notices n ON n.notice_id = m.notice_id
     WHERE m.notice_id = ? AND m.taken_down_at IS NULL`
  ).bind(noticeId).all<{ content_id: string; claimant_email: string }>();

  const takenDownIds: string[] = [];
  const quarantinedObjects: string[] = [];

  for (const match of matches) {
    // Soft-remove from content_nodes
    await env.DB.prepare(
      `UPDATE content_nodes
       SET removed = 1, removed_at = datetime('now'), removal_reason = 'dmca-notice'
       WHERE content_id = ?`
    ).bind(match.content_id).run();

    // Quarantine R2 media objects (move to quarantine/ prefix)
    const mediaKey = `media/${match.content_id}`;
    const obj = await env.MEDIA_BUCKET.get(mediaKey);
    if (obj) {
      const quarantineKey = `quarantine/dmca/${noticeId}/${match.content_id}`;
      await env.MEDIA_BUCKET.put(quarantineKey, obj.body, {
        customMetadata: {
          originalKey: mediaKey,
          noticeId,
          quarantinedAt: new Date().toISOString(),
        },
      });
      await env.MEDIA_BUCKET.delete(mediaKey);
      quarantinedObjects.push(quarantineKey);
    }

    // Record the takedown timestamp
    await env.DB.prepare(
      `UPDATE dmca_matches
       SET taken_down_at = datetime('now'), automated = ?
       WHERE notice_id = ? AND content_id = ?`
    ).bind(automatedApproval ? 1 : 0, noticeId, match.content_id).run();

    takenDownIds.push(match.content_id);
  }

  await env.DB.prepare(
    `UPDATE dmca_notices
     SET status = 'taken-down', resolved_at = datetime('now')
     WHERE notice_id = ?`
  ).bind(noticeId).run();

  return { takenDownIds, quarantinedObjects };
}
```

## Escalation — Counter-Notice Workflow

When an uploader disputes a DMCA takedown, they submit a counter-notice. The Worker records it and starts a mandatory 10-business-day waiting period before content can be restored, per §512(g).

```typescript
// workers/dmca-counter-notice.ts
export interface Env {
  DB: D1Database;
}

interface CounterNotice {
  contentId: string;
  sessionToken: string;
  statement: string;
  goodFaithDeclaration: boolean;
  signature: string;
}

export async function submitCounterNotice(
  db: D1Database,
  counter: CounterNotice
): Promise<{ counterNoticeId: string; restoreEligibleAt: string }> {
  // Verify content is taken down under DMCA
  const existing = await db.prepare(
    `SELECT m.notice_id
     FROM dmca_matches m
     JOIN content_nodes c ON c.content_id = m.content_id
     WHERE m.content_id = ? AND c.removed = 1 AND c.removal_reason = 'dmca-notice'
     LIMIT 1`
  ).bind(counter.contentId).first<{ notice_id: string }>();

  if (!existing) throw new Error("Content not found under DMCA removal");

  // 10 business days ≈ 14 calendar days (conservative)
  const restoreEligibleAt = new Date(Date.now() + 14 * 86_400_000).toISOString();
  const counterNoticeId = crypto.randomUUID();

  await db.prepare(
    `INSERT INTO dmca_counter_notices
       (counter_notice_id, original_notice_id, content_id, session_token,
        statement, submitted_at, restore_eligible_at, status)
     VALUES (?, ?, ?, ?, ?, datetime('now'), ?, 'pending')`
  ).bind(
    counterNoticeId,
    existing.notice_id,
    counter.contentId,
    counter.sessionToken,
    counter.statement,
    restoreEligibleAt
  ).run();

  return { counterNoticeId, restoreEligibleAt };
}

export async function processEligibleRestorations(db: D1Database): Promise<number> {
  const { meta } = await db.prepare(
    `UPDATE content_nodes
     SET removed = 0, removed_at = NULL, removal_reason = NULL
     WHERE content_id IN (
       SELECT content_id FROM dmca_counter_notices
       WHERE status = 'pending'
         AND restore_eligible_at <= datetime('now')
         AND claimant_challenged_at IS NULL
     )`
  ).run();

  await db.prepare(
    `UPDATE dmca_counter_notices
     SET status = 'restored', restored_at = datetime('now')
     WHERE status = 'pending'
       AND restore_eligible_at <= datetime('now')
       AND claimant_challenged_at IS NULL`
  ).run();

  return meta.changes;
}
```

## Monitoring — Compliance Metrics

```sql
-- DMCA SLA compliance: notices resolved within 24 hours
SELECT
  COUNT(*) AS total_notices,
  COUNT(CASE WHEN
    CAST((julianday(resolved_at) - julianday(received_at)) * 24 AS INTEGER) <= 24
    THEN 1 END) AS within_sla,
  AVG(CAST((julianday(resolved_at) - julianday(received_at)) * 60 AS INTEGER)) AS avg_resolution_minutes
FROM dmca_notices
WHERE received_at > datetime('now', '-30 days')
  AND resolved_at IS NOT NULL;

-- Pending counter-notices approaching restoration window
SELECT counter_notice_id, content_id, restore_eligible_at
FROM dmca_counter_notices
WHERE status = 'pending'
  AND restore_eligible_at <= datetime('now', '+48 hours')
ORDER BY restore_eligible_at;
```

## Anti-patterns

- Permanently deleting R2 objects on DMCA takedown — counter-notices require content to be restorable; always quarantine
- Auto-restoring content immediately after the 14-day window without checking for claimant legal action — §512(g)(2)(C) requires written notification of legal proceedings
- Processing counter-notices from the same session that submitted the infringing content without additional verification — anonymous platforms need extra friction here
- Storing claimant PII (email, signature) in unencrypted D1 TEXT columns — encrypt at rest using Workers KV-stored keys
- Trusting infringing URL patterns without URL-normalizing them first — attackers append query strings to bypass URL deduplication

## Gotchas

- R2 `put` after `get` does not guarantee atomicity; if the Worker crashes mid-quarantine, the original object may be deleted but the quarantine copy absent — use a two-step: write quarantine, verify, then delete
- D1 does not have a native date arithmetic for "business days"; use calendar days (14) as a safe proxy
- The DMCA does not define "expeditious" precisely; courts have found 1–2 weeks acceptable for platforms, but same-day automated takedown is the safe harbor gold standard
- Counter-notices from anonymous sessions create a legal paradox (they require a physical address); implement a pseudonymous box service or reject counter-notices for fully anonymous content
- `crypto.randomUUID()` is available in Workers without any import; no need for the `uuid` npm package

## Verification

1. POST a valid DMCA notice to the intake Worker with a URL matching a content ID in D1 — expect `status: "matched"`.
2. Call `executeDmcaTakedown` — verify `content_nodes.removed = 1` and the R2 object has moved to `quarantine/dmca/`.
3. Submit a counter-notice — expect a `restoreEligibleAt` 14 days in the future.
4. Manually set `restore_eligible_at` to the past in D1 and run `processEligibleRestorations` — verify `content_nodes.removed = 0`.
5. Query the compliance metrics SQL — all test notices should show `avg_resolution_minutes < 60`.

## Related

- `/documentation/categories/issues/copyright-dmca-takedown-worker-pipeline.md`
- `/documentation/categories/issues/legal-hold-evidence-preservation-d1-r2.md`
- `/documentation/categories/issues/hash-based-duplicate-content-detection-r2.md`
- `/documentation/categories/issues/platform-audit-log-immutable-d1-workers.md`

## Sources

- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/d1/
- https://www.law.cornell.edu/uscode/text/17/512 (DMCA §512 safe harbor)
- https://www.eff.org/issues/dmca/guide
