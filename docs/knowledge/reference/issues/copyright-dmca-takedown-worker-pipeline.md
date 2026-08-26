# Copyright DMCA Takedown Worker Pipeline

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project receives DMCA takedown notices via email and a public web form.  Without an
automated intake pipeline, notices sit in an inbox for days, R2-hosted media remains
publicly accessible long after the 17 U.S.C. § 512 "expeditious removal" obligation
is triggered, and counter-notice handling is entirely manual.  An unanswered DMCA
notice causes the platform to lose its DMCA safe-harbor protections under the DMCA and
equivalent Article 17 obligations under the EU Copyright Directive.

## Context

example project stores all user-uploaded media in Cloudflare R2 under the key pattern
`user/{accountId}/media/{mediaId}.{ext}`.  Posts reference media by URL
(`https://media.example.com/user/.../media/...`).  A Worker serves R2 objects and
generates signed URLs for private content.  The DMCA pipeline introduces a
"quarantine" state in R2 (object replaced by a tombstone key) and a D1 state machine
that tracks notice lifecycle from intake through counter-notice resolution.
Cloudflare's Abuse API is used to report content to Cloudflare where applicable
(e.g., content also cached at the Cloudflare edge).

## DMCA Intake Worker

A dedicated Worker at `https://example.com/api/dmca/notice` accepts structured
takedown notices.  Email-based notices are processed by a separate Email Worker
that parses the notice body and calls the same intake endpoint internally.

```ts
// worker/routes/dmcaIntake.ts
export interface DmcaNoticePayload {
  complainantName: string;
  complainantEmail: string;
  copyrightDescription: string;       // work allegedly infringed
  infringingUrls: string[];           // must be example.com URLs
  goodFaithStatement: boolean;        // § 512(c)(3)(A)(v)
  accuracyStatement: boolean;         // § 512(c)(3)(A)(vi)
  signature: string;                  // electronic signature
}

export async function handleDmcaIntake(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<DmcaNoticePayload>();

  // Validate required § 512(c)(3) elements
  if (!body.goodFaithStatement || !body.accuracyStatement || !body.signature) {
    return Response.json({ error: "incomplete_notice", missing: "statutory_statements" }, { status: 400 });
  }

  const noticeId = crypto.randomUUID();
  const mediaKeys = body.infringingUrls.map(urlToR2Key).filter(Boolean);

  // Write notice to D1
  await env.DB.prepare(`
    INSERT INTO dmca_notices
      (id, complainant_name, complainant_email, copyright_description,
       infringing_urls, good_faith, accuracy, signature, state, created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?)
  `).bind(
    noticeId,
    body.complainantName,
    body.complainantEmail,
    body.copyrightDescription,
    JSON.stringify(body.infringingUrls),
    body.goodFaithStatement ? 1 : 0,
    body.accuracyStatement  ? 1 : 0,
    body.signature,
    "received",
    Date.now(),
  ).run();

  // Quarantine each media object in R2
  await Promise.all(mediaKeys.map(key => quarantineMedia(env, noticeId, key)));

  // Notify designated agent (internal)
  await env.DMCA_QUEUE.send({ noticeId, mediaKeys });

  return Response.json({ noticeId, status: "received", mediaQuarantined: mediaKeys.length });
}
```

## R2 Quarantine Mechanism

"Quarantine" does not delete the object — it must be preserved as evidence and
restored if a counter-notice succeeds.  Instead the Worker copies the object to a
private quarantine prefix and replaces the original with a JSON tombstone.

```ts
// worker/lib/r2Quarantine.ts
export async function quarantineMedia(
  env: Env,
  noticeId: string,
  key: string,
): Promise<void> {
  const original = await env.R2_MEDIA.get(key);
  if (!original) return;

  // Copy to quarantine (private, no public URL)
  const quarantineKey = `dmca-quarantine/${noticeId}/${key}`;
  await env.R2_MEDIA.put(quarantineKey, original.body, {
    httpMetadata: original.httpMetadata,
    customMetadata: {
      ...original.customMetadata,
      dmcaNoticeId: noticeId,
      originalKey: key,
      quarantinedAt: new Date().toISOString(),
    },
  });

  // Replace original with a tombstone JSON object
  const tombstone = JSON.stringify({
    status: "removed",
    reason: "dmca_notice",
    noticeId,
    removedAt: new Date().toISOString(),
  });
  await env.R2_MEDIA.put(key, tombstone, {
    httpMetadata: { contentType: "application/json" },
    customMetadata: { dmcaTombstone: "true" },
  });
}
```

