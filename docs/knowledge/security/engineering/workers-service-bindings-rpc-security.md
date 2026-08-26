# Workers Service Bindings RPC Security

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your platform runs multiple Cloudflare Workers that communicate via Service Bindings. An internal "auth" Worker is callable from a public-facing "api" Worker. A penetration tester finds that the auth Worker's RPC methods — intended as internal-only — lack their own authorization checks, trusting that only the api Worker will call them. A misconfigured binding scope or future Workers topology change could expose the internal Worker directly, granting unauthenticated access to privileged operations.

---

## Context

Cloudflare Service Bindings let Workers call each other over an in-process channel without traversing the public internet. Since Cloudflare 2024, **Workers RPC** (based on the `WorkerEntrypoint` class) extends this with strongly-typed, capability-style method calls. The security model differs from HTTP:

- No network hop — the callee cannot inspect `cf-connecting-ip` or HTTP origin headers.
- A binding is a **capability grant** in `wrangler.toml`; any Worker with the binding can invoke any exported method.
- There is no built-in caller identity: the callee Worker does not automatically know *which* other Worker is calling it.

This creates three threat surfaces:

1. **Confused-deputy attacks** — a public Worker relays untrusted user input directly into internal RPC arguments without sanitisation.
2. **Horizontal privilege escalation** — multiple Workers share a binding to a high-privilege Worker; a low-privilege Worker can call the same sensitive method as the privileged one.
3. **Missing depth-of-defence** — developers assume the binding is the authorization boundary; the internal Worker has no per-method access control of its own.

---

## Section 1 — Principle of Least Privilege in Binding Declarations

Keep binding scopes narrow in `wrangler.toml`. Each Worker should declare only the bindings it genuinely needs.

```toml
# wrangler.toml for the public "api" worker
name = "api"

[[services]]
binding = "AUTH_SVC"
service  = "auth-worker"
entrypoint = "AuthEntrypoint"   # restrict to a specific named entrypoint
```

Define a dedicated `AuthEntrypoint` that exposes only methods safe for the api Worker to call. High-privilege administrative methods live on a separate `AdminEntrypoint` bound only from an internal admin Worker.

```typescript
// auth-worker/src/index.ts
import { WorkerEntrypoint } from "cloudflare:workers";

// Public entrypoint – api worker can call these
export class AuthEntrypoint extends WorkerEntrypoint {
  async verifyToken(token: string): Promise<{ userId: string; scopes: string[] }> {
    return verifyJwt(token, this.env.JWT_SECRET);
  }
}

// Admin entrypoint – only admin-worker binding reaches this
export class AdminEntrypoint extends WorkerEntrypoint {
  async revokeAllUserSessions(userId: string): Promise<void> {
    await this.env.AUTH_DB.prepare(
      "DELETE FROM sessions WHERE user_id = ?"
    ).bind(userId).run();
  }
}

export default {
  async fetch(): Promise<Response> {
    return new Response("internal", { status: 403 });
  },
};
```

---

## Section 2 — Caller Identity via Signed Context Tokens

Service Bindings do not pass caller identity, so the callee must enforce it explicitly. Inject a short-lived, HMAC-signed caller token in every RPC call.

```typescript
// shared/caller-token.ts
const ENCODER = new TextEncoder();

export async function signCallerToken(
  callerId: string,
  secret: string,
  nowMs = Date.now()
): Promise<string> {
  const payload = `${callerId}:${Math.floor(nowMs / 30_000)}`; // 30-second window
  const key = await crypto.subtle.importKey(
    "raw",
    ENCODER.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, ENCODER.encode(payload));
  const b64 = btoa(String.fromCharCode(...new Uint8Array(sig)));
  return `${payload}:${b64}`;
}

export async function verifyCallerToken(
  token: string,
  allowedCaller: string,
  secret: string
): Promise<void> {
  const [callerId, window, sig] = token.split(":");
  if (callerId !== allowedCaller) throw new Error("caller mismatch");

  const nowWindow = Math.floor(Date.now() / 30_000);
  if (Math.abs(Number(window) - nowWindow) > 1) throw new Error("token expired");

  const expected = await signCallerToken(callerId, secret, Number(window) * 30_000);
  const [, , expectedSig] = expected.split(":");

  // Constant-time compare
  const a = ENCODER.encode(sig);
  const b = ENCODER.encode(expectedSig);
  if (a.length !== b.length) throw new Error("signature invalid");
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  if (diff !== 0) throw new Error("signature invalid");
}
```

