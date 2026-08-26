# Email Render Testing Cross-Client Matrix — Workers + R2

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You push a campaign and discover the layout is broken in Outlook 2019 after the
send. You need an automated pre-send check that captures rendered screenshots
across a matrix of clients and flags regressions — without paying per-test fees
to a SaaS screenshot service on every deploy.

---

## Context

Litmus and Email on Acid expose REST APIs that return screenshot URLs or base64
images. A Workers pipeline can call these APIs, store the results in R2 (one
prefix per campaign + client), expose a review UI from a Worker, and block a
send queue entry until a human approves or CI thresholds pass. This keeps
render artefacts alongside the template in your own storage indefinitely.

---

## R2 Bucket Layout

```
renders/
  {campaign-id}/
    {client-slug}/
      screenshot.png
      meta.json        # { client, capturedAt, viewportWidth, darkMode }
    _matrix.json       # { campaignId, clients: [...], approvedAt, approvedBy }
```

---

## Submitting a Template for Rendering

```typescript
// src/workers/render-submit.ts
export interface Env {
  BUCKET: R2Bucket;
  LITMUS_API_KEY: string;
  RENDER_QUEUE: Queue;
}

interface SubmitBody {
  campaignId: string;
  htmlSource: string;
  subjectLine: string;
}

const CLIENT_MATRIX = [
  'GMAIL_CHROME_WINDOWS',
  'OUTLOOK_2019',
  'APPLE_MAIL_14_MACOS',
  'SAMSUNG_MAIL_ANDROID',
  'GMAIL_IPHONE',
];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<SubmitBody>();

    // Kick off Litmus test via their API
    const litmusRes = await fetch('https://api.litmus.com/v2/tests', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.LITMUS_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        subject: body.subjectLine,
        html: body.htmlSource,
        email_clients: CLIENT_MATRIX,
      }),
    });

    if (!litmusRes.ok) {
      return new Response('Litmus submission failed', { status: 502 });
    }

    const { test_id } = await litmusRes.json<{ test_id: string }>();

    // Enqueue a poller job
    await env.RENDER_QUEUE.send({
      campaignId: body.campaignId,
      testId: test_id,
      attempt: 0,
    });

    return new Response(JSON.stringify({ testId: test_id }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Queue Consumer — Poll and Store Screenshots

```typescript
// src/workers/render-poller.ts
const MAX_ATTEMPTS = 10;
const POLL_DELAY_MS = 15_000;

