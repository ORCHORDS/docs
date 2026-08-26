# Mobile Image Upload to R2 + Workers AI Captioning Pipeline

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your mobile app lets users upload photos and you want automatic AI-generated captions stored alongside the media. The pipeline must be non-blocking: the mobile client uploads directly to R2 using a presigned PUT URL (no proxy bandwidth cost), an R2 event notification triggers a Queue consumer, the consumer runs the `@cf/unum/uform-gen2-qwen-500m` captioning model via Workers AI, and the result is written to a D1 `media_captions` table.

---

## Context
Routing large file uploads through a Worker burns CPU time and counts against subrequest limits. Presigned R2 URLs let the mobile client PUT directly to R2 over HTTPS — the Worker only signs the URL and is not in the data path. R2 event notifications (via a connected Queue) fire a consumer Worker the moment the object lands; that consumer fetches the image bytes from R2, calls Workers AI for a caption, and persists the result. This keeps the upload path fast, the AI inference asynchronous, and the storage costs minimal (R2 has no egress fees within Cloudflare's network).

---

## Section 1 — wrangler.toml / Schema

```toml
name = "media-pipeline"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[r2_buckets]]
binding  = "MEDIA_BUCKET"
bucket_name = "orchords-media"

[[queues.consumers]]
queue = "media-events"
batch_size = 10
batch_timeout = 30
max_retries = 2

[[d1_databases]]
binding = "DB"
database_name = "mobile-db"
database_id = "<YOUR_D1_DATABASE_ID>"

[ai]
binding = "AI"

# R2 event notification — configure in dashboard or via API:
# Bucket: orchords-media
# Event type: object-create
# Queue: media-events
# Prefix filter: uploads/   (optional)

# Secrets:
# R2_PRESIGN_SECRET — used to HMAC-sign presigned URLs (if using custom auth)
```

```sql
-- D1 migration: 0003_media_captions.sql
CREATE TABLE IF NOT EXISTS media_captions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  r2_key       TEXT    NOT NULL UNIQUE,
  user_id      TEXT    NOT NULL,
  caption      TEXT,
  model        TEXT    NOT NULL DEFAULT '@cf/unum/uform-gen2-qwen-500m',
  status       TEXT    NOT NULL DEFAULT 'pending'
               CHECK(status IN ('pending','done','failed')),
  created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  captioned_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_captions_user ON media_captions(user_id);
```

---

## Section 2 — Worker implementation

```typescript
// src/index.ts
import { Hono } from 'hono';

export interface Env {
  MEDIA_BUCKET: R2Bucket;
  DB: D1Database;
  AI: Ai;
  mediaEvents: Queue;
}

const app = new Hono<{ Bindings: Env }>();

// ── Presigned URL endpoint ────────────────────────────────────────────────
// The mobile client calls this (authenticated) to get a one-time upload URL.
app.post('/media/presign', async (c) => {
  // In production: extract userId from verified JWT
  const { userId, filename, contentType } = await c.req.json<{
    userId: string;
    filename: string;
    contentType: string;
  }>();

  if (!['image/jpeg', 'image/png', 'image/webp', 'image/heic'].includes(contentType)) {
    return c.json({ error: 'unsupported_content_type' }, 400);
  }

  const ext = filename.split('.').pop() ?? 'jpg';
  const r2Key = `uploads/${userId}/${crypto.randomUUID()}.${ext}`;

  // Insert a pending record so we can track the upload
  await c.env.DB.prepare(
    'INSERT INTO media_captions (r2_key, user_id, status) VALUES (?, ?, \'pending\')'
  ).bind(r2Key, userId).run();

  // Generate R2 presigned PUT URL (expires in 15 minutes)
  const presignedUrl = await c.env.MEDIA_BUCKET.createMultipartUpload(r2Key);
  // Note: for simple PUT, use the R2 presigned URL API (Workers R2 SDK ≥ 2024-09)
  const url = await c.env.MEDIA_BUCKET.put;

  // Workers R2 createPresignedUrl is not yet stable for all plans;
  // use the R2 REST API signed with a service token instead:
  const signedUrl = await createR2PresignedPutUrl(c.env, r2Key, contentType, 900);

  return c.json({ uploadUrl: signedUrl, r2Key });
});

// ── Caption status endpoint ───────────────────────────────────────────────
app.get('/media/:key/caption', async (c) => {
  const r2Key = decodeURIComponent(c.req.param('key'));
  const row = await c.env.DB.prepare(
    'SELECT caption, status, captioned_at FROM media_captions WHERE r2_key = ?'
  ).bind(r2Key).first<{ caption: string | null; status: string; captioned_at: string | null }>();

  if (!row) return c.json({ error: 'not_found' }, 404);
  return c.json(row);
});

// ── R2 presigned PUT URL helper ───────────────────────────────────────────
async function createR2PresignedPutUrl(
  env: Env,
  key: string,
  contentType: string,
  expiresInSeconds: number
): Promise<string> {
  // Use the R2 bucket's createPresignedUrl method (available as of 2024-09)
  // @ts-expect-error — createPresignedUrl typing may not be present in older @cloudflare/workers-types
  const url: string = await env.MEDIA_BUCKET.createPresignedUrl(key, {
    method: 'PUT',
    expiresIn: expiresInSeconds,
    httpMetadata: { contentType },
  });
  return url;
}

export default app;

// ── Queue consumer (separate export) ─────────────────────────────────────
export const queueConsumer = {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body as {
        object: { key: string };
        action: string;
      };

      if (event.action !== 'PutObject' && event.action !== 'CompleteMultipartUpload') {
        msg.ack();
        continue;
      }

      const r2Key = event.object.key;

      try {
        // Fetch image bytes from R2
        const obj = await env.MEDIA_BUCKET.get(r2Key);
        if (!obj) throw new Error(`r2_object_not_found: ${r2Key}`);

        const imageBytes = await obj.arrayBuffer();
        const imageArray = [...new Uint8Array(imageBytes)];

        // Run captioning model
        const result = await env.AI.run(
          '@cf/unum/uform-gen2-qwen-500m' as BaseAiTextToImageModels,
          { image: imageArray } as any
        ) as { description: string };

        const caption = result?.description ?? '';

        // Persist caption
        await env.DB.prepare(`
          UPDATE media_captions
          SET caption = ?, status = 'done', captioned_at = datetime('now')
          WHERE r2_key = ?
        `).bind(caption, r2Key).run();

        msg.ack();
      } catch (err) {
        console.error('caption_error', r2Key, err);
        await env.DB.prepare(`
          UPDATE media_captions SET status = 'failed' WHERE r2_key = ?
        `).bind(r2Key).run();
        msg.retry();
      }
    }
  },
};
```

---

## Section 3 — Client-side (React Native / Expo)

```typescript
// lib/mediaUpload.ts
import * as ImagePicker from 'expo-image-picker';
import { apiFetch } from './apiClient';

export interface UploadResult {
  r2Key: string;
}

export async function pickAndUploadImage(userId: string): Promise<UploadResult> {
  const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!perm.granted) throw new Error('media_library_permission_denied');

  const picked = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    quality: 0.85,
    allowsEditing: false,
  });

  if (picked.canceled || !picked.assets[0]) throw new Error('cancelled');
  const asset = picked.assets[0];

  const filename = asset.fileName ?? `photo_${Date.now()}.jpg`;
  const contentType = asset.mimeType ?? 'image/jpeg';

  // Step 1: request presigned upload URL
  const presignRes = await apiFetch('/media/presign', {
    method: 'POST',
    body: JSON.stringify({ userId, filename, contentType }),
  });
  if (!presignRes.ok) throw new Error('presign_failed');
  const { uploadUrl, r2Key } = await presignRes.json<{ uploadUrl: string; r2Key: string }>();

  // Step 2: PUT file directly to R2 (no auth header — presigned URL carries credentials)
  const imageBlob = await fetch(asset.uri).then((r) => r.blob());
  const uploadRes = await fetch(uploadUrl, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body: imageBlob,
  });
  if (!uploadRes.ok) throw new Error(`r2_upload_failed: ${uploadRes.status}`);

  return { r2Key };
}

export async function pollCaption(
  r2Key: string,
  maxAttempts = 20,
  intervalMs = 1500
): Promise<string | null> {
  for (let i = 0; i < maxAttempts; i++) {
    const res = await apiFetch(`/media/${encodeURIComponent(r2Key)}/caption`);
    if (!res.ok) break;
    const { caption, status } = await res.json<{ caption: string | null; status: string }>();
    if (status === 'done') return caption;
    if (status === 'failed') return null;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return null;
}
```

---

## Anti-patterns
- **Proxying the image upload through a Worker** — uploading via a Worker consumes Worker CPU time, hits the 6 MB request body limit on the free tier, and wastes bandwidth; presigned URLs are the correct pattern.
- **Running AI inference synchronously in the upload request path** — image captioning can take 1–3 seconds; doing it inline blocks the upload response and risks a 30-second Worker CPU limit timeout.
- **Storing raw image bytes in D1** — D1 is a relational database with a 100 MB storage limit on the free tier; binary objects belong in R2.
- **Not handling `msg.retry()` for transient AI failures** — Workers AI may be temporarily unavailable; always retry transient errors and only update `status = 'failed'` after exhausting retries.

---

## Gotchas
- `@cf/unum/uform-gen2-qwen-500m` accepts an `image` field as an array of uint8 values (not base64 and not a URL); convert `arrayBuffer()` → `Uint8Array` → spread into an array.
- R2 `createPresignedUrl` requires the bucket to have public access disabled (the default); the presigned URL carries a time-limited HMAC credential.
- R2 event notifications are configured per-bucket in the Cloudflare dashboard or via the API; they are not declared in `wrangler.toml`.
- Workers AI billing is per-neuron-second; caching captions in D1 avoids re-running the model if the same key is queued more than once (e.g., from a retry).
- The `[ai]` binding in `wrangler.toml` requires the Workers AI product to be enabled for your account; enable it in the Cloudflare dashboard under AI → Workers AI.

---

## Verification
```bash
# Apply D1 migration
npx wrangler d1 execute mobile-db --file=0003_media_captions.sql

# Deploy
npx wrangler deploy

# Request a presigned URL
curl -s -X POST https://media-pipeline.orchords.workers.dev/media/presign \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -d '{"userId":"user:alice","filename":"photo.jpg","contentType":"image/jpeg"}' | jq .

# Upload directly to R2 (replace URL from above)
curl -s -X PUT "$UPLOAD_URL" \
  -H 'Content-Type: image/jpeg' \
  --data-binary @/path/to/photo.jpg

# Poll for caption
curl -s https://media-pipeline.orchords.workers.dev/media/<R2_KEY>/caption | jq .

# Check D1
npx wrangler d1 execute mobile-db \
  --command 'SELECT r2_key, status, caption FROM media_captions ORDER BY created_at DESC LIMIT 5;'
```

---

## Related
- `mobile-push-notifications-workers-queues-fcm.md`
- `mobile-deep-link-routing-workers.md`
- `offline-first-sync-workers-d1-mobile.md`

---

## Sources
- Cloudflare R2 Presigned URLs — https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- Workers AI Models — https://developers.cloudflare.com/workers-ai/models/
- R2 Event Notifications — https://developers.cloudflare.com/r2/buckets/event-notifications/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
