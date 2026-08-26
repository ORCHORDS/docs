# Miniflare Email Routing Testing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You use Cloudflare Email Routing to forward, filter, or transform inbound email in a
Worker via the `email` handler. Validating address-based routing rules, header rewriting,
and `reject()` / `forward()` logic without sending real email is painful when tests only
run in wrangler dev.

## Context

Workers with `email` handlers receive a `ForwardableEmailMessage` object exposing `from`,
`to`, `headers`, `raw` (a `ReadableStream`), `forward()`, `reject()`, and `setReject()`.
Miniflare 3 does not synthesise email events natively, but the handler is a plain async
function, so tests can construct a mock `ForwardableEmailMessage` and call the export
directly inside `@cloudflare/vitest-pool-workers`.

## Setting Up the Worker

```ts
// src/index.ts
export default {
  async email(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext) {
    if (message.to === "noreply@example.com") {
      message.setReject("This address does not accept mail");
      return;
    }
    if (message.from.endsWith("@spam-domain.example")) {
      message.setReject("Rejected: known spam domain");
      return;
    }
    await message.forward(env.FORWARD_TO);
  },
};
```

## Building a Mock ForwardableEmailMessage

```ts
// test/helpers/mock-email-message.ts
export interface MockEmailOptions {
  from?: string;
  to?: string;
  rawBody?: string;
  headers?: Record<string, string>;
}

export function mockEmailMessage(opts: MockEmailOptions = {}) {
  const { from = "sender@example.com", to = "hello@example.com", rawBody = "" } = opts;

  const forwardedTo: string[] = [];
  let rejection: string | undefined;

  const message = {
    from,
    to,
    headers: new Headers(opts.headers ?? {}),
    raw: new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(rawBody));
        controller.close();
      },
    }),
    rawSize: rawBody.length,
    forward: vi.fn(async (address: string) => {
      forwardedTo.push(address);
    }),
    reject: vi.fn(),
    setReject: vi.fn((reason: string) => {
      rejection = reason;
    }),
  };

  return { message, forwardedTo, getRejection: () => rejection };
}
```

## Testing Forward Path

```ts
// test/email-routing.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/index";
import { mockEmailMessage } from "./helpers/mock-email-message";

const env = { FORWARD_TO: "team@internal.example.com" } as Env;

describe("email() routing", () => {
  it("forwards legitimate mail to the team inbox", async () => {
    const { message, forwardedTo } = mockEmailMessage({
      from: "customer@example.com",
      to: "support@example.com",
    });

    await worker.email(message as any, env, {} as ExecutionContext);

    expect(message.forward).toHaveBeenCalledWith(env.FORWARD_TO);
    expect(forwardedTo).toContain(env.FORWARD_TO);
  });
});
```

## Testing Rejection Rules

```ts
// test/email-rejection.test.ts
import { describe, it, expect, vi } from "vitest";
import worker from "../src/index";
import { mockEmailMessage } from "./helpers/mock-email-message";

const env = { FORWARD_TO: "team@internal.example.com" } as Env;

describe("email() rejection", () => {
  it("rejects mail to noreply", async () => {
    const { message, getRejection } = mockEmailMessage({ to: "noreply@example.com" });

    await worker.email(message as any, env, {} as ExecutionContext);

    expect(message.forward).not.toHaveBeenCalled();
    expect(getRejection()).toMatch(/does not accept mail/i);
  });

  it("rejects mail from known spam domains", async () => {
    const { message, getRejection } = mockEmailMessage({
      from: "promo@spam-domain.example",
    });

    await worker.email(message as any, env, {} as ExecutionContext);

    expect(getRejection()).toMatch(/spam domain/i);
  });
});
```

## Testing Raw Body Parsing

```ts
// test/email-body.test.ts
import { describe, it, expect } from "vitest";
import { mockEmailMessage } from "./helpers/mock-email-message";

async function readStream(stream: ReadableStream<Uint8Array>): Promise<string> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  return new TextDecoder().decode(
    chunks.reduce((a, b) => {
      const merged = new Uint8Array(a.length + b.length);
      merged.set(a);
      merged.set(b, a.length);
      return merged;
    }, new Uint8Array())
  );
}

describe("email raw body", () => {
  it("exposes the raw RFC-5322 message bytes", async () => {
    const raw = "From: sender@example.com\r\nSubject: Hello\r\n\r\nBody text";
    const { message } = mockEmailMessage({ rawBody: raw });

    const text = await readStream(message.raw);
    expect(text).toContain("Subject: Hello");
  });
});
```

## Testing Header Rewriting Worker

```ts
// test/email-header-rewrite.test.ts
import { describe, it, expect, vi } from "vitest";
import { mockEmailMessage } from "./helpers/mock-email-message";

// Simulated header-enrichment worker
async function emailWithHeaderEnrich(
  message: any,
  env: any,
  _ctx: any
): Promise<void> {
  const xSource = message.headers.get("X-Source") ?? "unknown";
  await message.forward(env.FORWARD_TO, new Headers({ "X-Forwarded-Source": xSource }));
}

describe("email() header enrichment", () => {
  it("passes X-Forwarded-Source header to forward()", async () => {
    const { message } = mockEmailMessage({
      headers: { "X-Source": "newsletter" },
    });

    await emailWithHeaderEnrich(message, { FORWARD_TO: "inbox@example.com" }, {});

    const [, headers] = message.forward.mock.calls[0];
    expect((headers as Headers).get("X-Forwarded-Source")).toBe("newsletter");
  });
});
```

## Anti-patterns

- **Using `wrangler dev` manual sends for CI**: Sending real SMTP in CI is fragile and
  slow. Mock the `ForwardableEmailMessage` object instead.
- **Asserting on `reject()` instead of `setReject()`**: The Workers runtime uses
  `setReject()` to defer rejection; `reject()` exists for backwards compatibility.
  Test both if your worker uses both.
- **Forgetting env bindings**: The email handler receives `env` just like `fetch`. Tests
  that omit it will throw on first binding access.

## Gotchas

- `message.raw` is a **one-time readable** stream. If your worker reads it for virus
  scanning before forwarding, drain the stream in test helpers before asserting.
- `forward()` in production queues a real SMTP send; the mock must replace it entirely —
  do not let the real binding leak into unit tests.
- Email routing rules in the Cloudflare dashboard are **independent** of the Worker; the
  Worker only runs if a dashboard rule directs traffic to it. Test routing rule logic
  separately if it lives in Terraform / API config.

## Verification

```bash
npx vitest run test/email-routing.test.ts test/email-rejection.test.ts \
  test/email-body.test.ts test/email-header-rewrite.test.ts
```

Confirm no real network calls are made by running with `--reporter=verbose` and
inspecting that `fetch` is never invoked.

## Related

- `workers-tail-event-testing.md`
- `workers-test-patterns.md`
- `mock-service-worker-msw-api-mocking.md`

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/email-bindings/
- https://developers.cloudflare.com/email-routing/email-workers/reply-email-workers/
