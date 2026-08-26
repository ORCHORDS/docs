# Vitest Workers Turnstile Bypass Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workers endpoint calls the Turnstile siteverify API to validate a CAPTCHA token
before processing a form submission or login attempt. Vitest unit and integration tests
fail or become non-deterministic because they hit the real Turnstile endpoint, which
requires a valid browser-generated token and rejects test tokens unless you configure
specific test keys. You need a reliable, offline way to exercise the Worker logic that
surrounds Turnstile verification without making live network calls.

## Context

Cloudflare Turnstile provides a pair of testing credentials — a "always passes" site
key (`1x00000000000000000000AA`) and a "always fails" site key
(`2x00000000000000000000AB`) — but these still make outbound HTTPS calls to
`https://challenges.cloudflare.com/turnstile/v0/siteverify`. In a Vitest Workers pool
environment, outbound fetch may be disabled or unreliable. The right approach is to
intercept `fetch` at the Worker boundary so the Turnstile call never leaves the runtime.

---

## Strategy 1 — Dependency-Inject the Verify Function

Structure your Worker so the Turnstile verification is a plain async function that can
be swapped in tests.

```typescript
// src/turnstile.ts
export interface TurnstileResult {
  success: boolean;
  "error-codes"?: string[];
}

export type TurnstileVerifier = (
  token: string,
  ip: string,
  secretKey: string
) => Promise<TurnstileResult>;

export const defaultVerifier: TurnstileVerifier = async (token, ip, secretKey) => {
  const body = new URLSearchParams({
    secret: secretKey,
    response: token,
    remoteip: ip,
  });
  const res = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    body,
  });
  return res.json<TurnstileResult>();
};
```

```typescript
// src/handler.ts
import { defaultVerifier, TurnstileVerifier } from "./turnstile";

export function createHandler(verify: TurnstileVerifier = defaultVerifier) {
  return async (request: Request, env: Env): Promise<Response> => {
    const { token } = await request.json<{ token: string }>();
    const ip = request.headers.get("CF-Connecting-IP") ?? "127.0.0.1";

    const result = await verify(token, ip, env.TURNSTILE_SECRET_KEY);
    if (!result.success) {
      return Response.json({ error: "captcha_failed" }, { status: 403 });
    }
    return Response.json({ ok: true });
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return createHandler()(request, env);
  },
};
```

---

## Strategy 2 — Mock globalThis.fetch Inside the Worker Pool

When you cannot refactor production code, intercept `fetch` globally inside the test.

```typescript
// test/turnstile-global-mock.test.ts
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

function mockTurnstile(success: boolean, errorCodes: string[] = []) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url === TURNSTILE_URL) {
      return new Response(JSON.stringify({ success, "error-codes": errorCodes }), {
        headers: { "content-type": "application/json" },
      });
    }
    // Pass through all other fetch calls.
    return fetch(input, init);
  });
}

describe("Turnstile verification endpoint", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns 200 when Turnstile reports success", async () => {
    mockTurnstile(true);
    const res = await SELF.fetch("https://example.com/submit", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token: "test-token" }),
    });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
  });

  it("returns 403 when Turnstile reports failure", async () => {
    mockTurnstile(false, ["invalid-input-response"]);
    const res = await SELF.fetch("https://example.com/submit", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token: "bad-token" }),
    });
    expect(res.status).toBe(403);
    const body = await res.json<{ error: string }>();
    expect(body.error).toBe("captcha_failed");
  });
});
```

---

## Strategy 3 — Unit Test with Injected Verifier

