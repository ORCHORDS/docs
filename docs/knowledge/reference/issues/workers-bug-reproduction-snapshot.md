# Bug Reproduction Snapshot Capture in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A user reports a bug that is impossible to reproduce because there is no record of the exact request that caused it. You need a Worker middleware that intercepts 5xx responses, captures the full request/response context — headers, body, Cloudflare `cf` object, relevant env metadata — scrubs PII, stores the snapshot in R2, and returns a `X-Snapshot-ID` header that engineers can use to replay the exact failing request.

## Context

The snapshot Worker sits in front of your origin as a Cloudflare Worker. On any response with status ≥ 500, it clones the request and response, scrubs sensitive headers and body fields, writes the context to R2 with a 72-hour TTL, and appends a `X-Snapshot-ID` to the response the client receives. A separate `/replay/:id` endpoint reconstructs and re-issues the original request. Cleanup runs on a cron every hour.

## Solution

```typescript
// workers-bug-snapshot/src/index.ts
export interface Env {
  SNAPSHOT_BUCKET: R2Bucket;
  ORIGIN_URL: string;
  SNAPSHOT_TTL_HOURS: string;  // default '72'
  INTERNAL_REPLAY_SECRET: string;
  CAPTURE_BODY_MAX_BYTES: string; // default '65536' (64 KB)
}

// ---------------------------------------------------------------------------
// PII scrubbing
// ---------------------------------------------------------------------------
const SCRUB_HEADERS = new Set([
  'authorization', 'cookie', 'set-cookie', 'x-api-key',
  'x-auth-token', 'proxy-authorization', 'www-authenticate',
]);

const SCRUB_BODY_FIELDS = new Set([
  'password', 'token', 'secret', 'credit_card', 'card_number',
  'ssn', 'cvv', 'pin', 'access_token', 'refresh_token',
]);

function scrubHeaders(headers: Headers): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of headers.entries()) {
    out[k] = SCRUB_HEADERS.has(k.toLowerCase()) ? '[REDACTED]' : v;
  }
  return out;
}

function scrubJsonBody(raw: string): string {
  try {
    const parsed = JSON.parse(raw);
    const scrub = (obj: unknown): unknown => {
      if (Array.isArray(obj)) return obj.map(scrub);
      if (obj && typeof obj === 'object') {
        return Object.fromEntries(
          Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
            k,
            SCRUB_BODY_FIELDS.has(k.toLowerCase()) ? '[REDACTED]' : scrub(v),
          ]),
        );
      }
      return obj;
    };
    return JSON.stringify(scrub(parsed));
  } catch {
    return '[non-JSON body — not stored]';
  }
}

// ---------------------------------------------------------------------------
// Snapshot structure
// ---------------------------------------------------------------------------
interface Snapshot {
  id: string;
  captured_at: string;
  expires_at: string;
  request: {
    method: string;
    url: string;
    headers: Record<string, string>;
    body: string | null;
    cf: Record<string, unknown>;
  };
  response: {
    status: number;
    headers: Record<string, string>;
    body: string | null;
  };
  env_meta: {
    worker_version: string;
    colo: string;
  };
}

// ---------------------------------------------------------------------------
// Capture and store snapshot
// ---------------------------------------------------------------------------
async function captureSnapshot(
  env: Env,
  req: Request,
  res: Response,
): Promise<string> {
  const id = crypto.randomUUID();
  const maxBytes = Number(env.CAPTURE_BODY_MAX_BYTES || '65536');
  const ttlHours = Number(env.SNAPSHOT_TTL_HOURS || '72');
  const now = new Date();
  const expires = new Date(now.getTime() + ttlHours * 3_600_000);

  // Read bodies — guarded to avoid consuming streams the origin already sent
  async function readBody(bodyInit: ReadableStream | null, contentType: string | null): Promise<string | null> {
    if (!bodyInit) return null;
    try {
      const text = await new Response(bodyInit).text();
      if (text.length > maxBytes) return text.slice(0, maxBytes) + `\n[TRUNCATED at ${maxBytes} bytes]`;
      if (contentType?.includes('application/json')) return scrubJsonBody(text);
      return text;
    } catch {
      return '[could not read body]';
    }
  }

  const [reqClone, resClone] = [req.clone(), res.clone()];

  const reqBody = await readBody(
    reqClone.body,
    req.headers.get('content-type'),
  );
  const resBody = await readBody(
    resClone.body,
    res.headers.get('content-type'),
  );

  const snapshot: Snapshot = {
    id,
    captured_at: now.toISOString(),
    expires_at: expires.toISOString(),
    request: {
      method: req.method,
      url: req.url,
      headers: scrubHeaders(req.headers),
      body: reqBody,
      cf: req.cf as Record<string, unknown> ?? {},
    },
    response: {
      status: res.status,
      headers: scrubHeaders(res.headers),
      body: resBody,
    },
    env_meta: {
      worker_version: '1.0.0',
      colo: (req.cf as any)?.colo ?? 'unknown',
    },
  };

  await env.SNAPSHOT_BUCKET.put(
    `snapshots/${id}.json`,
    JSON.stringify(snapshot, null, 2),
    {
      httpMetadata: { contentType: 'application/json' },
      customMetadata: {
        expires_at: expires.toISOString(),
        status: String(res.status),
      },
    },
  );

  return id;
}

// ---------------------------------------------------------------------------
// Replay endpoint: reconstruct and re-issue the original request
// ---------------------------------------------------------------------------
async function replaySnapshot(env: Env, id: string, req: Request): Promise<Response> {
  const secret = <redacted-secret>'X-Replay-Secret');
  if (secret !== env.INTERNAL_REPLAY_SECRET) {
    return new Response('Forbidden', { status: 403 });
  }

  const obj = await env.SNAPSHOT_BUCKET.get(`snapshots/${id}.json`);
  if (!obj) return new Response('Snapshot not found', { status: 404 });

  const snapshot: Snapshot = await obj.json();

  if (new Date(snapshot.expires_at) < new Date()) {
    return new Response('Snapshot expired', { status: 410 });
  }

  // Reconstruct request — omit scrubbed/redacted headers
  const replayHeaders = new Headers();
  for (const [k, v] of Object.entries(snapshot.request.headers)) {
    if (v !== '[REDACTED]') replayHeaders.set(k, v);
  }
  replayHeaders.set('X-Replay-Snapshot-ID', id);
  replayHeaders.set('X-Replay-Captured-At', snapshot.captured_at);

  const replayReq = new Request(snapshot.request.url, {
    method: snapshot.request.method,
    headers: replayHeaders,
    body: snapshot.request.body && !['GET', 'HEAD'].includes(snapshot.request.method)
      ? snapshot.request.body
      : undefined,
  });

  const originRes = await fetch(replayReq);
  return new Response(originRes.body, {
    status: originRes.status,
    headers: originRes.headers,
  });
}

// ---------------------------------------------------------------------------
// TTL-based cleanup (cron)
// ---------------------------------------------------------------------------
async function cleanupExpiredSnapshots(env: Env) {
  const now = new Date().toISOString();
  // R2 list does not filter by metadata — iterate and delete expired objects
  let cursor: string | undefined;
  do {
    const listed = await env.SNAPSHOT_BUCKET.list({
      prefix: 'snapshots/',
      limit: 100,
      cursor,
    });
    for (const obj of listed.objects) {
      const expiresAt = obj.customMetadata?.expires_at;
      if (expiresAt && expiresAt < now) {
        await env.SNAPSHOT_BUCKET.delete(obj.key);
      }
    }
    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);
}

// ---------------------------------------------------------------------------
// Middleware: proxy to origin and snapshot on 5xx
// ---------------------------------------------------------------------------
async function proxyAndSnapshot(req: Request, env: Env): Promise<Response> {
  // Forward to origin — clone request before forwarding to preserve body
  const originReq = new Request(env.ORIGIN_URL + new URL(req.url).pathname + new URL(req.url).search, {
    method: req.method,
    headers: req.headers,
    body: req.body,
    redirect: 'manual',
  });

  const originRes = await fetch(originReq);

  if (originRes.status >= 500) {
    // Clone response before consuming body — we need to return it to the client too
    const [forClient, forCapture] = originRes.tee();
    const snapshotRes = new Response(forCapture.body, {
      status: originRes.status,
      headers: originRes.headers,
    });

    // Capture snapshot in background — do not block the client response
    const snapshotId = await captureSnapshot(env, req, snapshotRes);

    const clientRes = new Response(forClient.body, {
      status: originRes.status,
      headers: new Headers(originRes.headers),
    });
    clientRes.headers.set('X-Snapshot-ID', snapshotId);
    return clientRes;
  }

  return originRes;
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // Internal replay endpoint
    const replayMatch = url.pathname.match(/^\/replay\/([0-9a-f-]{36})$/);
    if (replayMatch) {
      return replaySnapshot(env, replayMatch[1], req);
    }

    return proxyAndSnapshot(req, env);
  },

  async scheduled(_event: ScheduledEvent, env: Env) {
    await cleanupExpiredSnapshots(env);
  },
};
```