The media-serving Worker checks for the tombstone:

```ts
if (obj.customMetadata?.dmcaTombstone === "true") {
  return new Response("Content removed per DMCA notice.", { status: 451 });
}
```

HTTP 451 ("Unavailable For Legal Reasons") is the correct status code per RFC 7725.

## D1 Takedown State Machine

```sql
CREATE TABLE IF NOT EXISTS dmca_notices (
  id                    TEXT    PRIMARY KEY,
  complainant_name      TEXT    NOT NULL,
  complainant_email     TEXT    NOT NULL,
  copyright_description TEXT    NOT NULL,
  infringing_urls       TEXT    NOT NULL,  -- JSON array
  good_faith            INTEGER NOT NULL,  -- 0|1
  accuracy              INTEGER NOT NULL,  -- 0|1
  signature             TEXT    NOT NULL,
  state                 TEXT    NOT NULL,  -- see enum below
  assigned_to           TEXT,              -- moderator UUID
  counter_notice_id     TEXT,              -- FK to counter_notices.id
  resolved_at           INTEGER,
  created_at            INTEGER NOT NULL
);

-- state enum:
-- received | under_review | quarantined | counter_notice_filed
-- counter_notice_pending_14d | restored | permanently_removed | rejected_incomplete
```

State transitions with timing obligations:

```
┌────────────────────────────────┬─────────────────────────┬─────────────────────────┐
│ Transition                     │ Trigger                 │ Timing Obligation        │
├────────────────────────────────┼─────────────────────────┼─────────────────────────┤
│ received → quarantined         │ Intake Worker           │ Expeditious (< 24 h)    │
│ quarantined → under_review     │ Moderator pick-up       │ Within 48 h             │
│ under_review → rejected        │ Invalid/incomplete      │ Notify complainant       │
│ quarantined → counter_notice   │ User files counter      │ Forward to complainant   │
│ counter_notice → pending_14d   │ Complainant notified    │ Wait 10–14 business days │
│ pending_14d → restored         │ No court order filed    │ Restore promptly         │
│ pending_14d → permanently_rmvd │ Court order received    │ Comply with order        │
└────────────────────────────────┴─────────────────────────┴─────────────────────────┘
```

## Counter-Notice Workflow

A suspended user may file a counter-notice under 17 U.S.C. § 512(g)(3).  The Worker
validates required elements and starts the 10–14 business-day waiting period.

```ts
// worker/routes/dmcaCounterNotice.ts
export async function handleCounterNotice(
  request: Request,
  env: Env,
  accountId: string,
): Promise<Response> {
  const { noticeId, statement, signature, consentToJurisdiction } =
    await request.json<CounterNoticePayload>();

  if (!consentToJurisdiction || !signature) {
    return Response.json({ error: "incomplete_counter_notice" }, { status: 400 });
  }

  const counterId = crypto.randomUUID();
  const batch = env.DB.batch([
    env.DB.prepare(
      `INSERT INTO counter_notices (id,notice_id,account_id,statement,signature,consent_jurisdiction,state,created_at)
       VALUES (?,?,?,?,?,?,?,?)`
    ).bind(counterId, noticeId, accountId, statement, signature, 1, "filed", Date.now()),

    env.DB.prepare(
      `UPDATE dmca_notices SET state='counter_notice_filed', counter_notice_id=? WHERE id=?`
    ).bind(counterId, noticeId),
  ]);
  await batch;

  // Schedule restore after 14 business days (approximate: 20 calendar days)
  await env.DMCA_QUEUE.send({
    type: "schedule_restore",
    counterId,
    noticeId,
    restoreAfter: Date.now() + 20 * 24 * 60 * 60 * 1000,
  });

  return Response.json({ counterId, status: "filed", expectedRestoreAfter: "14 business days" });
}
```

## Cloudflare Abuse API

