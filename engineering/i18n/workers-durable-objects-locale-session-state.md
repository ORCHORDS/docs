# Durable Objects for Per-User Locale Session State in Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A stateless Worker reads the `Accept-Language` header or a `locale` cookie on every request and re-derives the user's locale from scratch each time. When the user changes their language preference mid-session (e.g., via a UI dropdown), the next request might land on a different edge node that knows nothing about the change — because cookies can be stale, KV has milliseconds of eventual-consistency lag, and there is no canonical "session" in a stateless edge runtime.

You need a single authoritative source of truth for locale preference that:
- is mutable within a session (the user can toggle language live),
- is strongly consistent (no stale reads after a write),
- is co-located near the user (low latency),
- does not require a round-trip to an origin database.

Cloudflare Durable Objects provide exactly this: a singleton actor with its own storage, addressable by a stable key, guaranteed to run in one location at a time.

---

## Context

Durable Objects (DOs) are Cloudflare Workers that carry persistent storage and receive messages sequentially. Each DO instance lives in one Cloudflare data-centre and processes requests one at a time — giving you strong consistency without locks.

For locale state the model is simple:

```
User ID  ──▶  DO name  ──▶  single DO instance  ──▶  this.ctx.storage
```

The DO instance stores the user's current locale (and any related preferences) and serves reads/writes atomically. All Workers that handle requests for this user forward locale reads/writes to the same DO instance via a Service Binding stub.

This pattern is distinct from:
- **KV** — eventually consistent, read-heavy; wrong for writes that must be immediately visible everywhere.
- **Cookies** — client-owned; can be stale or spoofed; require a round-trip back to the browser.
- **D1** — globally replicated but not strongly consistent for concurrent writes to the same row without transactions.

---

## 1. Wrangler Configuration

```toml
# wrangler.toml
name = "i18n-gateway"
compatibility_date = "2025-09-01"

[[durable_objects.bindings]]
name        = "LOCALE_SESSION"
class_name  = "LocaleSession"

[[migrations]]
tag  = "v1"
new_classes = ["LocaleSession"]

[vars]
SUPPORTED_LOCALES = "en,fr,de,ja,ar,pt-BR,zh-Hans"
DEFAULT_LOCALE    = "en"
```

The binding `LOCALE_SESSION` is available as `env.LOCALE_SESSION` inside every Worker handler in this script.

---

## 2. The LocaleSession Durable Object

```typescript
// src/locale-session.ts

export interface LocalePreferences {
  locale: string;
  timezone?: string;
  currency?: string;
  updatedAt: number; // Unix ms
}

const STORAGE_KEY = "prefs";
const SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

export class LocaleSession implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    switch (`${request.method} ${url.pathname}`) {
      case "GET /prefs":
        return this.getPrefs();
      case "PUT /prefs":
        return this.putPrefs(request);
      case "DELETE /prefs":
        return this.deletePrefs();
      default:
        return new Response("Not found", { status: 404 });
    }
  }

  private async getPrefs(): Promise<Response> {
    const prefs = await this.state.storage.get<LocalePreferences>(STORAGE_KEY);

    if (!prefs) {
      return new Response(JSON.stringify(null), {
        headers: { "content-type": "application/json" },
      });
    }

    // Evict stale sessions so storage does not accumulate indefinitely.
    if (Date.now() - prefs.updatedAt > SESSION_TTL_MS) {
      await this.state.storage.delete(STORAGE_KEY);
      return new Response(JSON.stringify(null), {
        headers: { "content-type": "application/json" },
      });
    }

    return new Response(JSON.stringify(prefs), {
      headers: { "content-type": "application/json" },
    });
  }

  private async putPrefs(request: Request): Promise<Response> {
    let body: Partial<LocalePreferences>;
    try {
      body = await request.json();
    } catch {
      return new Response("Bad JSON", { status: 400 });
    }

    // Read existing prefs to merge (partial update semantics).
    const existing =
      (await this.state.storage.get<LocalePreferences>(STORAGE_KEY)) ?? {};

    const merged: LocalePreferences = {
      locale: body.locale ?? existing.locale ?? "en",
      timezone: body.timezone ?? existing.timezone,
      currency: body.currency ?? existing.currency,
      updatedAt: Date.now(),
    };

    await this.state.storage.put(STORAGE_KEY, merged);

    return new Response(JSON.stringify(merged), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }

  private async deletePrefs(): Promise<Response> {
    await this.state.storage.delete(STORAGE_KEY);
    return new Response(null, { status: 204 });
  }
}
```

All three operations — GET, PUT, DELETE — run inside the DO's single-threaded event loop, so there are no concurrent-write races even if two Workers call the same instance simultaneously (the second call queues behind the first).

---

## 3. Routing Requests Through the Gateway Worker