The calling Worker signs its token and passes it as a first argument:

```typescript
// api-worker/src/index.ts
import { signCallerToken } from "../../shared/caller-token";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const token = await signCallerToken("api-worker", env.SERVICE_SHARED_SECRET);
    const authorization = request.headers.get("Authorization") ?? "";
    const jwtToken = authorization.replace("Bearer ", "");

    const identity = await env.AUTH_SVC.verifyToken(jwtToken, token); // pass caller token
    // ...
  },
};
```

The auth Worker validates it before any sensitive work:

```typescript
// auth-worker/src/index.ts
export class AuthEntrypoint extends WorkerEntrypoint {
  async verifyToken(
    token: string,
    callerToken: string
  ): Promise<{ userId: string; scopes: string[] }> {
    await verifyCallerToken(callerToken, "api-worker", this.env.SERVICE_SHARED_SECRET);
    return verifyJwt(token, this.env.JWT_SECRET);
  }
}
```

Store `SERVICE_SHARED_SECRET` as a Cloudflare Secret, not in `wrangler.toml`.

---

## Section 3 — Input Validation on RPC Arguments

RPC arguments cross trust boundaries: the callee receives raw TypeScript values from a potentially confused deputy. Validate every argument with a schema library before acting on it.

```typescript
import { z } from "zod";

const VerifyTokenArgs = z.object({
  token: z.string().min(32).max(4096).regex(/^[A-Za-z0-9\-_=.]+$/),
  scopes: z.array(z.string().max(64)).max(20).optional(),
});

export class AuthEntrypoint extends WorkerEntrypoint {
  async verifyToken(rawToken: unknown, callerToken: unknown): Promise<unknown> {
    // 1. Validate caller identity first
    await verifyCallerToken(String(callerToken), "api-worker", this.env.SERVICE_SHARED_SECRET);

    // 2. Validate arguments
    const parsed = VerifyTokenArgs.safeParse({ token: rawToken });
    if (!parsed.success) {
      throw new Error(`invalid arguments: ${parsed.error.message}`);
    }

    return verifyJwt(parsed.data.token, this.env.JWT_SECRET);
  }
}
```

Never pass raw user-controlled strings from an HTTP request body directly into an RPC call. Always sanitise and validate at the public Worker boundary first.

---

## Section 4 — Preventing Confused-Deputy via Structured Data Transfer Objects

Define explicit Data Transfer Objects (DTOs) for every RPC boundary. This prevents accidentally forwarding raw request body fields.

```typescript
// api-worker/src/handlers/login.ts
import { z } from "zod";

const LoginBody = z.object({
  email: z.string().email().max(256),
  password: <redacted-secret>
});

export async function handleLogin(request: Request, env: Env): Promise<Response> {
  const body = await request.json().catch(() => null);
  const parsed = LoginBody.safeParse(body);
  if (!parsed.success) {
    return new Response("Bad Request", { status: 400 });
  }

  // Only pass the validated, typed DTO — never spread raw body into RPC call
  const result = await env.AUTH_SVC.authenticate({
    email: parsed.data.email,
    password: <redacted-secret>
  });

  return Response.json({ token: result.token });
}
```

---

## Section 5 — Rate-Limiting Internal RPC Calls

Even internal Workers can be abused by a confused deputy passing high-frequency requests. Protect expensive internal operations with a Durable Object rate limiter attached to the callee.

```typescript
// auth-worker/src/index.ts
export class AuthEntrypoint extends WorkerEntrypoint {
  async verifyToken(token: string, callerToken: string): Promise<unknown> {
    await verifyCallerToken(callerToken, "api-worker", this.env.SERVICE_SHARED_SECRET);

    // Rate-limit by a stable key derived from the token prefix, not the full token
    const prefix = token.slice(0, 8);
    const limiter = this.env.RATE_LIMITER.get(
      this.env.RATE_LIMITER.idFromName(`auth:${prefix}`)
    );
    const limited = await limiter.fetch(new Request("https://internal/check"));
    if (limited.status === 429) throw new Error("rate limit exceeded");

    return verifyJwt(token, this.env.JWT_SECRET);
  }
}
```

---

