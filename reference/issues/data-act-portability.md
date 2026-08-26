# data-act-portability

**Issue:** EU Data Act — portability + B2B + B2G data sharing
**Date:** 2026-08-09
**Status:** documented (compliance checklist)

## Symptom
A user requests to download all their data in a portable format.
You provide a JSON dump of their account settings. But the
posts they made, the messages they sent, the photos they
uploaded — not included. The Data Act requires all of it.

## Root cause
The Data Act (Regulation (EU) 2023/2854) extends data
portability rights to connected products (IoT) and
business-to-business / business-to-government data sharing.
For consumer platforms, the data portability requirements are
similar to GDPR Article 20 (right to data portability) but
with stricter format requirements.

**Source:** Data Act:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2854

> "The user shall have the right to receive personal data
> concerning them ... in a structured, commonly used and
> machine-readable format."

The key addition over GDPR: the data must be in a **commonly
used** format. A JSON dump of internal data structures is not
portable. A standardized schema (e.g. Schema.org, W3C Solid,
or industry-specific) is.

## What data must be portable?

For a social platform:
- **Profile data:** name, email, display name, avatar
- **Content:** all posts (text, images, videos, links)
- **Engagement:** likes, follows, comments (received + given)
- **Messaging:** DMs (with consent of other parties; for 1:1
  messages, the recipient must also consent)
- **Settings:** preferences, blocks, mutes
- **Activity log:** login history, account changes

## What format?

- **JSON-LD with Schema.org** markup — most universal
- **W3C Solid pod** — emerging standard for personal data
- **NDJSON** (one JSON per line) — for activity logs
- **Industry-specific:** e.g. ActivityPub for social networks

For maximum portability, provide a ZIP file with:
```
user_data_export.zip
├── README.md                  # explains contents
├── profile.json               # profile data (Schema.org Person)
├── posts/
│   ├── posts.jsonld          # all posts (Schema.org SocialMediaPosting)
│   ├── images/               # all images
│   └── videos/               # all videos
├── engagement/
│   ├── likes.jsonld
│   ├── follows.jsonld
│   └── comments.jsonld
├── activity/
│   └── activity.ndjson       # login history, settings changes
└── settings.json              # preferences, blocks, mutes
```

## B2B / B2G data sharing

The Data Act also requires B2B (business-to-business) data
sharing for connected products. For a consumer platform:
- When a user connects a third-party service (e.g. a fitness
  app to your platform), the user can request the data flow
  be redirected to a different service
- B2G (business-to-government) data sharing is for "public
  sector needs" — e.g. emergency response, statistical
  purposes

For most consumer platforms, the user-facing portability is
the primary concern. B2B / B2G are forward-looking.

## Fix

### Implement the export endpoint
```ts
// POST /api/path/to/export
export async function exportUserData(request: Request, env: Env, ctx: McContext): Promise<Response> {
  const userId = ctx.user.id;
  // 1. Start a background job (long-running)
  const jobId = crypto.randomUUID();
  await env.DB!.prepare(
    `INSERT INTO export_jobs (id, user_id, status, requested_at) VALUES (?, ?, 'pending', ?)`
  ).bind(jobId, userId, Math.floor(Date.now() / 1000)).run();

  // 2. Return 202 Accepted with job ID
  // The user polls GET /api/path/to/export/:jobId

  // 3. Trigger the actual export (DO + R2)
  // (separately)

  return new Response(JSON.stringify({ job_id: jobId, status_url: `/api/path/to/export/${jobId}` }), {
    status: 202,
    headers: { 'content-type': 'application/json' },
  });
}
```

### Background processing
```ts
class ExportJobDO {
  async fetch(req: Request): Promise<Response> {
    const jobId = req.headers.get('X-Job-Id');

    // 1. Collect data
    const profile = await getProfile(userId);
    const posts = await getPosts(userId);
    const engagement = await getEngagement(userId);
    // ...

    // 2. Build the export
    const zip = await buildExportZip({ profile, posts, engagement });

    // 3. Upload to R2
    await env.R2.put(`exports/${userId}/${jobId}.zip`, zip);

    // 4. Update job status
    await env.DB!.prepare(
      `UPDATE export_jobs SET status = 'complete', download_url = ? WHERE id = ?`
    ).bind(`/api/path/to/export/${jobId}/download`, jobId).run();

    return new Response('OK');
  }
}
```

### Time limit
The Data Act requires the export to be available within
**30 days** of the request. Most platforms target 24-48h.

## Verification
- **Test:** Request export → within 48h, downloadable ZIP is
  available
- **Live:** The ZIP contains all the user's data in
  standardized formats
- **Audit:** Annual third-party review of export quality

## Gotchas
- **Other users' data is not exportable.** If User A's post has
  comments from Users B, C, D, the export of A's data does
  NOT include B, C, D's profile data. The export is "A's view
  of the world."
- **DMs are tricky.** For 1:1 DMs, both parties must consent
  to the export. If the other party hasn't consented, the
  message is redacted (e.g. "[Message redacted — recipient
  has not consented to data portability]").
- **The export must include data, not "exports of exports."**
  Provide the raw data in standardized formats, not nested
  exported JS objects.
- **The export must be downloadable for at least 30 days.**
  After that, you can delete (with notice).
- **The Data Act's 30-day timeline is separate from GDPR's
  1-month timeline.** They're compatible; use the longer of
  the two.

## Related
- `gdpr-article-17-erasure.md` (companion for deletion)
- `audit-log-mandatory.md` (the data.export event)
- Data Act: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2854
- Schema.org: https://schema.org/