```typescript
// src/index.ts
import { LocaleSession } from "./locale-session";

export { LocaleSession }; // re-export so Wrangler registers the class

interface Env {
  LOCALE_SESSION: DurableObjectNamespace;
  SUPPORTED_LOCALES: string;
  DEFAULT_LOCALE: string;
}

/**
 * Derive a stable DO name from a user identifier.
 * Use a hashed/opaque value in production (session token, UID).
 */
function doNameFromRequest(request: Request): string {
  const sessionId =
    parseCookie(request.headers.get("cookie") ?? "", "session_id") ??
    "anonymous";
  return `locale-session:${sessionId}`;
}

function parseCookie(header: string, name: string): string | undefined {
  return header
    .split(";")
    .map((p) => p.trim().split("="))
    .find(([k]) => k === name)?.[1];
}

async function getLocaleFromDO(
  ns: DurableObjectNamespace,
  doName: string
): Promise<string | null> {
  const id = ns.idFromName(doName);
  const stub = ns.get(id);
  const res = await stub.fetch("https://internal/prefs");
  const prefs = await res.json<{ locale?: string } | null>();
  return prefs?.locale ?? null;
}

async function setLocaleInDO(
  ns: DurableObjectNamespace,
  doName: string,
  locale: string
): Promise<void> {
  const id = ns.idFromName(doName);
  const stub = ns.get(id);
  await stub.fetch("https://internal/prefs", {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ locale }),
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const supported = env.SUPPORTED_LOCALES.split(",");
    const doName = doNameFromRequest(request);

    // --- API: update locale preference ---
    if (url.pathname === "/api/locale" && request.method === "PUT") {
      const { locale } = await request.json<{ locale: string }>();
      if (!supported.includes(locale)) {
        return new Response("Unsupported locale", { status: 422 });
      }
      await setLocaleInDO(env.LOCALE_SESSION, doName, locale);
      return new Response(JSON.stringify({ locale }), {
        headers: {
          "content-type": "application/json",
          // Reflect in a cookie so the browser can read it client-side.
          "set-cookie": `locale=${locale}; Path=/; SameSite=Lax; Max-Age=2592000`,
        },
      });
    }

    // --- All other requests: read locale and pass downstream ---
    let locale =
      (await getLocaleFromDO(env.LOCALE_SESSION, doName)) ??
      parseCookie(request.headers.get("cookie") ?? "", "locale") ??
      negotiateFromHeader(
        request.headers.get("accept-language") ?? "",
        supported
      ) ??
      env.DEFAULT_LOCALE;

    // Clone request with locale header for downstream services.
    const modifiedRequest = new Request(request, {
      headers: {
        ...Object.fromEntries(request.headers),
        "x-locale": locale,
      },
    });

    // Fetch from origin (or return a localised response directly).
    const response = await fetch(modifiedRequest);
    return response;
  },
} satisfies ExportedHandler<Env>;

function negotiateFromHeader(
  header: string,
  supported: string[]
): string | undefined {
  // Simplified BCP47 negotiation — replace with a proper library in production.
  return header
    .split(",")
    .map((p) => p.trim().split(";")[0].trim())
    .find((tag) => supported.includes(tag));
}
```

The key pattern: the Worker calls `ns.idFromName(doName)` — a deterministic mapping from the DO's string name to a `DurableObjectId`. Cloudflare routes all calls for the same ID to the same physical instance, regardless of which edge node the Worker runs on.

---

## 4. Handling Unauthenticated Users

Anonymous users have no stable user ID, so their DO name is derived from a short-lived session token stored in a cookie:

```typescript
// src/session-bootstrap.ts

const SESSION_COOKIE = "session_id";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 30; // 30 days

/**
 * If the request has no session cookie, generate one and attach it
 * to both the response Set-Cookie header and the forwarded request.
 */
export function ensureSessionCookie(
  request: Request,
  response: Response
): { request: Request; response: Response; sessionId: string } {
  const existing = parseCookie(
    request.headers.get("cookie") ?? "",
    SESSION_COOKIE
  );
  if (existing) {
    return { request, response, sessionId: existing };
  }

  const sessionId = crypto.randomUUID();

  const newRequest = new Request(request, {
    headers: {
      ...Object.fromEntries(request.headers),
      cookie:
        (request.headers.get("cookie") ?? "") +
        `; ${SESSION_COOKIE}=${sessionId}`,
    },
  });

  const newResponse = new Response(response.body, response);
  newResponse.headers.append(
    "set-cookie",
    `${SESSION_COOKIE}=${sessionId}; Path=/; SameSite=Lax; HttpOnly; Max-Age=${SESSION_TTL_SECONDS}`
  );

  return { request: newRequest, response: newResponse, sessionId };
}

function parseCookie(header: string, name: string): string | undefined {
  return header
    .split(";")
    .map((p) => p.trim().split("="))
    .find(([k]) => k.trim() === name)?.[1];
}
```

