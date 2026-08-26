# Playwright Workers R2 File Upload E2E

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project lets anonymous users upload images and short video clips to posts. The upload pipeline
routes through a Cloudflare Worker that validates MIME type, generates a signed R2 pre-signed
URL, and stores metadata in D1. Manual testing of this flow across browsers was slow and error-prone
because the Worker, R2 bucket, and D1 table all needed to be in the right state together.

## Context

End-to-end tests run against a preview deployment (Workers + R2 + D1 bound to a `preview` environment
via `wrangler.toml` environments). Playwright interacts with the actual Worker over HTTPS; there is
no local R2 emulator in this flow. The R2 bucket is configured with a `test-` prefix lifecycle rule
that deletes objects after 24 hours, keeping the bucket clean between CI runs.

## Worker Upload Route

The Worker exposes `POST /upload/request` which returns a pre-signed URL and an `objectKey`. The
client then `PUT`s directly to R2 using that URL, then calls `POST /upload/confirm` with the key
so the Worker can write the D1 record and emit a Queue message.

```typescript
// src/routes/upload.ts
import { Env } from "../types";

export async function handleUploadRequest(
  request: Request,
  env: Env
): Promise<Response> {
  const { mimeType, byteLength } = await request.json<{
    mimeType: string;
    byteLength: number;
  }>();

  const allowed = ["image/jpeg", "image/png", "image/webp", "video/mp4"];
  if (!allowed.includes(mimeType)) {
    return Response.json({ error: "unsupported_type" }, { status: 415 });
  }
  if (byteLength > 10 * 1024 * 1024) {
    return Response.json({ error: "too_large" }, { status: 413 });
  }

  const objectKey = `test-uploads/${crypto.randomUUID()}`;
  // createPresignedUrl is a helper wrapping R2's presign capability
  const url = await env.MEDIA_BUCKET.createPresignedUrl(objectKey, {
    expiresIn: 300,
    method: "PUT",
  });

  return Response.json({ url, objectKey });
}

export async function handleUploadConfirm(
  request: Request,
  env: Env
): Promise<Response> {
  const { objectKey, caption } = await request.json<{
    objectKey: string;
    caption: string;
  }>();

  await env.DB.prepare(
    "INSERT INTO media (object_key, caption, created_at) VALUES (?, ?, ?)"
  )
    .bind(objectKey, caption, Date.now())
    .run();

  await env.UPLOAD_QUEUE.send({ type: "media_uploaded", objectKey });
  return Response.json({ ok: true });
}
```

## Playwright Fixture for Upload State

A custom Playwright fixture tears down R2 objects written during a test so bucket storage does not
accumulate during repeated local runs.

```typescript
// tests/fixtures/upload.ts
import { test as base, expect } from "@playwright/test";

type UploadFixtures = {
  uploadedKeys: string[];
  cleanupUploads: () => Promise<void>;
};

export const test = base.extend<UploadFixtures>({
  uploadedKeys: [[], { scope: "test" }],

  cleanupUploads: async ({ uploadedKeys, request }, use) => {
    await use(async () => {
      for (const key of uploadedKeys) {
        // Internal Worker admin endpoint only reachable with a shared secret
        await request.delete(`/admin/r2/${encodeURIComponent(key)}`, {
          headers: { "x-admin-secret": process.env.ADMIN_SECRET! },
        });
      }
      uploadedKeys.length = 0;
    });
  },
});

export { expect };
```

## Full Upload Flow E2E Test

