# Playwright Workers Turnstile Captcha E2E

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project protects its anonymous post-creation form with Cloudflare Turnstile to prevent automated
spam. During Playwright E2E tests the Turnstile widget blocks test automation because the challenge
is designed to detect bots. The team needed a reliable way to exercise the full Worker validation
path — including the server-side `siteverify` call — without flaky CAPTCHA challenges interfering.

## Context

Cloudflare Turnstile provides two special site keys for automated testing: one that always passes
(`1x00000000000000000000AA`) and one that always fails (`2x00000000000000000000AB`). The Worker
calls `https://challenges.cloudflare.com/turnstile/v0/siteverify` with the submitted token. In CI
the Worker environment variable `TURNSTILE_SECRET_KEY` is set to the matching test secret so
`siteverify` returns a valid response for the test site key token.

## Worker Turnstile Verification Middleware

```typescript
// src/middleware/turnstile.ts
import { Env } from "../types";

export interface TurnstileResult {
  success: boolean;
  "error-codes"?: string[];
}

export async function verifyTurnstile(
  token: string,
  env: Env,
  ip: string
): Promise<TurnstileResult> {
  const body = new FormData();
  body.append("secret", env.TURNSTILE_SECRET_KEY);
  body.append("response", token);
  body.append("remoteip", ip);

  const res = await fetch(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    { method: "POST", body }
  );

  return res.json<TurnstileResult>();
}

export async function turnstileMiddleware(
  request: Request,
  env: Env
): Promise<Response | null> {
  const body = await request.clone().json<{ cfTurnstileToken?: string }>();
  const token = body.cfTurnstileToken;

  if (!token) {
    return Response.json({ error: "missing_token" }, { status: 400 });
  }

  const ip = request.headers.get("CF-Connecting-IP") ?? "127.0.0.1";
  const result = await verifyTurnstile(token, env, ip);

  if (!result.success) {
    return Response.json(
      { error: "captcha_failed", codes: result["error-codes"] },
      { status: 403 }
    );
  }

  return null; // proceed
}
```

## Playwright Fixture with Test Site Key Injection

```typescript
// tests/fixtures/turnstile.ts
import { test as base, expect } from "@playwright/test";

/**
 * Injects the Turnstile "always passes" test site key into the page
 * before the widget renders, so Playwright can submit the form without
 * a real challenge.
 */
export const test = base.extend({
  page: async ({ page }, use) => {
    // Intercept the Turnstile script and replace the render call's sitekey
    await page.route("**/turnstile/v0/api.js", async (route) => {
      const response = await route.fetch();
      let body = await response.text();
      // Stub window.turnstile.render so it immediately invokes the callback
      // with the always-passes test token
      body = `
        window.turnstile = {
          render(el, params) {
            setTimeout(() => {
              const cb = params.callback;
              if (cb) cb("XXXX.DUMMY.TOKEN.ALWAYS.PASSES");
            }, 50);
            return "test-widget-id";
          },
          remove() {},
          reset() {},
          getResponse() { return "XXXX.DUMMY.TOKEN.ALWAYS.PASSES"; }
        };
      `;
      await route.fulfill({ body, contentType: "text/javascript" });
    });
    await use(page);
  },
});

export { expect };
```

## E2E Test: Post Creation Protected by Turnstile

```typescript
// tests/e2e/turnstile-post.spec.ts
import { test, expect } from "../fixtures/turnstile";

const BASE_URL = process.env.WORKER_BASE_URL!;

test.describe("Turnstile-protected post creation", () => {
  test("creates a post when CAPTCHA passes", async ({ page }) => {
    await page.goto(`${BASE_URL}/new-post`);

    await page.getByLabel("Post content").fill("Hello anonymous world!");

    // Turnstile widget renders and the fixture's stub fires the callback
    // automatically — no manual interaction needed
    await expect(
      page.locator('[name="cfTurnstileToken"]')
    ).not.toHaveValue("");

    await page.getByRole("button", { name: /submit/i }).click();

    await expect(page.getByText("Post created")).toBeVisible();
  });

  test("Worker rejects requests with no token", async ({ request }) => {
    const res = await request.post(`${BASE_URL}/api/posts`, {
      data: { content: "spam without captcha" },
    });
    expect(res.status()).toBe(400);
    const body = await res.json();
    expect(body.error).toBe("missing_token");
  });

  test("Worker rejects requests with a failing test token", async ({
    request,
  }) => {
    // Uses the always-fails test token directly against the API
    const res = await request.post(`${BASE_URL}/api/posts`, {
      data: {
        content: "spam with bad captcha",
        cfTurnstileToken: "3x00000000000000000000FF", // always-fails secret triggers failure
      },
    });
    expect(res.status()).toBe(403);
    const body = await res.json();
    expect(body.error).toBe("captcha_failed");
  });
});
```

