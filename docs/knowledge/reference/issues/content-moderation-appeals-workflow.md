# content-moderation-appeals-workflow

**Issue:** Appeals state machine has no timeout fallback — appeals
  older than 14 days remain 'pending' indefinitely; mobile submit
  form creates duplicate appeals on double-tap; moderator dashboard
  Worker returns 200 on expired JWT instead of 401
**Date:** 2026-08-22
**Author:** example.com
**Status:** open

## Symptom

1. A user whose post was removed 21 days ago still shows appeal
   status as "Under review". The moderator queue shows 340 stale
   appeals with no assigned reviewer and no auto-resolution.
2. iOS users tapping "Submit appeal" on a slow connection see the
   button briefly re-enable. A second tap creates two identical
   appeal rows in D1. The user receives two separate case IDs.
3. The moderator dashboard `GET /api/mod/appeals` returns
   `{ "appeals": [] }` with HTTP 200 when the moderator JWT has
   expired. Moderators interpret this as an empty queue.

## Context

When example project removes content, the user receives a notification
containing a link to file an appeal. Appeals are anonymous — the
platform does not disclose which moderator reviewed the content.
The appeals system must handle three removal types:
- Automated removals (trust score below threshold)
- Human moderator removals
- CSAM-related removals (not appealable — lock state immediately)

## D1 State Machine Schema

```sql
CREATE TABLE appeals (
  id            TEXT PRIMARY KEY,
  content_id    TEXT NOT NULL,
  user_id       TEXT NOT NULL,
  reason        TEXT NOT NULL,       -- user's explanation, ≤500 chars
  status        TEXT NOT NULL DEFAULT 'pending',
                  -- 'pending'|'under_review'|'approved'
                  -- |'rejected'|'escalated'|'locked'
  removal_type  TEXT NOT NULL,       -- 'auto'|'human'|'csam'
  idempotency_key TEXT UNIQUE,       -- client-generated UUID
  created_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  assigned_to   TEXT,                -- moderator ID, nullable
  resolved_at   INTEGER,
  timeout_at    INTEGER NOT NULL
                  GENERATED ALWAYS AS (created_at + 1209600) STORED,
  escalated_at  INTEGER
);

CREATE INDEX idx_appeals_status     ON appeals(status, timeout_at);
CREATE INDEX idx_appeals_content    ON appeals(content_id);
CREATE INDEX idx_appeals_user       ON appeals(user_id, created_at);
```

Valid state transitions:

```
pending ──────────────► under_review ──► approved
    │                        │
    │ (removal_type=csam)    ├──────────► rejected
    ▼                        │
  locked                     └──────────► escalated
    │                                         │
    │ (timeout: 14 d, no review assigned)     ├──► approved
    ▼                                         └──► rejected
  rejected (auto; reason: "not reviewed
            in time, original decision stands")
```

Cloudflare Cron Trigger (every 4 hours) auto-rejects stale appeals:

```ts
// workers/appeals-timeout-cron.ts
export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    await env.DB.prepare(
      `UPDATE appeals
          SET status = 'rejected',
              resolved_at = unixepoch()
        WHERE status IN ('pending', 'under_review')
          AND timeout_at < unixepoch()`
    ).run();
  },
};
```

## Moderator Dashboard Workers API

Always return 401 on auth failure — never 200 with empty data:

```ts
// workers/mod-dashboard.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const moderator = await verifyModJwt(req, env);
    if (!moderator) {
      return new Response(
        JSON.stringify({ error: 'Unauthorized' }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        }
      );
    }

    const appeals = await env.DB.prepare(
      `SELECT id, content_id, reason, status, created_at
         FROM appeals
        WHERE status = 'pending'
           OR (status = 'under_review' AND assigned_to = ?1)
        ORDER BY created_at ASC
        LIMIT 50`
    ).bind(moderator.id).all();

    return Response.json({ appeals: appeals.results });
  },
};
```

Escalation endpoint — moves status to `escalated` and notifies ops:

```ts
await env.DB.prepare(
  `UPDATE appeals
      SET status       = 'escalated',
          escalated_at = unixepoch()
    WHERE id            = ?1
      AND assigned_to   = ?2
      AND status        = 'under_review'`
).bind(appealId, moderator.id).run();

await env.NOTIFICATIONS.send({
  type:       'appeal_escalated',
  appealId,
  escalatedBy: moderator.id,
});
```

## Mobile-Optimised Appeal Submission

Prevent duplicate submissions with an idempotency key generated
client-side and held in `sessionStorage`:

```ts
// client/appeal-form.ts
async function submitAppeal(form: FormData): Promise<void> {
  const key = sessionStorage.getItem('appeal_idem')
            ?? crypto.randomUUID();
  sessionStorage.setItem('appeal_idem', key);

  const res = await fetch('/api/appeals', {
    method:  'POST',
    headers: { 'Idempotency-Key': key },
    body:    form,
  });

  if (res.ok) sessionStorage.removeItem('appeal_idem');
}
```

