# Miniflare Workers R2 Multipart Upload Testing

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You have a Cloudflare Worker that orchestrates S3-compatible multipart uploads to R2 — initiating the upload, generating per-part presigned URLs, and completing or aborting the sequence. Unit tests that call `fetch()` directly miss the real R2 multipart state machine (part ETags, minimum part sizes, ordering) and give false confidence. You need Miniflare's in-process R2 binding to exercise the full happy path and edge cases (abort mid-flight, out-of-order parts, undersized parts) without hitting a live R2 bucket.

## Context

R2's multipart upload API has three distinct phases:
- `createMultipartUpload` → returns `uploadId`
- `uploadPart` (per chunk, min 5 MB except last) → returns part `ETag`
- `completeMultipartUpload` (ordered part list with ETags) → final object

Miniflare 3.x ships a faithful R2 simulation that enforces the 5 MB minimum, tracks ETags per `(uploadId, partNumber)`, and rejects completion if any ETag mismatches. Testing with `@cloudflare/vitest-pool-workers` gives you a real R2 binding inside a Worker context, but for pure-unit isolation of the Worker business logic (error handling, retry, header generation) you may want to drive Miniflare directly via its programmatic API without spinning up Vitest's pool. This article covers the Miniflare-direct approach.

## 1. Project Setup

```bash
npm install --save-dev miniflare wrangler
```

```jsonc
// wrangler.toml
name = "upload-worker"

[[r2_buckets]]
binding = "UPLOAD_BUCKET"
bucket_name = "uploads"
```

```typescript
// src/worker.ts
export interface Env {
  UPLOAD_BUCKET: R2Bucket;
}

export interface MultipartSession {
  uploadId: string;
  key: string;
  parts: { partNumber: number; etag: string }[];
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const action = url.searchParams.get("action");
    const key = url.searchParams.get("key") ?? "unknown";

    if (action === "initiate") {
      const upload = await env.UPLOAD_BUCKET.createMultipartUpload(key);
      return Response.json({ uploadId: upload.uploadId, key });
    }

    if (action === "upload-part") {
      const uploadId = url.searchParams.get("uploadId")!;
      const partNumber = Number(url.searchParams.get("partNumber") ?? "1");
      const upload = env.UPLOAD_BUCKET.resumeMultipartUpload(key, uploadId);
      const part = await upload.uploadPart(partNumber, req.body!);
      return Response.json({ partNumber, etag: part.etag });
    }

    if (action === "complete") {
      const body = await req.json<{ uploadId: string; parts: { partNumber: number; etag: string }[] }>();
      const upload = env.UPLOAD_BUCKET.resumeMultipartUpload(key, body.uploadId);
      await upload.complete(body.parts);
      return Response.json({ status: "completed", key });
    }

    if (action === "abort") {
      const uploadId = url.searchParams.get("uploadId")!;
      const upload = env.UPLOAD_BUCKET.resumeMultipartUpload(key, uploadId);
      await upload.abort();
      return new Response(null, { status: 204 });
    }

    return new Response("Unknown action", { status: 400 });
  },
};
```

## 2. Miniflare Test Harness

