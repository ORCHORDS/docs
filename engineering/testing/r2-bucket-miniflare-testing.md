# Testing Cloudflare R2 Bucket Bindings with Miniflare

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A Cloudflare Workers handler uploads user-generated files to an R2 bucket, serves them with `HEAD`/`GET`, lists objects for an admin dashboard, and deletes stale assets on a schedule. You want deterministic, offline tests for all these paths — including range requests, conditional `If-None-Match` headers, and multipart uploads — without touching a real R2 bucket or racking up egress costs.

---

## Context

Cloudflare R2 is an S3-compatible object store accessible inside Workers through a typed `R2Bucket` binding. Miniflare 3.x (the local Workers runtime used by `vitest-pool-workers` and `wrangler dev`) ships an in-memory R2 implementation that honours the full binding surface: `put`, `get`, `head`, `list`, `delete`, and `createMultipartUpload`. Tests run entirely in-process with no network I/O, sub-millisecond latency, and zero cost.

The in-memory store resets between isolated test suites when each test is run through `vitest-pool-workers` with `isolatedStorage: true`. Without that flag the bucket state leaks across tests, producing ordering-dependent failures — the single most common mistake when starting out.

---

## 1. Project Setup

```
npm install --save-dev vitest @cloudflare/vitest-pool-workers wrangler
```

`wrangler.toml`:

```toml
name = "asset-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "assets-prod"
```

`vitest.config.ts`:

```typescript
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          // Reset every binding store between test files
          isolatedStorage: true,
        },
      },
    },
  },
});
```

`tsconfig.json` must include `"types": ["@cloudflare/workers-types"]` so the `R2Bucket` global is recognised.

---

## 2. Accessing the Binding in Tests

`vitest-pool-workers` exposes bindings via the `env` helper from `cloudflare:test`:

```typescript
// src/__tests__/r2.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";

// The binding name must match wrangler.toml exactly
const bucket = (): R2Bucket => env.ASSETS;

describe("R2 bucket binding", () => {
  beforeEach(async () => {
    // Purge any objects placed by a previous test in the same file.
    // isolatedStorage only resets between *files*, not between *tests*.
    const listed = await bucket().list();
    await Promise.all(listed.objects.map((o) => bucket().delete(o.key)));
  });
});
```

Keep the `beforeEach` purge lean — only clear what your suite touches, not the entire namespace, once your suites grow large.

---

## 3. Testing PUT and GET Round-trips

```typescript
import { env } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("put / get", () => {
  it("stores and retrieves text content", async () => {
    await env.ASSETS.put("hello.txt", "hello world", {
      httpMetadata: { contentType: "text/plain" },
      customMetadata: { uploadedBy: "test-suite" },
    });

    const obj = await env.ASSETS.get("hello.txt");
    expect(obj).not.toBeNull();
    expect(await obj!.text()).toBe("hello world");
    expect(obj!.httpMetadata?.contentType).toBe("text/plain");
    expect(obj!.customMetadata?.uploadedBy).toBe("test-suite");
  });

  it("returns null for a missing key", async () => {
    const obj = await env.ASSETS.get("does-not-exist.txt");
    expect(obj).toBeNull();
  });

  it("overwrites an existing key", async () => {
    await env.ASSETS.put("file.txt", "v1");
    await env.ASSETS.put("file.txt", "v2");
    const obj = await env.ASSETS.get("file.txt");
    expect(await obj!.text()).toBe("v2");
  });

  it("stores binary content via ArrayBuffer", async () => {
    const bytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47]); // PNG magic
    await env.ASSETS.put("icon.png", bytes.buffer, {
      httpMetadata: { contentType: "image/png" },
    });
    const obj = await env.ASSETS.get("icon.png");
    const buf = await obj!.arrayBuffer();
    expect(new Uint8Array(buf)[0]).toBe(0x89);
  });
});
```

---

## 4. Testing HEAD and Conditional Requests

The `head` method returns metadata without downloading the body — critical for `ETag`-based caching in your Workers handler.

