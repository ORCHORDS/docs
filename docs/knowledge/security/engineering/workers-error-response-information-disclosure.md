# Workers Error Response Information Disclosure Prevention

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Unhandled exceptions in a Cloudflare Worker surface raw stack traces, D1 query strings, Wrangler binding names, or internal environment variable names to HTTP clients in 500 responses. Similarly, validation errors echo user-supplied input verbatim, and 404 paths reveal internal routing structure. These leaks hand attackers a map of your application's internals — table names for SQL injection probing, file paths for traversal, or stack frames for gadget-chain discovery.

## Context

Workers default uncaught-exception behavior depends on the environment:
- **Development (`wrangler dev`)** — full stack traces are included in the response body.
- **Production** — by default Workers return a generic Cloudflare error page with a Ray ID, but a Worker that explicitly returns `new Response(err.message)` or `JSON.stringify(err)` in a catch block leaks the error to clients.

Error disclosure is particularly dangerous in Workers because exceptions often include D1 prepared-statement SQL (with column names), KV key prefixes, R2 bucket names, or internal service binding identifiers. A structured error handling strategy must: (1) log full context server-side, (2) return only a safe, opaque message to the client, and (3) include a correlation ID to link the two.

---

## 1. Top-Level Error Boundary in the Fetch Handler

```typescript
import { nanoid } from "nanoid";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const requestId = nanoid(12);

    try {
      return await handleRequest(request, env, ctx, requestId);
    } catch (err: unknown) {
      // Log full error server-side with context
      ctx.waitUntil(logError(err, request, requestId, env));

      // Return opaque error to client — no stack, no internals
      return Response.json(
        {
          error: "internal_server_error",
          message: "An unexpected error occurred.",
          requestId, // safe to expose — used for support lookup only
        },
        {
          status: 500,
          headers: {
            "Content-Type": "application/json",
            "X-Request-Id": requestId,
            "Cache-Control": "no-store",
          },
        },
      );
    }
  },
};
```

`ctx.waitUntil()` ensures the error log write completes even after the response is sent.

---

## 2. Structured Server-Side Error Logging to Tail Worker

```typescript
async function logError(
  err: unknown,
  request: Request,
  requestId: string,
  env: Env,
): Promise<void> {
  const entry = {
    requestId,
    timestamp: new Date().toISOString(),
    method: request.method,
    url: request.url,           // includes path — OK for server logs
    cfRay: request.headers.get("CF-Ray"),
    error: {
      name: err instanceof Error ? err.name : typeof err,
      message: err instanceof Error ? err.message : String(err),
      stack: err instanceof Error ? err.stack : undefined,
    },
  };

  // Write to analytics engine for structured querying
  env.ANALYTICS.writeDataPoint({
    blobs: [
      entry.requestId,
      entry.error.name,
      entry.error.message ?? "",
      entry.url,
    ],
    indexes: [entry.requestId],
  });
}
```

Tail Workers receive the full exception payload automatically — use them for log pipelines; the Analytics Engine write above is an additional structured index.

---

## 3. Domain-Specific Error Classes with Safe Public Messages

Define error classes that carry both a safe user-facing message and internal details:

```typescript
class AppError extends Error {
  readonly statusCode: number;
  readonly publicMessage: string;
  readonly code: string;

  constructor(opts: {
    statusCode: number;
    code: string;
    publicMessage: string;
    internalMessage: string;
  }) {
    super(opts.internalMessage); // full detail for server logs
    this.name = "AppError";
    this.statusCode = opts.statusCode;
    this.publicMessage = opts.publicMessage;
    this.code = opts.code;
  }
}

class NotFoundError extends AppError {
  constructor(resource: string, id: string) {
    super({
      statusCode: 404,
      code: "not_found",
      publicMessage: "The requested resource was not found.",
      internalMessage: `Resource '${resource}' with id '${id}' not found in D1`,
    });
  }
}

class DatabaseError extends AppError {
  constructor(query: string, cause: unknown) {
    super({
      statusCode: 500,
      code: "database_error",
      publicMessage: "A database error occurred.",
      // Internal message includes the query — NEVER sent to client
      internalMessage: `D1 query failed: ${query} — ${String(cause)}`,
    });
  }
}
```

---

## 4. Discriminated Error Handler in the Boundary

```typescript
function errorToResponse(err: unknown, requestId: string): Response {
  if (err instanceof AppError) {
    return Response.json(
      { error: err.code, message: err.publicMessage, requestId },
      { status: err.statusCode, headers: { "Cache-Control": "no-store" } },
    );
  }

  // Unknown error — never expose message or stack
  return Response.json(
    { error: "internal_server_error", message: "An unexpected error occurred.", requestId },
    { status: 500, headers: { "Cache-Control": "no-store" } },
  );
}
```

