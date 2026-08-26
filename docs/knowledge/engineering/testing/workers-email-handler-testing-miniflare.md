# Unit Testing Email Worker Handlers with Miniflare

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a Cloudflare Email Worker that parses incoming SMTP messages, stores metadata in D1, and forwards or rejects mail based on business rules. Testing this end-to-end via live email delivery is painfully slow and non-deterministic; you need a way to construct synthetic `EmailMessage` objects and drive the `email()` handler in isolation.

---

## Context

Email Workers expose an `email(message, env, ctx)` export that receives an `EmailMessage` — a platform-provided object with `.from`, `.to`, `.headers`, and a `ReadableStream` `.raw` body. Miniflare (used internally by `@cloudflare/vitest-pool-workers`) does not auto-construct `EmailMessage` instances, so you build a plain object that satisfies the interface and pass it directly. Side effects — KV writes, D1 inserts, `forward()` and `setReject()` calls — are asserted via Vitest spies attached to the mock object. Because `setReject()` takes an SMTP rejection reason string and `forward()` takes an address plus optional headers, the spy signatures must match exactly.

---

## Setup / Config

`wrangler.toml`:
```toml
[send_email]
binding = "SEND_EMAIL"

[[d1_databases]]
binding = "DB"
database_name = "orchords-local"
database_id = "00000000-0000-0000-0000-000000000000"

[[kv_namespaces]]
binding = "EMAIL_META"
id = "00000000000000000000000000000001"
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
          d1Databases: ["DB"],
          kvNamespaces: ["EMAIL_META"],
        },
      },
    },
  },
});
```

`src/worker-email.ts`:
```typescript
export interface Env {
  DB: D1Database;
  EMAIL_META: KVNamespace;
}

export default {
  async email(
    message: EmailMessage,
    env: Env,
    _ctx: ExecutionContext
  ): Promise<void> {
    const from = message.from;
    const subject = message.headers.get("subject") ?? "(no subject)";

    // Reject messages from blocked senders
    const blocked = await env.EMAIL_META.get(`blocked:${from}`);
    if (blocked) {
      message.setReject("Sender is blocked");
      return;
    }

    // Read body (first 4 KB)
    const reader = message.raw.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;
    while (total < 4096) {
      const { done, value } = await reader.read();
      if (done || !value) break;
      chunks.push(value);
      total += value.byteLength;
    }
    const body = new TextDecoder().decode(
      chunks.reduce((acc, c) => {
        const merged = new Uint8Array(acc.length + c.length);
        merged.set(acc);
        merged.set(c, acc.length);
        return merged;
      }, new Uint8Array(0))
    );

    // Persist metadata
    await env.DB.prepare(
      "INSERT INTO emails (from_addr, subject, preview) VALUES (?, ?, ?)"
    )
      .bind(from, subject, body.slice(0, 200))
      .run();

    // Forward to internal address
    await message.forward("internal@example.com");
  },
};
```

---

## Test Implementation

`src/worker-email.test.ts`:
```typescript
import { env } from "cloudflare:test";
import { describe, it, expect, vi, beforeAll, afterEach } from "vitest";
import worker from "./worker-email";

// ---------------------------------------------------------------------------
// Helper: build a minimal EmailMessage mock
// ---------------------------------------------------------------------------
function makeEmailMessage(options: {
  from: string;
  to: string;
  subject?: string;
  body?: string;
}): EmailMessage {
  const { from, to, subject = "Hello", body = "Test body" } = options;

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(body));
      controller.close();
    },
  });

  const headers = new Headers();
  headers.set("subject", subject);
  headers.set("from", from);
  headers.set("to", to);

  return {
    from,
    to,
    headers,
    raw: stream,
    rawSize: encoder.encode(body).byteLength,
    setReject: vi.fn<[reason: string], void>(),
    forward: vi.fn<[rcptTo: string, headers?: Headers], Promise<void>>(
      async () => {}
    ),
  } as unknown as EmailMessage;
}

// ---------------------------------------------------------------------------
// Shared execution context stub
// ---------------------------------------------------------------------------
const mockCtx: ExecutionContext = {
  waitUntil: vi.fn(),
  passThroughOnException: vi.fn(),
} as unknown as ExecutionContext;

// ---------------------------------------------------------------------------
// Schema setup
// ---------------------------------------------------------------------------
beforeAll(async () => {
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS emails (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      from_addr  TEXT NOT NULL,
      subject    TEXT,
      preview    TEXT,
      received_at INTEGER DEFAULT (unixepoch())
    )
  `);
});