**wrangler.toml snippet:**

```toml
[triggers]
crons = ["0 * * * *"]  # hourly cleanup

[vars]
SNAPSHOT_TTL_HOURS = "72"
CAPTURE_BODY_MAX_BYTES = "65536"

[[r2_buckets]]
binding = "SNAPSHOT_BUCKET"
bucket_name = "bug-snapshots"
```

## Implementation Details

- `Response.tee()` (from the Streams API) splits the response body into two identical streams: one returned to the client, one consumed for snapshot storage. This avoids double-buffering the full body in memory.
- `scrubHeaders` redacts a fixed set of sensitive headers. Extend `SCRUB_HEADERS` for your own custom auth headers.
- `scrubJsonBody` recursively walks the JSON tree and replaces values at any depth where the key matches `SCRUB_BODY_FIELDS`.
- Non-JSON bodies (form data, binary) are stored as raw text with the size cap applied. Add content-type-specific scrubbers as needed.
- `cleanupExpiredSnapshots` paginates R2 listings with a cursor to handle large numbers of objects without hitting the 100-item default limit.
- The replay endpoint deliberately omits redacted headers (those with value `[REDACTED]`) so replayed requests cannot impersonate credentials.

## Anti-patterns

- **Storing snapshots without a TTL.** R2 has no native expiry on objects. Without the cleanup cron, storage grows unbounded. Always store `expires_at` in `customMetadata` and clean up on a cron.
- **Blocking the client response while writing to R2.** The `captureSnapshot` call should be wrapped in `ctx.waitUntil()` in production to avoid increasing client latency. In this implementation it is `await`-ed inline for clarity; move it to `ctx.waitUntil` in real deployments.
- **Storing full authorization tokens in snapshots.** Even in an internal store, credentials at rest are a risk. The `SCRUB_HEADERS` list must include all auth-bearing headers.
- **Replaying snapshots in production without isolation.** Replay endpoints should target a staging origin or a feature-flag-gated path, not live production, to avoid unintended side effects.