Worker-side idempotency check:

```ts
const existing = await env.DB.prepare(
  `SELECT id FROM appeals
    WHERE idempotency_key = ?1
      AND created_at > unixepoch() - 3600`
).bind(idempotencyKey).first();

if (existing) {
  return Response.json({ id: existing.id }, { status: 200 });
}
```

```
┌───────────────────────┬────────────────────┬──────────────────┐
│ Mobile UX pattern     │ iOS                │ Android          │
├───────────────────────┼────────────────────┼──────────────────┤
│ Submit confirmation   │ Action Sheet       │ Snackbar +       │
│                       │ (.confirmDialog)   │ full-screen      │
│                       │                    │ summary sheet    │
├───────────────────────┼────────────────────┼──────────────────┤
│ Appeal status polling │ BGTaskScheduler    │ WorkManager      │
│                       │ background fetch   │ periodic task    │
├───────────────────────┼────────────────────┼──────────────────┤
│ Character limit for   │ 500 chars; UIText- │ 500 chars;       │
│ reason field          │ Field maxLength    │ TextInputLayout  │
│                       │ enforced natively  │ counterText      │
├───────────────────────┼────────────────────┼──────────────────┤
│ Attachment evidence   │ PHPickerController │ Photo Picker     │
│ picker                │ (privacy-safe)     │ API (Android 13+)│
└───────────────────────┴────────────────────┴──────────────────┘
```

## Escalation to Human Review Queue

When a moderator marks an appeal `escalated`, it enters a senior
review queue with a 72-hour SLA. Senior reviewers see the full
moderation history for the content (but not the reporter identity):

```sql
-- Fetch appeals for senior review with moderation context
SELECT a.id, a.reason, a.escalated_at,
       c.removal_reason, c.removed_by_type
  FROM appeals a
  JOIN content c ON c.id = a.content_id
 WHERE a.status = 'escalated'
   AND a.escalated_at < unixepoch() - 259200  -- 72-hour breach alert
 ORDER BY a.escalated_at ASC;
```

## Anti-patterns

- **Allowing appeals on CSAM removals.** The moment
  `removal_type = 'csam'` is set, write `status = 'locked'` and
  return a static rejection message. Never expose the CSAM
  detection logic to the appeal reviewer.
- **Assigning the appeal to the same moderator who made the
  original removal.** Store `removed_by` on the content row and
  exclude that moderator from the assignment pool in the query.
- **Storing appeal reason text in KV.** KV has poor query support.
  Use D1 for all structured appeal data; use R2 only for attached
  evidence files uploaded alongside the appeal.

## Gotchas

- `GENERATED ALWAYS AS ... STORED` requires SQLite 3.31+. Verify
  with `wrangler d1 execute example project-db --command
  "SELECT sqlite_version()"` before shipping the migration.
- Moderator JWT verification must explicitly check the `exp` claim.
  Lightweight CF Worker JWT libraries do not all reject expired
  tokens by default — test this path explicitly.
- If a moderator session expires mid-review, the `assigned_to` row
  remains. The cron must un-assign `under_review` appeals with no
  activity for >48 hours so they re-enter the queue.

## Verification

```
# Idempotency: second submit with same key returns same ID
ID=$(curl -s -X POST https://example project.app/api/appeals \
  -H 'Idempotency-Key: test-idem-001' \
  -d '{"content_id":"c1","reason":"I disagree"}' \
  | jq -r .id)

ID2=$(curl -s -X POST https://example project.app/api/appeals \
  -H 'Idempotency-Key: test-idem-001' \
  -d '{"content_id":"c1","reason":"I disagree"}' \
  | jq -r .id)

[ "$ID" = "$ID2" ] && echo "PASS" || echo "FAIL"

# Expired JWT must return 401, not 200 with empty list
curl -s -o /dev/null -w "%{http_code}" \
  -H 'Authorization: Bearer <expired_jwt>' \
  https://example project.app/api/mod/appeals
# → 401
```

## Related

- `documentation/docs/policies/issues/877-csam-vendor-integration.md`
- `documentation/docs/policies/issues/anonymous-content-reporting-worker-pipeline.md`
- `documentation/docs/policies/issues/platform-trust-score-cloudflare-signals.md`
- `documentation/docs/policies/issues/age-verification-cloudflare-workers-kyc.md`
- `documentation/docs/policies/issues/d1-column-affinity-gotcha.md`

## Source URLs

- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
- https://developers.cloudflare.com/d1/
- https://gdpr-info.eu/art-17-gdpr/
- https://www.apple.com/app-store/review/guidelines/#user-generated-content