afterEach(async () => {
  await env.DB.exec("DELETE FROM emails");
  // Clean up any KV keys set during the test
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("email() handler", () => {
  it("stores email metadata in D1 and forwards to internal address", async () => {
    const msg = makeEmailMessage({
      from: "fan@example.com",
      to: "contact@example.com",
      subject: "Love your tracks",
      body: "Hi Orchords team!",
    });

    await worker.email(msg, env as any, mockCtx);

    // setReject should NOT have been called
    expect(msg.setReject).not.toHaveBeenCalled();

    // forward() should target internal address
    expect(msg.forward).toHaveBeenCalledOnce();
    expect(msg.forward).toHaveBeenCalledWith("internal@example.com");

    // D1 row should exist
    const row = await env.DB.prepare(
      "SELECT from_addr, subject, preview FROM emails WHERE from_addr = ?"
    )
      .bind("fan@example.com")
      .first<{ from_addr: string; subject: string; preview: string }>();

    expect(row?.from_addr).toBe("fan@example.com");
    expect(row?.subject).toBe("Love your tracks");
    expect(row?.preview).toContain("Hi Orchords");
  });

  it("calls setReject() for blocked senders and skips D1 write", async () => {
    // Seed block list in KV
    await env.EMAIL_META.put("blocked:spam@bad.com", "1");

    const msg = makeEmailMessage({
      from: "spam@bad.com",
      to: "contact@example.com",
    });

    await worker.email(msg, env as any, mockCtx);

    expect(msg.setReject).toHaveBeenCalledOnce();
    expect(msg.setReject).toHaveBeenCalledWith("Sender is blocked");
    expect(msg.forward).not.toHaveBeenCalled();

    const count = await env.DB.prepare(
      "SELECT COUNT(*) as cnt FROM emails"
    ).first<{ cnt: number }>();
    expect(count?.cnt).toBe(0);
  });

  it("handles large body by only reading first 4 KB", async () => {
    const largeBody = "A".repeat(8192);
    const msg = makeEmailMessage({
      from: "sender@example.com",
      to: "contact@example.com",
      body: largeBody,
    });

    await worker.email(msg, env as any, mockCtx);

    const row = await env.DB.prepare(
      "SELECT preview FROM emails WHERE from_addr = ?"
    )
      .bind("sender@example.com")
      .first<{ preview: string }>();

    // preview is capped at 200 chars inside the handler
    expect(row?.preview.length).toBeLessThanOrEqual(200);
  });

  it("stores empty subject when header is absent", async () => {
    const msg = makeEmailMessage({
      from: "nosubject@example.com",
      to: "contact@example.com",
      subject: "",
    });
    // Override header to simulate missing subject
    (msg.headers as Headers).delete("subject");

    await worker.email(msg, env as any, mockCtx);

    const row = await env.DB.prepare(
      "SELECT subject FROM emails WHERE from_addr = ?"
    )
      .bind("nosubject@example.com")
      .first<{ subject: string }>();

    expect(row?.subject).toBe("(no subject)");
  });
});
```

---

## Anti-patterns

- **Using `fetch()` to simulate email delivery** — Email Workers use a distinct `email()` export, not HTTP; you must call the export directly.
- **Asserting on `forward()` return value** — `forward()` returns `void` in the type signature; assert on call arguments, not the return.
- **Forgetting to cancel the ReadableStream reader** — if the handler exits early (e.g. after `setReject`), the stream remains locked; call `reader.cancel()` in a `finally` block in the handler.
- **Mocking `Headers` with a plain object** — `message.headers.get()` expects a real `Headers` instance; use `new Headers()` in the mock helper.

---

## Gotchas

- `EmailMessage` is a platform type available in `@cloudflare/workers-types` — add `"types": ["@cloudflare/workers-types"]` to `tsconfig.json` to avoid `Cannot find name 'EmailMessage'` errors.
- `message.raw` is a `ReadableStream<Uint8Array>`, not a `ReadableStream<string>`; always decode with `TextDecoder`.
- `setReject()` and `forward()` are platform-enforced to be mutually exclusive at runtime; in unit tests both spies can be called since there is no enforcement layer.
- KV `put` in one test leaks into the next unless you call `delete` in `afterEach` — track keys set per test or use unique prefixes.

---

## Verification

```bash
# Run email handler tests
npx vitest run src/worker-email.test.ts

# Confirm types compile
npx tsc --noEmit

# Inspect KV state during a failing test
npx wrangler kv key list --namespace-id 00000000000000000000000000000001 --local
```

---

## Related

- `workers-queue-consumer-testing-vitest.md`
- `workers-d1-migration-test-vitest.md`

---

## Sources

- Cloudflare Email Workers Docs — https://developers.cloudflare.com/email-routing/email-workers/
- EmailMessage type reference — https://developers.cloudflare.com/workers/runtime-apis/email-message/
- Vitest Pool Workers — https://developers.cloudflare.com/workers/testing/vitest-integration/