## Gotchas

- `req.cf` is only available inside Cloudflare Workers. In `wrangler dev` local mode it is `undefined` — guard with `?? {}`.
- `Response.tee()` is a Streams API method, not a Cloudflare-specific one. It is available in all modern Workers runtimes.
- The body of a `GET` or `HEAD` request is always `null` per the Fetch spec. The replay handler checks the method before setting the body.
- R2 object keys are limited to 1,024 bytes. UUIDs are 36 characters — the `snapshots/<uuid>.json` key is well within the limit.
- If the origin itself streams the response, `tee()` will consume both halves concurrently. Ensure the origin does not send partial/chunked bodies that take longer than the Worker CPU time limit (50ms on the free tier, 30s on paid).

## Verification

1. Deploy the Worker in front of a test origin that returns HTTP 500 on `/error`.
2. Send `GET /error`. Assert the client response includes `X-Snapshot-ID` header with a UUID value.
3. Fetch `snapshots/<uuid>.json` directly from R2 (via `wrangler r2 object get`) and assert: the `request.url` is correct, `authorization` header is `[REDACTED]`, and `response.status` is 500.
4. Send `POST /replay/<uuid>` with `X-Replay-Secret`. Assert the Worker re-issues the request to the origin and returns the origin's response.
5. Manually set `expires_at` to a past timestamp on a snapshot object. Run `wrangler dev --test-scheduled`. Assert the object is deleted from R2.

## Related

- `workers-postmortem-generator.md` — postmortems that reference snapshot IDs
- `workers-github-issue-triage-bot.md` — issue triage that links snapshot IDs as reproduction evidence
- `workers-sla-breach-auto-escalation.md` — escalation notifications that include snapshot links

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/workers/runtime-apis/streams/
- https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream/tee
- https://developers.cloudflare.com/workers/runtime-apis/request/#the-cf-property-requestinitcfproperties