```typescript
// tests/e2e/upload-r2.spec.ts
import { test, expect } from "../fixtures/upload";
import * as fs from "node:fs";
import * as path from "node:path";

const BASE_URL = process.env.WORKER_BASE_URL!;

test.describe("R2 media upload flow", () => {
  test.afterEach(async ({ cleanupUploads }) => {
    await cleanupUploads();
  });

  test("uploads a JPEG and confirms the D1 record", async ({
    page,
    request,
    uploadedKeys,
  }) => {
    // 1. Request a pre-signed URL from the Worker
    const requestRes = await request.post(`${BASE_URL}/upload/request`, {
      data: { mimeType: "image/jpeg", byteLength: 4096 },
    });
    expect(requestRes.ok()).toBeTruthy();
    const { url, objectKey } = await requestRes.json();
    uploadedKeys.push(objectKey);

    // 2. PUT a tiny synthetic image directly to R2
    const fakeJpeg = fs.readFileSync(
      path.join(__dirname, "../fixtures/sample.jpg")
    );
    const putRes = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "image/jpeg" },
      body: fakeJpeg,
    });
    expect(putRes.ok).toBe(true);

    // 3. Confirm the upload so the Worker writes the D1 record
    const confirmRes = await request.post(`${BASE_URL}/upload/confirm`, {
      data: { objectKey, caption: "test caption" },
    });
    expect(confirmRes.ok()).toBeTruthy();

    // 4. Navigate to the page that shows the uploaded media
    await page.goto(`${BASE_URL}/media/${encodeURIComponent(objectKey)}`);
    await expect(page.getByRole("img", { name: /uploaded media/i })).toBeVisible();
    await expect(page.getByText("test caption")).toBeVisible();
  });

  test("rejects files over 10 MB", async ({ request }) => {
    const res = await request.post(`${BASE_URL}/upload/request`, {
      data: { mimeType: "image/jpeg", byteLength: 11 * 1024 * 1024 },
    });
    expect(res.status()).toBe(413);
    const body = await res.json();
    expect(body.error).toBe("too_large");
  });

  test("rejects unsupported MIME types", async ({ request }) => {
    const res = await request.post(`${BASE_URL}/upload/request`, {
      data: { mimeType: "application/pdf", byteLength: 1024 },
    });
    expect(res.status()).toBe(415);
  });
});
```

## Playwright Configuration

```typescript
// playwright.config.ts (upload suite fragment)
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  use: {
    baseURL: process.env.WORKER_BASE_URL,
    extraHTTPHeaders: {
      "x-wasm-anon-token": process.env.TEST_ANON_TOKEN ?? "test",
    },
  },
  projects: [
    { name: "chromium", use: { channel: "chrome" } },
    { name: "firefox" },
    { name: "webkit" },
  ],
});
```

## Anti-patterns

- Using a shared R2 bucket without a prefix or lifecycle rule — objects accumulate and costs grow.
- Asserting on S3-style presigned URL structure instead of the response status code; the URL format is internal to Cloudflare.
- Calling `wrangler r2 object delete` in test teardown — too slow and requires wrangler installed in CI.
- Mocking `fetch` to intercept the R2 PUT — this skips the actual pre-signed URL validation logic.
- Omitting `Content-Type` on the PUT request — R2 stores it as `application/octet-stream`, breaking MIME checks on read.

## Gotchas

- Pre-signed URLs expire (300 s in the example); slow CI runners can fail the PUT step if the pipeline pauses.
- The R2 `createPresignedUrl` method is only available in the Workers runtime, not in Miniflare 3 by default; add `r2Persist` config or use a preview environment.
- `request.delete` in Playwright sends an HTTP DELETE, not a filesystem delete — ensure the admin endpoint is wired correctly.
- Chromium sandboxes may block large `File` objects constructed in-page; use `request` (API layer) for the PUT step.
- D1 writes from the confirm step are eventually consistent relative to the page render; add a `waitFor` poll if the media page queries D1 directly.

## Verification

```bash
# Run against the preview Worker deployment
WORKER_BASE_URL=https://preview.example.com \
ADMIN_SECRET=dev-secret \
TEST_ANON_TOKEN=anon-test \
npx playwright test tests/e2e/upload-r2.spec.ts --reporter=list
```

CI: add the `upload-r2` spec to the `e2e` GitHub Actions job that runs on preview deployments triggered by PRs targeting `main`.

## Related

- documentation/docs/policies/testing/vitest-r2-multipart-upload-testing.md
- documentation/docs/policies/testing/r2-bucket-miniflare-testing.md
- documentation/docs/policies/testing/playwright-d1-state-reset-between-tests.md
- documentation/docs/policies/testing/workers-queues-retry-dlq-testing.md

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/#create-presigned-urls
- https://playwright.dev/docs/api/class-apirequestcontext
- https://developers.cloudflare.com/workers/wrangler/environments/
