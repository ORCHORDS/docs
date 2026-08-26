# R2 Cross-Account Replication via Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

R2 does not have native cross-account replication.
Objects written to a production account's R2 bucket need to be replicated to a separate DR/archive Cloudflare account without routing through a third-party intermediary.
Existing solutions using `aws s3 sync` either miss real-time writes or require a persistent VM.
A Workers-based pipeline triggered by R2 Event Notifications replicates objects as they land, with retry and observability built in.

## Context

Cloudflare R2 Event Notifications (2024+) fire a message to a Queue whenever an object is created, overwritten, or deleted in a bucket.
A Queue Consumer Worker processes these events and copies the object to the destination account's R2 bucket via the S3-compatible API using a scoped API token from the destination account.
The destination account exposes the bucket endpoint at `https://<ACCOUNT_ID>.r2.cloudflarestorage.com/<BUCKET>`.
Authentication uses AWS Signature V4 with Cloudflare R2 credentials (Access Key ID + Secret Access Key generated in the destination account dashboard).

## R2 Event Notification Queue Consumer

```typescript
// src/replicator.ts
export interface Env {
  SOURCE_BUCKET: R2Bucket;
  DEST_ACCOUNT_ID: string;
  DEST_BUCKET_NAME: string;
  DEST_R2_ACCESS_KEY_ID: string;
  DEST_R2_SECRET_ACCESS_KEY: string;
  REPLICATION_DLQ: Queue;  // dead-letter queue for failed replications
}

interface R2EventMessage {
  account: string;
  bucket: string;
  object: { key: string; size: number; etag: string };
  action: 'PutObject' | 'DeleteObject' | 'CopyObject';
}

export default {
  async queue(batch: MessageBatch<R2EventMessage>, env: Env): Promise<void> {
    await Promise.all(
      batch.messages.map(async (msg) => {
        try {
          await replicateObject(msg.body, env);
          msg.ack();
        } catch (err) {
          console.error(`Failed to replicate ${msg.body.object.key}:`, err);
          msg.retry({ delaySeconds: 30 });
        }
      }),
    );
  },
};
```

## Object Copy via S3-Compatible API with SigV4