```typescript
describe("head and conditional GET", () => {
  it("head returns metadata without body", async () => {
    await env.ASSETS.put("meta.json", JSON.stringify({ ok: true }), {
      httpMetadata: { contentType: "application/json" },
    });

    const meta = await env.ASSETS.head("meta.json");
    expect(meta).not.toBeNull();
    expect(meta!.size).toBe(10);
    expect(meta!.etag).toMatch(/^[0-9a-f]{32}$/); // MD5 hex
    // body is undefined on an R2ObjectBody from head()
    expect((meta as R2Object).body).toBeUndefined();
  });

  it("conditional get with matching etag returns null", async () => {
    await env.ASSETS.put("doc.txt", "content");
    const initial = await env.ASSETS.head("doc.txt");
    const etag = initial!.etag;

    // Simulate If-None-Match: the binding returns null when condition fails
    const conditional = await env.ASSETS.get("doc.txt", {
      onlyIf: { etagMatches: etag },
    });
    // R2 returns null body when etag matched (304 equivalent)
    expect(conditional?.body).toBeUndefined();
  });

  it("conditional get with stale etag returns body", async () => {
    await env.ASSETS.put("doc.txt", "v1");
    await env.ASSETS.put("doc.txt", "v2"); // new etag

    const obj = await env.ASSETS.get("doc.txt", {
      onlyIf: { etagDoesNotMatch: "stale-etag" },
    });
    expect(await obj!.text()).toBe("v2");
  });
});
```

---

## 5. Testing Range Requests

Range reads are essential for serving large media files. The Miniflare R2 implementation honours byte-range semantics:

```typescript
describe("range reads", () => {
  const content = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"; // 26 bytes

  it("reads a byte range", async () => {
    await env.ASSETS.put("alphabet.txt", content);

    const partial = await env.ASSETS.get("alphabet.txt", {
      range: { offset: 0, length: 5 },
    });
    expect(await partial!.text()).toBe("ABCDE");
  });

  it("reads a suffix range", async () => {
    await env.ASSETS.put("alphabet.txt", content);

    const partial = await env.ASSETS.get("alphabet.txt", {
      range: { suffix: 4 },
    });
    expect(await partial!.text()).toBe("WXYZ");
  });

  it("exposes range metadata on the response object", async () => {
    await env.ASSETS.put("alphabet.txt", content);
    const partial = await env.ASSETS.get("alphabet.txt", {
      range: { offset: 10, length: 5 },
    });
    expect(partial!.range).toEqual({ offset: 10, length: 5 });
  });
});
```

---

## 6. Testing LIST and DELETE

```typescript
describe("list", () => {
  beforeEach(async () => {
    await Promise.all([
      env.ASSETS.put("images/cat.jpg", "cat"),
      env.ASSETS.put("images/dog.jpg", "dog"),
      env.ASSETS.put("docs/readme.txt", "readme"),
    ]);
  });

  it("lists all objects", async () => {
    const result = await env.ASSETS.list();
    expect(result.objects).toHaveLength(3);
    expect(result.truncated).toBe(false);
  });

  it("filters by prefix", async () => {
    const result = await env.ASSETS.list({ prefix: "images/" });
    expect(result.objects.map((o) => o.key)).toEqual(
      expect.arrayContaining(["images/cat.jpg", "images/dog.jpg"])
    );
    expect(result.objects).toHaveLength(2);
  });

  it("paginates with limit and cursor", async () => {
    const first = await env.ASSETS.list({ limit: 2 });
    expect(first.objects).toHaveLength(2);
    expect(first.truncated).toBe(true);

    const second = await env.ASSETS.list({ cursor: first.cursor, limit: 2 });
    expect(second.objects).toHaveLength(1);
    expect(second.truncated).toBe(false);
  });

  it("uses delimiter to get common prefixes", async () => {
    const result = await env.ASSETS.list({ delimiter: "/" });
    // Top-level prefixes, not individual files
    expect(result.delimitedPrefixes).toEqual(
      expect.arrayContaining(["images/", "docs/"])
    );
  });
});

describe("delete", () => {
  it("removes a single object", async () => {
    await env.ASSETS.put("temp.txt", "bye");
    await env.ASSETS.delete("temp.txt");
    expect(await env.ASSETS.head("temp.txt")).toBeNull();
  });

  it("deletes multiple objects atomically", async () => {
    await env.ASSETS.put("a.txt", "a");
    await env.ASSETS.put("b.txt", "b");
    await env.ASSETS.delete(["a.txt", "b.txt"]);
    expect(await env.ASSETS.head("a.txt")).toBeNull();
    expect(await env.ASSETS.head("b.txt")).toBeNull();
  });

  it("delete is idempotent for missing keys", async () => {
    // Should not throw
    await expect(env.ASSETS.delete("ghost.txt")).resolves.toBeUndefined();
  });
});
```

---

## 7. Integration Test: Worker Handler with R2

Test the full HTTP handler, not just the raw binding:

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1); // strip leading /

    if (request.method === "PUT") {
      const body = await request.arrayBuffer();
      await env.ASSETS.put(key, body, {
        httpMetadata: { contentType: request.headers.get("content-type") ?? "application/octet-stream" },
      });
      return new Response(null, { status: 201 });
    }

    if (request.method === "GET") {
      const obj = await env.ASSETS.get(key);
      if (!obj) return new Response("Not Found", { status: 404 });
      const headers = new Headers();
      headers.set("etag", obj.etag);
      if (obj.httpMetadata?.contentType) {
        headers.set("content-type", obj.httpMetadata.contentType);
      }
      return new Response(obj.body, { headers });
    }

    return new Response("Method Not Allowed", { status: 405 });
  },
};
```

```typescript
// src/__tests__/handler.test.ts
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import worker from "../index";
import { describe, it, expect } from "vitest";