```typescript
// test/turnstile-unit.test.ts
import { describe, it, expect } from "vitest";
import { createHandler } from "../src/handler";
import type { TurnstileVerifier } from "../src/turnstile";

function makeRequest(token: string): Request {
  return new Request("https://example.com/submit", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token }),
  });
}

const mockEnv = { TURNSTILE_SECRET_KEY: "test-secret" } as Env;

describe("createHandler with injected verifier", () => {
  it("passes the token and IP through to the verifier", async () => {
    let capturedToken = "";
    let capturedIp = "";

    const verifier: TurnstileVerifier = async (token, ip) => {
      capturedToken = token;
      capturedIp = ip;
      return { success: true };
    };

    const request = new Request("https://example.com/submit", {
      method: "POST",
      headers: { "content-type": "application/json", "CF-Connecting-IP": "1.2.3.4" },
      body: JSON.stringify({ token: "abc123" }),
    });

    await createHandler(verifier)(request, mockEnv);
    expect(capturedToken).toBe("abc123");
    expect(capturedIp).toBe("1.2.3.4");
  });

  it("short-circuits and returns 403 without reaching business logic", async () => {
    const failingVerifier: TurnstileVerifier = async () => ({
      success: false,
      "error-codes": ["timeout-or-duplicate"],
    });

    const res = await createHandler(failingVerifier)(makeRequest("stale-token"), mockEnv);
    expect(res.status).toBe(403);
  });

  it("propagates verifier errors as 500", async () => {
    const throwingVerifier: TurnstileVerifier = async () => {
      throw new Error("network unreachable");
    };
    await expect(
      createHandler(throwingVerifier)(makeRequest("any"), mockEnv)
    ).rejects.toThrow("network unreachable");
  });
});
```

---

## Configuring the Test Environment Secret

```toml
# wrangler.toml (for local dev only; never commit real secrets)
[vars]
TURNSTILE_SECRET_KEY = "1x0000000000000000000000000000000AA"  # Cloudflare always-pass test secret
```

In CI, set `TURNSTILE_SECRET_KEY` via a repository secret injected as an env var. The
mock strategies above do not require this value to be a real secret, but the Worker
code needs it to be present to avoid `undefined` errors.

---

## Anti-patterns

- Using the real Turnstile siteverify endpoint in unit tests. Network failures in CI
  cause false negatives with no indication that Turnstile was the root cause.
- Using `vi.mock("../src/turnstile")` without resetting mocks in `afterEach`. Leaked
  mock state breaks parallel test files in the Workers pool.
- Asserting only the HTTP status code. Also assert the response body shape; a 403 from
  a JSON parse error looks identical to a 403 from Turnstile rejection.
- Skipping the "always fails" path. That branch is where security bugs hide.

## Gotchas

- `vi.spyOn(globalThis, "fetch")` works inside `@cloudflare/vitest-pool-workers` only
  when `fetchMock` is not already overriding the global. Check your pool config.
- The Turnstile test secret `1x00000000000000000000AA` still requires outbound network
  access to validate. For fully offline tests, the mock strategies above are correct.
- `CF-Connecting-IP` is not set on requests made via `SELF.fetch()` inside Vitest.
  Your Worker must handle the `null` case gracefully (fall back to `"127.0.0.1"`).
- Do not pass `remoteip` as an empty string to siteverify; Cloudflare may reject the
  request. Always coerce `null` to a valid IP string before calling the API.

## Verification

```bash
npx vitest run test/turnstile-unit.test.ts test/turnstile-global-mock.test.ts
```

All tests should pass with no outbound network requests. Confirm by adding a
`console.log` inside the spy to verify it is called for Turnstile-path tests and
NOT called for non-Turnstile tests.

## Related

- `turnstile-test-keys-automation.md` — using Cloudflare's official test site keys with Playwright
- `playwright-workers-turnstile-captcha-e2e.md` — end-to-end Turnstile bypass in browser tests
- `vitest-workers-env-var-override-testing.md` — injecting test env vars into Workers pool

## Sources

- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://developers.cloudflare.com/turnstile/reference/testing/
- https://vitest.dev/api/vi.html#vi-spyon
- https://developers.cloudflare.com/workers/testing/vitest-integration/