When the infringing content is also cached or accessible via Cloudflare's network
(not just stored in R2), the platform should submit a report to Cloudflare's Abuse
Reporting API so that Cloudflare can take its own network-level action.

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ Cloudflare Abuse Report endpoint                                                  │
│ POST https://api.cloudflare.com/client/v4/accounts/{accountId}/abuse_reports      │
├──────────────────────┬────────────────────────────────────────────────────────────┤
│ Field                │ Value for DMCA reports                                    │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ type                 │ "dmca"                                                    │
│ urls                 │ array of infringing URLs                                  │
│ comments             │ copyright_description from notice                         │
│ email                │ complainant_email                                          │
│ name                 │ complainant_name                                           │
│ signature            │ signature field from notice                               │
└──────────────────────┴────────────────────────────────────────────────────────────┘
```

This is a supplementary step; example project is the primary responsible party and must act on
the notice independently of whether Cloudflare accepts the report.

## Anti-patterns

- Deleting quarantined R2 objects immediately — destroys evidence required for
  counter-notice restoration and may constitute spoliation in litigation.
- Using HTTP 404 for removed DMCA content — 451 is the legally specified status
  and is required by several EU member state copyright implementing laws.
- Waiting for a human moderator before quarantining — § 512 "expeditious removal"
  has been interpreted by courts as requiring action within hours, not days;
  automated quarantine on intake is necessary for safe-harbor eligibility.
- Forwarding the counter-notice to the complainant's email directly from a Worker
  without rate-limiting — enables the DMCA intake endpoint to be used as an email
  relay/spam vector.
- Storing the complainant's personal information beyond the retention period required
  by your privacy policy — GDPR Article 5(1)(e) storage limitation applies even to
  legal-process records.

## Gotchas

- `env.R2_MEDIA.get(key)` returns `null` if the object does not exist, and the body
  stream can only be consumed once.  Do not call `original.body` after the `put()` to
  the quarantine prefix has consumed it.  Read metadata separately from body if needed.
- `R2Object.body` is a `ReadableStream`.  Passing it to a second `put()` after the
  first has started consuming it will produce a partial or empty object.  If you need
  to read the body for inspection AND copy it, use `original.arrayBuffer()` first.
- D1 `batch()` is not a true transaction in all contexts; it runs statements
  sequentially inside a single connection but does not roll back on partial failure in
  the current D1 preview.  Add manual compensation logic or accept minor inconsistency.
- The 10–14 business-day wait in § 512(g) is measured in US business days.  A cron
  Worker using 20 calendar days is a conservative approximation; for strict compliance
  implement a business-day calendar or use 10 business days minimum.
- `wrangler queues` (Cloudflare Queues) requires the `queues_producer` and
  `queues_consumer` bindings in `wrangler.toml`.  Omitting the consumer binding means
  `schedule_restore` messages are enqueued but never processed.

## Verification

```bash
# 1. Submit a test DMCA notice
curl -X POST https://example.com/api/dmca/notice \
  -H "Content-Type: application/json" \
  -d '{
    "complainantName":"Test Corp",
    "complainantEmail":"dmca@testcorp.example",
    "copyrightDescription":"Test image 2026",
    "infringingUrls":["https://media.example.com/user/acct-1/media/img-1.jpg"],
    "goodFaithStatement":true,
    "accuracyStatement":true,
    "signature":"John Doe"
  }'
# Expect: {"noticeId":"...","status":"received","mediaQuarantined":1}

# 2. Verify the original key now returns a tombstone
curl -I https://media.example.com/user/acct-1/media/img-1.jpg
# Expect: HTTP/1.1 451 Unavailable For Legal Reasons

# 3. Verify quarantine copy exists
wrangler r2 object get example project-media "dmca-quarantine/$NOTICE_ID/user/acct-1/media/img-1.jpg" \
  --file /tmp/quarantine-check.jpg
# Expect: file downloaded successfully

# 4. Check D1 state
wrangler d1 execute example project-db --command \
  "SELECT id, state, created_at FROM dmca_notices ORDER BY created_at DESC LIMIT 1"
# Expect: state = "quarantined"
```

## Related

- `anonymous-content-reporting-worker-pipeline.md`
- `content-moderation-appeals-workflow.md`
- `account-suspension-appeals-worker-workflow.md`
- `user-privacy-law-enforcement-requests.md`
- `platform-liability-section-230-dsa.md`
- `r2-etag-conditional-request.md`

## Sources

- 17 U.S.C. § 512 (DMCA Safe Harbor) — law.cornell.edu/uscode/text/17/512
- RFC 7725 (HTTP 451) — rfc-editor.org/rfc/rfc7725
- EU Copyright Directive (DSM) Article 17 — eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32019L0790
- Cloudflare R2 — developers.cloudflare.com/r2/
- Cloudflare D1 — developers.cloudflare.com/d1/
- Cloudflare Queues — developers.cloudflare.com/queues/
- Cloudflare Abuse Reporting API — developers.cloudflare.com/fundamentals/abuse/
