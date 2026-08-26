# Vitest R2 Multipart Upload Testing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

R2 multipart upload introduces a three-phase lifecycle—`createMultipartUpload`, sequential `uploadPart` calls, and `completeMultipartUpload` or `abortMultipartUpload`—that is hard to exercise in unit tests without a real bucket. Developers need confidence that chunked uploads complete correctly, partial failures abort cleanly, and part ETags are assembled in the right order, all without deploying to production.

## Context

Cloudflare R2 exposes the S3-compatible multipart upload API on the `R2Bucket` binding. The `@cloudflare/vitest-pool-workers` pool, backed by Miniflare, provides a full in-process R2 implementation that supports multipart semantics. Because the pool resets bucket state between test files by default, each suite starts with an empty bucket, keeping tests independent.

Key R2 multipart types from `@cloudflare/workers-types`:

- `R2MultipartUpload` – created by `bucket.createMultipartUpload(key, options?)`
- `R2UploadedPart` – returned by `multipart.uploadPart(partNumber, body)`
- `R2Object` – returned on successful `multipart.complete(parts)`

Minimum part size on production R2 is 5 MiB, but Miniflare removes this floor in tests, so 1-byte parts work.

## Setup

Install pool workers and configure Vitest:

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    pool: '@cloudflare/vitest-pool-workers',
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml' },
      },
    },
  },
});
```

```toml
# wrangler.toml
[[r2_buckets]]
binding = "BUCKET"
bucket_name = "test-bucket"
```

Declare the binding in your test environment type:

```typescript
// env.d.ts
interface Env {
  BUCKET: R2Bucket;
}
```

## Basic Multipart Upload

```typescript
// tests/r2-multipart.test.ts
import { env } from 'cloudflare:test';
import { describe, it, expect, beforeEach } from 'vitest';

describe('R2 multipart upload', () => {
  beforeEach(async () => {
    // Ensure bucket is empty at the start of each test
    const listed = await env.BUCKET.list();
    await Promise.all(listed.objects.map((o) => env.BUCKET.delete(o.key)));
  });

  it('completes a multipart upload assembling parts in order', async () => {
    const key = 'large-file.bin';
    const upload = await env.BUCKET.createMultipartUpload(key, {
      httpMetadata: { contentType: 'application/octet-stream' },
    });

    const part1 = await upload.uploadPart(1, new Uint8Array([0x01, 0x02, 0x03]));
    const part2 = await upload.uploadPart(2, new Uint8Array([0x04, 0x05, 0x06]));

    const object = await upload.complete([part1, part2]);

    expect(object.key).toBe(key);
    expect(object.size).toBe(6);

    const stored = await env.BUCKET.get(key);
    expect(stored).not.toBeNull();
    const body = new Uint8Array(await stored!.arrayBuffer());
    expect(body).toEqual(new Uint8Array([0x01, 0x02, 0x03, 0x04, 0x05, 0x06]));
  });

  it('aborts an in-progress upload and leaves no object', async () => {
    const key = 'aborted-file.bin';
    const upload = await env.BUCKET.createMultipartUpload(key);
    await upload.uploadPart(1, new Uint8Array([0xde, 0xad]));

    await upload.abort();

    const stored = await env.BUCKET.get(key);
    expect(stored).toBeNull();
  });
});
```

## Testing Metadata and Custom Headers

```typescript
it('preserves custom metadata through multipart completion', async () => {
  const key = 'metadata-file.json';
  const upload = await env.BUCKET.createMultipartUpload(key, {
    httpMetadata: {
      contentType: 'application/json',
      cacheControl: 'public, max-age=86400',
    },
    customMetadata: {
      'x-source': 'upload-service',
      'x-version': '2',
    },
  });

  const encoder = new TextEncoder();
  const part1 = await upload.uploadPart(1, encoder.encode('{"chunk":1}'));
  const part2 = await upload.uploadPart(2, encoder.encode('{"chunk":2}'));
  const object = await upload.complete([part1, part2]);

  const head = await env.BUCKET.head(key);
  expect(head?.httpMetadata?.contentType).toBe('application/json');
  expect(head?.customMetadata?.['x-source']).toBe('upload-service');
});
```

## Simulating Part Upload Failure and Retry

```typescript
it('allows re-uploading a failed part before completing', async () => {
  const key = 'retry-file.bin';
  const upload = await env.BUCKET.createMultipartUpload(key);

  // First attempt at part 1 (simulate partial corruption — we just re-upload)
  await upload.uploadPart(1, new Uint8Array([0xff, 0xff]));
  // Re-upload part 1 with corrected data; only the latest ETag is used
  const goodPart1 = await upload.uploadPart(1, new Uint8Array([0x01]));
  const part2 = await upload.uploadPart(2, new Uint8Array([0x02]));

  const object = await upload.complete([goodPart1, part2]);
  expect(object.size).toBe(2);

  const body = new Uint8Array(await (await env.BUCKET.get(key))!.arrayBuffer());
  expect(body).toEqual(new Uint8Array([0x01, 0x02]));
});
```

## Testing Out-of-Order Part Submission

```typescript
it('rejects completion when parts array is out of order', async () => {
  const key = 'ooo-file.bin';
  const upload = await env.BUCKET.createMultipartUpload(key);

  const part1 = await upload.uploadPart(1, new Uint8Array([0xaa]));
  const part2 = await upload.uploadPart(2, new Uint8Array([0xbb]));

  // Intentionally swap part order — R2 spec requires ascending part numbers
  await expect(upload.complete([part2, part1])).rejects.toThrow();
});
```

## Anti-patterns

- **Using `put()` for large-file integration tests** – `put()` buffers the whole body in memory and does not exercise the multipart lifecycle; use `createMultipartUpload` for files intended to be chunked.
- **Ignoring returned `R2UploadedPart`** – Part ETags are opaque handles required by `complete()`; storing the part number alone is not enough.
- **Not calling `abort()` in error paths** – Incomplete uploads accumulate state. Always abort on failure to prevent resource leaks, even in test helpers.
- **Assuming Miniflare enforces the 5 MiB minimum** – Production enforces it; Miniflare does not. Write a separate validation test that checks your upload code rejects parts below the production limit.

## Gotchas

- `complete()` receives an array of `R2UploadedPart`, not plain `{ partNumber, etag }` objects. Pass the exact values returned by `uploadPart()`.
- `createMultipartUpload` is called on the bucket, not on the Worker's `fetch` handler directly. Test it via `env.BUCKET` in the pool-workers environment without importing the Worker module.
- Miniflare's R2 is in-memory: all state is lost when the test process exits. Do not rely on uploads created in one Vitest worker process being visible in another.
- `head()` after `complete()` reflects the metadata from `createMultipartUpload`, not from any individual `uploadPart` call.

## Verification

```bash
# Run multipart upload tests only
npx vitest run tests/r2-multipart.test.ts

# Confirm coverage of all three lifecycle phases
npx vitest run --reporter=verbose tests/r2-multipart.test.ts | grep -E "(createMultipartUpload|uploadPart|complete|abort)"
```

Expected: all tests pass; no "unresolved R2UploadedPart" errors in output.

## Related

- `r2-bucket-miniflare-testing.md` — basic R2 put/get/delete patterns
- `vitest-cloudflare-pool-workers.md` — pool-workers Vitest setup
- `test-doubles-cloudflare-workers.md` — manual binding mocks as fallback

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#multipart-upload-commands
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