## Wrangler Environment Variables for CI

```toml
# wrangler.toml
[env.preview.vars]
TURNSTILE_SITE_KEY = "1x00000000000000000000AA"   # always-passes test key

# TURNSTILE_SECRET_KEY is set as a secret:
# wrangler secret put TURNSTILE_SECRET_KEY --env preview
# value: 1x0000000000000000000000000000000AA  (test secret matching the test site key)
```

```typescript
// vitest unit test for the middleware in isolation
// tests/unit/turnstile.test.ts
import { describe, it, expect, vi } from "vitest";
import { verifyTurnstile } from "../../src/middleware/turnstile";

describe("verifyTurnstile", () => {
  it("returns success:true for the always-passes test token", async () => {
    const mockEnv = {
      TURNSTILE_SECRET_KEY: "1x0000000000000000000000000000000AA",
    } as any;

    // Stub global fetch to return Cloudflare's test siteverify response
    vi.stubGlobal("fetch", async () =>
      Response.json({ success: true, "error-codes": [] })
    );

    const result = await verifyTurnstile(
      "XXXX.DUMMY.TOKEN.ALWAYS.PASSES",
      mockEnv,
      "1.2.3.4"
    );
    expect(result.success).toBe(true);
    vi.unstubAllGlobals();
  });
});
```

## Anti-patterns

- Using `page.evaluate` to set `window.turnstile` after the script loads — the widget may have already initialized, leaving the form's hidden input empty.
- Disabling Turnstile verification entirely in the Worker for `NODE_ENV=test` — this creates a production code path that is never exercised.
- Hardcoding the always-passes token string in Worker source code — use environment variables so the test and production secrets are separated.
- Routing all Turnstile API calls to a local mock server — the Worker still needs to reach `challenges.cloudflare.com` in preview; mock only in unit tests.

## Gotchas

- The Turnstile test site key `1x00000000000000000000AA` must be used in the frontend; the matching secret is `1x0000000000000000000000000000000AA`. Mismatched pairs cause `siteverify` to fail even for test tokens.
- `page.route` intercepts only requests made from the browser context; the Worker's server-side `siteverify` fetch is not intercepted — it goes to `challenges.cloudflare.com` for real, which is why the test secret key is needed.
- If the Turnstile script is loaded via a Cloudflare Pages `<script>` tag with `integrity`, the stub response will fail the SRI check. Remove `integrity` in non-production environments.
- The hidden `cfTurnstileToken` input is populated asynchronously; use `expect(locator).not.toHaveValue("")` with a timeout rather than checking immediately after page load.

## Verification

```bash
WORKER_BASE_URL=https://preview.example.com \
npx playwright test tests/e2e/turnstile-post.spec.ts --headed
```

For CI without a headed browser, add `--reporter=github` and ensure the `TURNSTILE_SECRET_KEY`
secret is set in the preview Worker environment via `wrangler secret put`.

## Related

- documentation/docs/policies/testing/turnstile-test-keys-automation.md
- documentation/docs/policies/testing/playwright-workers-feature-flag-ab-test.md
- documentation/docs/policies/testing/playwright-cloudflare-pages-e2e.md
- documentation/docs/policies/testing/auth-flow-testing-strategy.md

## Sources

- https://developers.cloudflare.com/turnstile/reference/testing/
- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://playwright.dev/docs/network#modify-responses
- https://developers.cloudflare.com/workers/configuration/secrets/