Wire `ensureSessionCookie` at the top of your `fetch` handler before calling into the DO, so every visitor gets a stable DO name.

---

## 5. Testing Locale Switching End-to-End

```bash
# Bootstrap a session (no cookie → Worker sets one automatically)
SESSION=$(curl -sc /tmp/cookies.txt https://example.workers.dev/ -o /dev/null -w '%{filename_effective}')

# Switch locale to French
curl -sb /tmp/cookies.txt \
     -X PUT https://example.workers.dev/api/locale \
     -H 'content-type: application/json' \
     -d '{"locale":"fr"}' | jq .

# Subsequent request should carry x-locale: fr downstream
curl -sb /tmp/cookies.txt -I https://example.workers.dev/ | grep x-locale
```

In a unit-test harness (Miniflare / `@cloudflare/vitest-pool-workers`):

```typescript
import { env } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("LocaleSession DO", () => {
  it("returns null prefs for a new session", async () => {
    const id = env.LOCALE_SESSION.idFromName("test-user-1");
    const stub = env.LOCALE_SESSION.get(id);
    const res = await stub.fetch("https://internal/prefs");
    expect(await res.json()).toBeNull();
  });

  it("persists and reads back a locale", async () => {
    const id = env.LOCALE_SESSION.idFromName("test-user-2");
    const stub = env.LOCALE_SESSION.get(id);

    await stub.fetch("https://internal/prefs", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ locale: "ja" }),
    });

    const res = await stub.fetch("https://internal/prefs");
    const prefs = await res.json<{ locale: string }>();
    expect(prefs.locale).toBe("ja");
  });
});
```

---

## Anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Using `idFromName(userId)` with a plaintext user ID from the URL | Allows ID enumeration across users | Hash or HMAC the user ID before using it as the DO name |
| Storing the entire translation bundle in DO storage | DO storage has a 128 KiB per-key limit; large bundles overflow | Store only the locale tag; keep translation bundles in KV/R2 |
| Calling the DO on every static asset request | Unnecessary latency for assets that don't need personalisation | Cache the locale in a Worker-level variable within a single request; only call the DO on document requests |
| One DO for all users (`idFromName("global")`) | Serialises all locale reads/writes through one actor; becomes a bottleneck | One DO per user/session — that is the intended model |
| Not deleting stale DOs | Accumulates billable storage over time | Implement TTL-based eviction inside `getPrefs` (shown above) or use the Alarm API to schedule cleanup |

---

## Gotchas

- **Cold start latency:** A DO that has not received traffic recently needs to be hydrated from disk. Add a 10–50 ms warm-up latency budget in your SLA. Use the `hibernatable WebSockets` API if you need persistent warm state.
- **Cross-region requests:** `ns.idFromName` always routes to the DO's home region. If a user in Tokyo hits a DO located in Frankfurt (because their first request was processed there), round-trip latency adds up. Use `locationHint` on `ns.get()` to nudge placement:
  ```typescript
  const stub = ns.get(id, { locationHint: "apac" });
  ```
- **DO storage is not replicated:** A DO instance's storage lives in one region. If Cloudflare migrates the DO, storage migrates too — but there is a brief unavailability window during migration.
- **Billing:** Each DO invocation (including `stub.fetch()`) is billed as a separate Worker invocation. Minimise unnecessary calls.
- **`idFromName` vs `idFromString`:** `idFromName` derives an ID from an arbitrary string; `idFromString` parses a previously serialised ID. Do not confuse them — `idFromString` will throw if given a plain string.

---

## Verification Checklist

- [ ] DO class is exported from the entry point file and listed in `wrangler.toml` `new_classes`.
- [ ] Session cookie is `HttpOnly` and `SameSite=Lax` (or `Strict`).
- [ ] Locale values are validated against the supported list before writing to DO storage.
- [ ] TTL eviction is implemented to prevent unbounded DO storage growth.
- [ ] Tests run against `@cloudflare/vitest-pool-workers` — not a plain Node test runner — so DO bindings resolve correctly.
- [ ] `locationHint` is set for latency-sensitive regions.

---

## Related Articles

- `locale-url-routing-workers-middleware.md`
- `translation-kv-caching-ttl-strategy.md`
- `locale-persistence-cookies-storage-2026.md`
- `language-detection-workers-accept-language.md`
- `d1-schema-locale-preferences-content-translations-2026.md`

---

## Sources

- Cloudflare Durable Objects documentation — https://developers.cloudflare.com/durable-objects/
- Durable Objects storage API — https://developers.cloudflare.com/durable-objects/api/storage-api/
- `@cloudflare/vitest-pool-workers` — https://developers.cloudflare.com/workers/testing/vitest-integration/
- Durable Objects locationHint — https://developers.cloudflare.com/durable-objects/reference/in-memory-state/#location-hints