```typescript
async function replicateObject(event: R2EventMessage, env: Env): Promise<void> {
  if (event.action === 'DeleteObject') {
    await deleteFromDest(event.object.key, env);
    return;
  }

  // Fetch from source bucket (Worker binding — zero egress cost)
  const obj = await env.SOURCE_BUCKET.get(event.object.key);
  if (!obj) {
    console.warn(`Object not found in source: ${event.object.key}`);
    return;
  }

  const body = await obj.arrayBuffer();
  const destUrl = `https://${env.DEST_ACCOUNT_ID}.r2.cloudflarestorage.com/${env.DEST_BUCKET_NAME}/${event.object.key}`;

  const signed = await signR2Request('PUT', destUrl, body, {
    accessKeyId: env.DEST_R2_ACCESS_KEY_ID,
    secretAccessKey: env.DEST_R2_SECRET_ACCESS_KEY,
    contentType: obj.httpMetadata?.contentType ?? 'application/octet-stream',
    customMetadata: obj.customMetadata,
  });

  const res = await fetch(destUrl, {
    method: 'PUT',
    headers: signed.headers,
    body,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Dest PUT failed (${res.status}): ${text}`);
  }
}
```

## AWS Signature V4 for R2 (Workers-native, no SDK)

```typescript
async function signR2Request(
  method: string,
  url: string,
  body: ArrayBuffer,
  opts: {
    accessKeyId: string;
    secretAccessKey: string;
    contentType: string;
    customMetadata?: Record<string, string>;
  },
): Promise<{ headers: Record<string, string> }> {
  const parsed = new URL(url);
  const now = new Date();
  const dateStamp = now.toISOString().slice(0, 10).replace(/-/g, '');
  const amzDate = now.toISOString().replace(/[:-]|\.\d+/g, '').slice(0, 15) + 'Z';

  const bodyHash = Array.from(
    new Uint8Array(await crypto.subtle.digest('SHA-256', body)),
  ).map(b => b.toString(16).padStart(2, '0')).join('');

  const headers: Record<string, string> = {
    'host': parsed.host,
    'x-amz-date': amzDate,
    'x-amz-content-sha256': bodyHash,
    'content-type': opts.contentType,
  };

  if (opts.customMetadata) {
    for (const [k, v] of Object.entries(opts.customMetadata))
      headers[`x-amz-meta-${k}`] = v;
  }

  const sortedHeaders = Object.keys(headers).sort();
  const canonicalHeaders = sortedHeaders.map(k => `${k}:${headers[k]}`).join('\n') + '\n';
  const signedHeaders = sortedHeaders.join(';');
  const canonicalRequest = [method, parsed.pathname, '', canonicalHeaders, signedHeaders, bodyHash].join('\n');

  const region = 'auto';
  const service = 's3';
  const scope = `${dateStamp}/${region}/${service}/aws4_request`;
  const reqHash = Array.from(
    new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalRequest))),
  ).map(b => b.toString(16).padStart(2, '0')).join('');

  const stringToSign = ['AWS4-HMAC-SHA256', amzDate, scope, reqHash].join('\n');

  const sign = async (key: ArrayBuffer, data: string): Promise<ArrayBuffer> => {
    const k = await crypto.subtle.importKey('raw', key, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    return crypto.subtle.sign('HMAC', k, new TextEncoder().encode(data));
  };

  const kDate = await sign(new TextEncoder().encode(`AWS4${opts.secretAccessKey}`), dateStamp);
  const kRegion = await sign(kDate, region);
  const kService = await sign(kRegion, service);
  const kSigning = await sign(kService, 'aws4_request');
  const sig = Array.from(new Uint8Array(await sign(kSigning, stringToSign))).map(b => b.toString(16).padStart(2, '0')).join('');

  headers['authorization'] = `AWS4-HMAC-SHA256 Credential=${opts.accessKeyId}/${scope}, SignedHeaders=${signedHeaders}, Signature=${sig}`;
  return { headers };
}
```

## Handling Deletes and Large Objects

```typescript
async function deleteFromDest(key: string, env: Env): Promise<void> {
  const destUrl = `https://${env.DEST_ACCOUNT_ID}.r2.cloudflarestorage.com/${env.DEST_BUCKET_NAME}/${key}`;
  const signed = await signR2Request('DELETE', destUrl, new ArrayBuffer(0), {
    accessKeyId: env.DEST_R2_ACCESS_KEY_ID,
    secretAccessKey: env.DEST_R2_SECRET_ACCESS_KEY,
    contentType: '',
  });
  const res = await fetch(destUrl, { method: 'DELETE', headers: signed.headers });
  if (!res.ok && res.status !== 404) throw new Error(`Delete failed: ${res.status}`);
}

// For objects > 100 MB, use multipart upload — initiate on dest, stream parts from source
// wrangler.toml: set [limits] cpu_ms = 30000 and use streaming body
```

## Anti-patterns

- **Polling source bucket with list() instead of event notifications** — list-based polling misses concurrent writes and adds per-million-list-ops cost.
- **Fetching object from source via HTTP instead of binding** — cross-Internet fetches incur egress fees; always use the R2 binding (`env.SOURCE_BUCKET.get()`) for free intra-account reads.
- **No dead-letter queue** — without DLQ, replication failures silently drop objects; always configure a Queue with `max_retries` and a DLQ binding.
- **Replicating metadata-only without body validation** — always verify `etag` of the replicated object matches source before acknowledging the queue message.

## Gotchas

- R2 Event Notifications deliver **at least once** — the consumer must handle duplicate `PutObject` events idempotently (overwrite is safe for most use cases).
- Objects larger than 128 MB require multipart upload to the destination; the Worker 128 MB memory limit means large objects must be streamed using range reads.
- The destination account's R2 bucket must have **Public Access** or **CORS** configured only if the Worker cannot use the private S3 endpoint with credentials.
- Cross-account R2 access keys expire if unused for 90 days; rotate them via the destination account dashboard and update Worker secrets.

## Verification

```bash
# Upload a test object to source
wrangler r2 object put SOURCE_BUCKET/test/hello.txt --file /tmp/hello.txt

# Check it arrived in destination (using dest credentials)
AWS_ACCESS_KEY_ID=$DEST_KEY AWS_SECRET_ACCESS_KEY=$DEST_SECRET \
  aws s3 ls s3://dest-bucket/test/ --endpoint-url "https://$DEST_ACCOUNT_ID.r2.cloudflarestorage.com"

# Monitor queue consumer logs
wrangler tail r2-replicator --format pretty

# Check DLQ depth for failures
wrangler queues consumer list r2-replication-dlq
```

## Related

- `cloudflare-r2-backup-restore-strategy.md`
- `object-storage-replication.md`
- `r2-lifecycle-archival-glacier-strategy.md`
- `cloudflare-workers-api-token-scoping.md`

## Sources

- https://developers.cloudflare.com/r2/buckets/event-notifications/
- https://developers.cloudflare.com/r2/api/s3/api/
- https://developers.cloudflare.com/queues/reference/how-queues-works/