## Section 6 — Audit Logging RPC Calls

Log every cross-Worker RPC invocation with caller identity, method name, and outcome. Use Tail Workers to ship logs without blocking the hot path.

```typescript
// tail-worker/src/index.ts
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const event of events) {
      for (const log of event.logs) {
        if (log.message[0]?.startsWith("rpc:")) {
          await fetch("https://log-sink.example.com/ingest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              timestamp: event.eventTimestamp,
              scriptName: event.scriptName,
              message: log.message,
              outcome: event.outcome,
            }),
          });
        }
      }
    }
  },
};
```

In the callee Worker, emit structured RPC audit events:

```typescript
console.log(
  JSON.stringify({
    type: "rpc",
    method: "verifyToken",
    caller: "api-worker",
    outcome: "success",
    durationMs: Date.now() - start,
  })
);
```

---

## Anti-patterns

- **Trusting the binding as the only authorization boundary.** If the topology changes (a new internal Worker is added or a binding is misconfigured), the internal Worker is wide open.
- **Passing `request.body` directly as an RPC argument** without parsing and validating it in the public Worker.
- **Using `env.MY_BINDING.fetch()` instead of typed RPC.** Switching to `WorkerEntrypoint` with named methods enables schema validation and IDE type-checking.
- **Sharing one large `SERVICE_SHARED_SECRET` across all Workers.** Each Worker pair should have its own secret, limiting blast radius of a compromise.
- **No error differentiation.** Throwing generic `Error` from validation failures makes it hard to distinguish input errors from infrastructure errors in logs.

---

## Gotchas

- RPC arguments are serialized via the [structured clone algorithm](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Structured_clone_algorithm). `undefined`, functions, and class instances without `[Symbol.hasInstance]` do not survive the boundary. Use plain objects and primitives in your DTOs.
- A Worker calling itself via a self-binding is possible but the caller identity check will fail if it uses the same `callerToken` approach — guard against this in testing.
- Tail Workers see RPC invocations as `fetch` events if the callee Worker's `default` export handles them. Structured RPC on `WorkerEntrypoint` appears under a different event type in tail logs; confirm behaviour in your Cloudflare dashboard before relying on tail logging for RPC audit.
- Secrets added with `wrangler secret put` are scoped per-Worker. A secret named `SERVICE_SHARED_SECRET` in the api Worker is a different value from the same-named secret in the auth Worker. Both Workers need the same value provisioned independently.

---

## Verification

```bash
# Confirm the internal worker entrypoint cannot be reached from the internet
curl -i https://auth-worker.example.com/
# Expected: 403

# Run integration test asserting caller-token rejection
npx vitest run tests/service-bindings-security.test.ts

# Grep wrangler.toml for overly broad bindings (no entrypoint restriction)
grep -n '\[\[services\]\]' wrangler.toml | head -20
# Then verify every service block has an 'entrypoint' field
```

Sample Vitest test:

```typescript
import { env } from "cloudflare:test";
import { AuthEntrypoint } from "../src/index";

test("rejects call with missing caller token", async () => {
  const entrypoint = new AuthEntrypoint(env, {} as ExecutionContext);
  await expect(entrypoint.verifyToken("some.jwt.token", "")).rejects.toThrow(
    "signature invalid"
  );
});

test("rejects call with wrong caller id", async () => {
  const token = await signCallerToken("evil-worker", env.SERVICE_SHARED_SECRET);
  const entrypoint = new AuthEntrypoint(env, {} as ExecutionContext);
  await expect(entrypoint.verifyToken("some.jwt.token", token)).rejects.toThrow(
    "caller mismatch"
  );
});
```

---

## Related

- `durable-objects-auth-patterns.md`
- `multi-tenancy-isolation-workers-kv-d1.md`
- `rate-limiting-per-user-d1-durable-objects.md`
- `outbound-url-policy-ssrf-and-dns-rebinding-resistance.md`
- `jwt-best-practices.md`

---

## Sources

- Cloudflare Workers RPC documentation: https://developers.cloudflare.com/workers/runtime-apis/rpc/
- Cloudflare Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- Confused-Deputy Problem — Hardy (1988): https://dl.acm.org/doi/10.1145/41949.41958
- Structured Clone Algorithm — MDN: https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API/Structured_clone_algorithm
- Zod input validation: https://zod.dev