---

## 5. Validation Error Sanitization — Never Echo User Input

Zod and similar validators produce error messages that may include the user-supplied value in the `received` field. Strip those before returning:

```typescript
import { ZodError } from "zod";

function safeValidationError(err: ZodError): Response {
  const issues = err.issues.map((issue) => ({
    path: issue.path,     // field path — safe to expose
    code: issue.code,     // e.g. "invalid_type" — safe
    // Deliberately omit issue.received and issue.message to avoid echoing input
  }));

  return Response.json(
    { error: "validation_error", issues },
    { status: 400, headers: { "Cache-Control": "no-store" } },
  );
}
```

Validation error responses should enumerate which fields are invalid and why (type mismatch, too long) but never echo the raw value the caller sent.

---

## 6. 404 Responses — Avoid Path Disclosure

A 404 that echoes the requested path (`"Not found: /internal/admin/users/bulk-delete"`) reveals your routing structure:

```typescript
function notFoundResponse(requestId: string): Response {
  return Response.json(
    { error: "not_found", message: "The requested endpoint does not exist.", requestId },
    { status: 404, headers: { "Cache-Control": "no-store" } },
  );
}
```

Never include `request.url` or `request.pathname` in a client-visible 404 body.

---

## 7. Security Headers on All Error Responses

Error responses must carry the same security headers as success responses — many middleware chains apply headers only on 2xx:

```typescript
function addSecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  headers.set("Referrer-Policy", "no-referrer");
  return new Response(response.body, { status: response.status, headers });
}
```

Without `X-Content-Type-Options: nosniff`, a JSON error body containing HTML fragments may be rendered by IE-era and some mobile browsers as HTML, enabling reflected XSS via error messages.

---

## Anti-patterns

- **`catch (err) { return new Response(err.message) }`** — directly exposes internal error strings; the most common source of information disclosure in Workers.
- **`JSON.stringify(err)` in error responses** — non-enumerable Error properties serialize unpredictably; custom Error subclasses may expose internal fields.
- **Different error detail levels between environments using `env.ENVIRONMENT === "production"`** — staging environments are often reachable from the internet; apply the same opaque error policy everywhere.
- **Stack traces in error response headers** — some frameworks put debug info in `X-Debug-*` headers; never add these to production responses.
- **Returning `{error: err}` from an async handler without try/catch** — unhandled promise rejections in Workers propagate as 500s with varying default behavior across runtime versions.

## Gotchas

- `Error` objects do not serialize via `JSON.stringify()` — `JSON.stringify(new Error("oops"))` returns `"{}"`, silently dropping the message. An explicit `.message` access is needed but must only go to logs.
- Workers that use `Response.error()` return a network-level error, not an HTTP response — the client receives a fetch failure, not a JSON body. Use this only for cases where no HTTP response should reach the client (e.g., blocked requests).
- `ctx.waitUntil()` deadline is 30 seconds after the response is sent; error log writes should be fast (Analytics Engine or a Queue) to fit within this window.
- Cloudflare's own 5xx error pages include the Ray ID — your Workers 500 response should also include the Ray ID (`request.headers.get("CF-Ray")`) so support can correlate client-reported errors with Cloudflare logs.

## Verification

```bash
# Trigger an unhandled error and confirm no stack trace in response
curl -s -X GET https://api.example.com/deliberately-broken | jq .
# Expected: {"error":"internal_server_error","message":"An unexpected error occurred.","requestId":"<id>"}

# Confirm 404 does not echo path
curl -s -X GET https://api.example.com/internal/secret-route | jq .
# Expected: {"error":"not_found","message":"The requested endpoint does not exist.","requestId":"<id>"}

# Confirm validation error does not echo user input
curl -s -X POST https://api.example.com/users \
  -d '{"email":"<script>alert(1)</script>"}' | jq .
# Expected: {"error":"validation_error","issues":[{"path":["email"],"code":"invalid_string"}]}

# Check security headers on error response
curl -sI https://api.example.com/deliberately-broken | grep -i "x-content-type"
# Expected: x-content-type-options: nosniff
```

## Related

- `silent-catch-antipattern.md`
- `log-injection-prevention.md`
- `security-logging-what-to-log.md`
- `workers-tail-workers-security-event-streaming.md`
- `workers-sensitive-data-masking-response-transform.md`
- `api-schema-validation-openapi-zod-workers.md`

## Sources

- OWASP Top 10 2021 — A05: Security Misconfiguration (verbose error messages)
- OWASP Testing Guide — OTG-ERR-001: Testing for Improper Error Handling
- Cloudflare Workers — Error handling — https://developers.cloudflare.com/workers/observability/errors/
- CWE-209: Generation of Error Message Containing Sensitive Information