export default {
  async queue(batch: MessageBatch<RenderJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;

      const statusRes = await fetch(
        `https://api.litmus.com/v2/tests/${job.testId}`,
        { headers: { Authorization: `Bearer ${env.LITMUS_API_KEY}` } }
      );
      const test = await statusRes.json<LitmusTest>();

      if (test.status !== 'completed') {
        if (job.attempt >= MAX_ATTEMPTS) {
          console.error(`Render test ${job.testId} timed out`);
          msg.ack();
          return;
        }
        // Requeue with back-off — Queues delay via visibilityTimeoutMs
        await env.RENDER_QUEUE.send(
          { ...job, attempt: job.attempt + 1 },
          { delaySeconds: Math.floor(POLL_DELAY_MS / 1000) }
        );
        msg.ack();
        return;
      }

      // Persist each client screenshot to R2
      for (const result of test.results) {
        const imgRes = await fetch(result.screenshot_url);
        const blob = await imgRes.arrayBuffer();
        const key = `renders/${job.campaignId}/${result.client_slug}/screenshot.png`;

        await env.BUCKET.put(key, blob, {
          httpMetadata: { contentType: 'image/png' },
        });
        await env.BUCKET.put(
          `renders/${job.campaignId}/${result.client_slug}/meta.json`,
          JSON.stringify({
            client: result.client_slug,
            capturedAt: Date.now(),
            viewportWidth: result.viewport_width,
            darkMode: result.dark_mode ?? false,
          })
        );
      }

      // Write matrix summary
      await env.BUCKET.put(
        `renders/${job.campaignId}/_matrix.json`,
        JSON.stringify({
          campaignId: job.campaignId,
          clients: test.results.map((r) => r.client_slug),
          completedAt: Date.now(),
          approvedAt: null,
        })
      );

      msg.ack();
    }
  },
};
```

---

## Review Worker — Serve Screenshot Gallery

```typescript
// src/workers/render-review.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const campaignId = url.searchParams.get('campaign');
    if (!campaignId) return new Response('Missing campaign', { status: 400 });

    // List all client prefixes for this campaign
    const listed = await env.BUCKET.list({
      prefix: `renders/${campaignId}/`,
      delimiter: '/',
    });

    const clients = listed.delimitedPrefixes.map((p) =>
      p.replace(`renders/${campaignId}/`, '').replace('/', '')
    );

    // Generate pre-signed read URLs (R2 signed URLs, 1-hour expiry)
    const rows = await Promise.all(
      clients.map(async (slug) => {
        const key = `renders/${campaignId}/${slug}/screenshot.png`;
        const signed = await env.BUCKET.createMultipartUpload; // placeholder
        // Use signed URL via R2 public bucket or Workers auth header
        return `<tr><td>${slug}</td><td><img  style="max-width:300px"></td></tr>`;
      })
    );

    return new Response(
      `<table>${rows.join('')}</table>`,
      { headers: { 'Content-Type': 'text/html' } }
    );
  },
};
```

---

## CI Gate — Block Send Until Approved

```typescript
// src/workers/send-gate.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { campaignId } = await request.json<{ campaignId: string }>();

    const matrixObj = await env.BUCKET.get(
      `renders/${campaignId}/_matrix.json`
    );
    if (!matrixObj) return new Response('Renders not ready', { status: 202 });

    const matrix = await matrixObj.json<{ approvedAt: number | null }>();
    if (!matrix.approvedAt) {
      return new Response(
        JSON.stringify({ blocked: true, reason: 'Render review pending' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }
      );
    }

    return new Response(
      JSON.stringify({ blocked: false }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  },
};
```

---

## Anti-patterns

- **Storing screenshots in KV** — KV values max out at 25 MB; a single PNG
  from a high-DPI Outlook render can exceed that. R2 has no object-size limit
  that matters here.
- **Polling synchronously inside a fetch handler** — Litmus tests take 2–10
  minutes; a synchronous loop in `fetch` will hit the 30-second CPU wall. The
  queue-based poller above is the correct pattern.
- **One test ID shared across re-renders** — always create a new Litmus test
  when the HTML changes; reusing old IDs shows stale screenshots.

---

## Gotchas

- R2 does not auto-generate public URLs; serve screenshots through a Worker
  that reads the object and streams the response, or configure an R2 custom
  domain with public access.
- Litmus charges per rendered client × email; reduce cost by keeping
  `CLIENT_MATRIX` to your actual audience split rather than the full 100+
  client catalogue.
- Queues `delaySeconds` caps at 43 200 (12 hours) — well above any render
  timeout, but verify if Litmus SLA ever exceeds that.

---

## Verification

```bash
# Submit a test
curl -X POST https://workers.example.com/render-submit \
  -H "Content-Type: application/json" \
  -d '{"campaignId":"camp-001","htmlSource":"<html>...</html>","subjectLine":"Test"}'

# Check R2 after polling completes
wrangler r2 object get MY_BUCKET renders/camp-001/_matrix.json

# Check one screenshot arrived
wrangler r2 object get MY_BUCKET renders/camp-001/OUTLOOK_2019/screenshot.png \
  --file /tmp/outlook.png
```

---

## Related

- `email-template-versioning-ab-testing-r2.md`
- `email-html-css-rendering-matrix.md`
- `email-testing-debugging.md`

---

## Sources

- Litmus API docs — https://litmus.com/developer
- Cloudflare R2 — https://developers.cloudflare.com/r2/
- Cloudflare Queues delay — https://developers.cloudflare.com/queues/configuration/message-delay/