```typescript
// test/multipart.test.ts
import { Miniflare } from "miniflare";
import { describe, it, beforeEach, afterEach, expect } from "vitest";

const FIVE_MB = 5 * 1024 * 1024;

let mf: Miniflare;

beforeEach(async () => {
  mf = new Miniflare({
    scriptPath: "./dist/worker.js",      // built with `wrangler build --dry-run`
    modules: true,
    r2Buckets: ["UPLOAD_BUCKET"],
    bindings: {},
  });
  await mf.ready;
});

afterEach(async () => {
  await mf.dispose();
});

async function workerFetch(path: string, init?: RequestInit): Promise<Response> {
  return mf.dispatchFetch(`http://worker${path}`, init);
}
```

## 3. Happy-Path: Initiate → Upload Parts → Complete

```typescript
describe("happy path", () => {
  it("completes a two-part upload and object is readable", async () => {
    // Initiate
    const initRes = await workerFetch("/upload?action=initiate&key=<redacted-secret>
    expect(initRes.status).toBe(200);
    const { uploadId, key } = await initRes.json<{ uploadId: string; key: string }>();
    expect(uploadId).toBeTruthy();

    // Part 1 — exactly 5 MB
    const part1Body = new Uint8Array(FIVE_MB).fill(0xab);
    const p1Res = await workerFetch(
      `/upload?action=upload-part&key=${key}&uploadId=${uploadId}&partNumber=1`,
      { method: "PUT", body: part1Body }
    );
    const { etag: etag1 } = await p1Res.json<{ etag: string }>();
    expect(etag1).toMatch(/^[a-f0-9]{32}$/);

    // Part 2 — last part may be smaller
    const part2Body = new Uint8Array(1024).fill(0xcd);
    const p2Res = await workerFetch(
      `/upload?action=upload-part&key=${key}&uploadId=${uploadId}&partNumber=2`,
      { method: "PUT", body: part2Body }
    );
    const { etag: etag2 } = await p2Res.json<{ etag: string }>();

    // Complete
    const completeRes = await workerFetch(`/upload?action=complete&key=${key}`, {
      method: "POST",
      body: JSON.stringify({
        uploadId,
        parts: [
          { partNumber: 1, etag: etag1 },
          { partNumber: 2, etag: etag2 },
        ],
      }),
      headers: { "Content-Type": "application/json" },
    });
    expect(completeRes.status).toBe(200);

    // Verify via direct bucket access
    const bucket = await mf.getR2Bucket("UPLOAD_BUCKET");
    const obj = await bucket.get("video.mp4");
    expect(obj).not.toBeNull();
    expect(obj!.size).toBe(FIVE_MB + 1024);
  });
});
```

## 4. Abort Path: Multipart Upload Disappears

```typescript
describe("abort", () => {
  it("aborts in-progress upload; object does not exist", async () => {
    const initRes = await workerFetch("/upload?action=initiate&key=<redacted-secret>
    const { uploadId, key } = await initRes.json<{ uploadId: string; key: string }>();

    // Upload one part so the session is non-trivial
    const body = new Uint8Array(FIVE_MB).fill(0x00);
    await workerFetch(
      `/upload?action=upload-part&key=${key}&uploadId=${uploadId}&partNumber=1`,
      { method: "PUT", body }
    );

    // Abort
    const abortRes = await workerFetch(
      `/upload?action=abort&key=${key}&uploadId=${uploadId}`,
      { method: "DELETE" }
    );
    expect(abortRes.status).toBe(204);

    // Object must not exist
    const bucket = await mf.getR2Bucket("UPLOAD_BUCKET");
    const obj = await bucket.get("draft.bin");
    expect(obj).toBeNull();
  });
});
```

## 5. Error Cases: Undersized Non-Final Part

```typescript
describe("error handling", () => {
  it("completes with wrong ETags returns an error-like response", async () => {
    const initRes = await workerFetch("/upload?action=initiate&key=bad.bin");
    const { uploadId, key } = await initRes.json<{ uploadId: string; key: string }>();

    // Upload a real part
    const part1Body = new Uint8Array(FIVE_MB).fill(0xff);
    const p1Res = await workerFetch(
      `/upload?action=upload-part&key=${key}&uploadId=${uploadId}&partNumber=1`,
      { method: "PUT", body: part1Body }
    );
    await p1Res.json(); // consume

    // Complete with a fabricated ETag — Miniflare enforces ETag matching
    await expect(
      workerFetch(`/upload?action=complete&key=${key}`, {
        method: "POST",
        body: JSON.stringify({
          uploadId,
          parts: [{ partNumber: 1, etag: "deadbeefdeadbeefdeadbeefdeadbeef" }],
        }),
        headers: { "Content-Type": "application/json" },
      })
    ).resolves.toMatchObject({ status: expect.not.stringMatching(/^2/) });
  });
});
```

## 6. Direct Bucket Fixture for Seeding Pre-Existing Objects

```typescript
describe("pre-existing objects", () => {
  it("does not overwrite an existing key with an aborted multipart", async () => {
    const bucket = await mf.getR2Bucket("UPLOAD_BUCKET");
    // Seed an existing object
    await bucket.put("stable.txt", "original content");

    const initRes = await workerFetch("/upload?action=initiate&key=<redacted-secret>
    const { uploadId } = await initRes.json<{ uploadId: string }>();

    // Abort immediately — original content must survive
    await workerFetch(`/upload?action=abort&key=stable.txt&uploadId=${uploadId}`, {
      method: "DELETE",
    });

    const obj = await bucket.get("stable.txt");
    const text = await obj!.text();
    expect(text).toBe("original content");
  });
});
```

## Anti-patterns

- **Mocking `createMultipartUpload` with `vi.fn()`**: This bypasses ETag validation and part-size enforcement, leaving the entire multipart state machine untested.
- **Using a live R2 bucket in CI**: Incurs egress cost, requires secrets, and makes tests non-deterministic when a previous run left orphaned multipart sessions.
- **Testing only the happy path**: Multipart uploads fail in practice at completion due to ETag reordering or network retries that replay a part. Cover abort and ETag-mismatch paths.
- **Not disposing Miniflare in `afterEach`**: Leaked instances accumulate port bindings and shared state across test files.

## Gotchas

- Miniflare's R2 enforces the 5 MB minimum only for non-last parts. If your test uses data smaller than 5 MB for part 1 of a 2-part upload, `completeMultipartUpload` will throw in Miniflare the same as in production.
- `resumeMultipartUpload` does NOT validate that the `uploadId` exists — it just reconstructs the handle. The validation happens at `uploadPart` or `complete` time.
- Miniflare R2 ETags are MD5 hex strings of the part content; they will change if your test fixture data changes. Assert format (`/^[a-f0-9]{32}$/`) rather than literal value.
- When running multiple test files in parallel with `vitest --pool=forks`, each fork needs its own Miniflare instance. Do not share a single Miniflare across files via a module-level singleton.

## Verification

```bash
# Build the worker first
npx wrangler build --dry-run --outdir dist

# Run the test suite
npx vitest run test/multipart.test.ts --reporter=verbose
```

Expected output: all assertions pass, including the ETag-mismatch rejection and the abort-does-not-overwrite cases.

## Related

- `vitest-r2-multipart-upload-testing.md` — same scenarios driven via `@cloudflare/vitest-pool-workers` pool
- `r2-bucket-miniflare-testing.md` — single-object put/get/delete fundamentals
- `miniflare-multi-worker-environment-setup.md` — multi-worker wiring for signed-URL delegation patterns

## Sources

- Miniflare R2 docs: https://miniflare.dev/storage/r2
- R2 multipart spec: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#multipart-upload
- Cloudflare Workers R2 binding reference: https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