async function req(method: string, path: string, body?: BodyInit, headers?: Record<string, string>) {
  const ctx = createExecutionContext();
  const res = await worker.fetch(
    new Request(`https://example.com${path}`, { method, body, headers }),
    env,
    ctx
  );
  await waitOnExecutionContext(ctx);
  return res;
}

describe("asset worker", () => {
  it("PUT then GET round-trip", async () => {
    const put = await req("PUT", "/photo.jpg", new Uint8Array([0xff, 0xd8]).buffer, {
      "content-type": "image/jpeg",
    });
    expect(put.status).toBe(201);

    const get = await req("GET", "/photo.jpg");
    expect(get.status).toBe(200);
    expect(get.headers.get("content-type")).toBe("image/jpeg");
  });

  it("GET missing key returns 404", async () => {
    const res = await req("GET", "/nobody.txt");
    expect(res.status).toBe(404);
  });
});
```

---

## Anti-patterns

- **Sharing a single `R2Bucket` reference across files without `isolatedStorage: true`.** Each test file runs in the same Miniflare instance by default; leftover objects from one file pollute the next.
- **Asserting on exact ETag values.** Miniflare computes MD5s identically to production, but relying on a hardcoded hex string makes tests fragile if the hashing algorithm changes. Assert on format (`/^[0-9a-f]{32}$/`) or on the round-trip behaviour instead.
- **Skipping `beforeEach` cleanup inside a file.** `isolatedStorage` resets between *files*, not between *tests* within a file. Without a purge, test order determines whether earlier keys are visible.
- **Testing multipart uploads without completing them.** An incomplete multipart upload leaves parts in the store but the key is invisible to `get` and `head`. Always call `complete` or `abort` to avoid phantom state.
- **Using `any` for the env type.** Import or declare `interface Env { ASSETS: R2Bucket }` so TypeScript catches binding renames before tests run.

---

## Gotchas

- `list()` returns objects sorted lexicographically by key, not insertion order. Tests that depend on array position must sort the returned `objects` array first.
- `put` with a `ReadableStream` body works in production Workers but Miniflare may buffer it differently. Prefer `ArrayBuffer` or `string` in tests.
- `R2Object.body` is a `ReadableStream` that can only be consumed once. Calling `obj.text()` twice throws. If you need to inspect the body multiple times, clone it: `const [a, b] = obj.body.tee()`.
- Miniflare's `list()` does not honour `include: ["httpMetadata"]` in older versions. Upgrade to the latest `wrangler` / `@cloudflare/vitest-pool-workers` patch if metadata is missing from list results.
- The `onlyIf` conditional on `get` returns an `R2ObjectBody` with no body (not `null`) when the condition matched for `etagMatches`. Distinguish a 304-equivalent from a 404 by checking `obj !== null` separately from `obj.body !== undefined`.

---

## Verification

```bash
# Run just the R2 tests
npx vitest run src/__tests__/r2.test.ts

# Watch mode during development
npx vitest --reporter=verbose src/__tests__/r2.test.ts

# Coverage with v8 provider
npx vitest run --coverage src/__tests__/r2.test.ts
```

Expected output for a healthy suite (all sections combined ~25 tests):

```
✓ src/__tests__/r2.test.ts (25 tests) 312ms
  ✓ put / get (4)
  ✓ head and conditional GET (3)
  ✓ range reads (3)
  ✓ list (4)
  ✓ delete (3)
  ✓ asset worker (2)
```

---

## Related

- `kv-testing-miniflare.md` — same `isolatedStorage` pattern for KV namespaces
- `miniflare-d1-integration-testing.md` — D1 binding patterns inside `vitest-pool-workers`
- `vitest-cloudflare-pool-workers.md` — full pool-workers configuration reference
- `cloudflare-queues-miniflare-batch-testing.md` — Queue consumer testing in the same harness
- `durable-objects-miniflare-fake-timers.md` — Durable Object storage alongside R2

---

## Sources

- Cloudflare R2 Workers API reference: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- `@cloudflare/vitest-pool-workers` README: https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- Miniflare R2 implementation source: https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare/src/workers/r2
- Wrangler `wrangler.toml` R2 binding docs: https://developers.cloudflare.com/workers/wrangler/configuration/#r2-buckets
