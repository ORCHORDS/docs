# Locale Context Propagation Across Workers Service Bindings

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A example project platform request enters an edge Worker (locale negotiation, auth), which then fans out to downstream service-bound Workers for content rendering, search, and email dispatch. Each downstream Worker needs the resolved locale, the user's calendar preference, the number system preference, and the text direction. Without a disciplined propagation pattern, each Worker re-negotiates locale independently, producing inconsistent formatting across the response (e.g., a date in `dd/MM/yyyy` from the content Worker and a date in `MM/dd/yyyy` from the email Worker).

---

## Context

Cloudflare Workers **service bindings** allow one Worker to call another as a `fetch`-like subrequest without leaving the Cloudflare network. The calling Worker constructs a `Request` object; the callee receives it normally. There is no shared memory, no automatic header forwarding, and no propagated execution context between Workers.

The recommended pattern for locale propagation is to encode the resolved locale context as a small JSON header (`X-Locale-Context`) set by the entry Worker and read by all downstream Workers. This header travels on the internal service binding call, never reaches the browser, and is stripped by the edge before the final response.

The context object carries enough information to reconstruct all `Intl.*` constructors the downstream Worker needs without re-running Accept-Language negotiation or a D1 lookup.

---

## Locale Context Type and Serialization

Define a shared type for the locale context. Both the entry Worker and all downstream Workers import this type from a shared package or a copy in each Worker's `src/types/locale-context.ts`.

```typescript
// packages/shared/src/locale-context.ts

/**
 * Fully resolved locale context forwarded via X-Locale-Context header
 * on every inter-Worker service binding call.
 */
export interface LocaleContext {
  /** BCP 47 language tag as negotiated from Accept-Language */
  locale: string;
  /** IANA time zone identifier resolved from CF-IPCountry or user pref */
  timeZone: string;
  /** ISO 4217 currency code resolved from user preferences */
  currency: string;
  /** Text direction inferred from locale */
  dir: "ltr" | "rtl";
  /** Unicode calendar extension, e.g. "gregory", "islamic-umalqura" */
  calendar: string;
  /** Unicode number system extension, e.g. "latn", "arab", "deva" */
  numberingSystem: string;
  /** Whether locale was explicitly set by the user (vs. inferred) */
  explicit: boolean;
}

export const DEFAULT_LOCALE_CONTEXT: LocaleContext = {
  locale: "en",
  timeZone: "UTC",
  currency: "USD",
  dir: "ltr",
  calendar: "gregory",
  numberingSystem: "latn",
  explicit: false,
};

const HEADER = "X-Locale-Context";
const STRIP_HEADER = "X-Locale-Context-Strip"; // signal to edge to strip on egress

export function encodeLocaleContext(ctx: LocaleContext): string {
  return btoa(JSON.stringify(ctx));
}

export function decodeLocaleContext(header: string | null): LocaleContext {
  if (!header) return DEFAULT_LOCALE_CONTEXT;
  try {
    return JSON.parse(atob(header)) as LocaleContext;
  } catch {
    return DEFAULT_LOCALE_CONTEXT;
  }
}

export { HEADER as LOCALE_CONTEXT_HEADER, STRIP_HEADER as LOCALE_STRIP_HEADER };
```

Base64-encoding the JSON keeps the header value a single ASCII token, avoiding issues with special characters in some header-parsing implementations.

---

## Entry Worker: Resolving and Injecting Locale Context

```typescript
// workers/entry/src/index.ts

import {
  type LocaleContext,
  DEFAULT_LOCALE_CONTEXT,
  encodeLocaleContext,
  LOCALE_CONTEXT_HEADER,
} from "../../packages/shared/src/locale-context";

export interface Env {
  DB: D1Database;
  CONTENT_WORKER: Fetcher;  // service binding
  SEARCH_WORKER: Fetcher;   // service binding
  EMAIL_WORKER: Fetcher;    // service binding
}

interface UserPrefsRow {
  locale: string;
  time_zone: string;
  currency: string;
  calendar: string;
  numbering_system: string;
}

const RTL_LOCALES = /^(ar|he|fa|ur|ps|sd|ug|yi|dv|ky-Arab)/;

async function resolveLocaleContext(
  request: Request,
  env: Env,
  userId: string | null
): Promise<LocaleContext> {
  // 1. Try user preferences from D1
  if (userId) {
    const row = await env.DB
      .prepare(
        "SELECT locale, time_zone, currency, calendar, numbering_system FROM user_prefs WHERE user_id = ?"
      )
      .bind(userId)
      .first<UserPrefsRow>();

    if (row) {
      return {
        locale: row.locale,
        timeZone: row.time_zone,
        currency: row.currency,
        dir: RTL_LOCALES.test(row.locale) ? "rtl" : "ltr",
        calendar: row.calendar,
        numberingSystem: row.numbering_system,
        explicit: true,
      };
    }
  }

  // 2. Fall back to Accept-Language negotiation
  const acceptLang = request.headers.get("Accept-Language") ?? "en";
  const supported = ["en", "fr", "de", "ar", "ja", "zh-Hans", "hi", "tr"];
  const negotiated =
    new Intl.LocaleMatcher
      ? Intl.LocaleMatcher.match(
          acceptLang.split(",").map((s) => s.split(";")[0].trim()),
          supported,
          "en"
        )
      : "en"; // fallback if LocaleMatcher not available

  // 3. Derive remaining fields from the locale
  const locale = new Intl.Locale(negotiated).maximize();
  const cf = (request as Request & { cf?: { timezone?: string; country?: string } }).cf;

  return {
    locale: negotiated,
    timeZone: cf?.timezone ?? "UTC",
    currency: currencyForCountry(cf?.country ?? "US"),
    dir: RTL_LOCALES.test(negotiated) ? "rtl" : "ltr",
    calendar: locale.calendar ?? "gregory",
    numberingSystem: locale.numberingSystem ?? "latn",
    explicit: false,
  };
}

function currencyForCountry(country: string): string {
  const map: Record<string, string> = {
    US: "USD", GB: "GBP", DE: "EUR", FR: "EUR", JP: "JPY",
    CN: "CNY", IN: "INR", BR: "BRL", AU: "AUD", CA: "CAD",
    SA: "SAR", AE: "AED", EG: "EGP", TR: "TRY",
  };
  return map[country] ?? "USD";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // In production, extract userId from a verified JWT / session cookie
    const userId = request.headers.get("X-User-Id");

    const localeCtx = await resolveLocaleContext(request, env, userId);
    const encoded = encodeLocaleContext(localeCtx);

    // Attach locale context to every downstream subrequest
    function withLocaleCtx(req: Request): Request {
      const h = new Headers(req.headers);
      h.set(LOCALE_CONTEXT_HEADER, encoded);
      return new Request(req.url, { ...req, headers: h });
    }

    if (url.pathname.startsWith("/search")) {
      return env.SEARCH_WORKER.fetch(withLocaleCtx(request));
    }
    if (url.pathname.startsWith("/email")) {
      return env.EMAIL_WORKER.fetch(withLocaleCtx(request));
    }
    return env.CONTENT_WORKER.fetch(withLocaleCtx(request));
  },
};
```

---

## Downstream Worker: Reading Locale Context

```typescript
// workers/content/src/index.ts

import {
  decodeLocaleContext,
  LOCALE_CONTEXT_HEADER,
  type LocaleContext,
} from "../../packages/shared/src/locale-context";

export interface Env {
  DB: D1Database;
}

function formatDate(iso: string, ctx: LocaleContext): string {
  return new Intl.DateTimeFormat(ctx.locale, {
    dateStyle: "long",
    timeZone: ctx.timeZone,
    calendar: ctx.calendar,
    // @ts-expect-error — numberingSystem not yet in all TS definitions
    numberingSystem: ctx.numberingSystem,
  }).format(new Date(iso));
}

function formatAmount(amount: number, ctx: LocaleContext): string {
  return new Intl.NumberFormat(ctx.locale, {
    style: "currency",
    currency: ctx.currency,
    numberingSystem: ctx.numberingSystem,
  } as Intl.NumberFormatOptions).format(amount);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const ctx = decodeLocaleContext(request.headers.get(LOCALE_CONTEXT_HEADER));

    const row = await env.DB
      .prepare("SELECT title, price, published_at FROM articles WHERE slug = ?")
      .bind(new URL(request.url).searchParams.get("slug") ?? "")
      .first<{ title: string; price: number; published_at: string }>();

    if (!row) return new Response("Not found", { status: 404 });

    const body = JSON.stringify({
      title: row.title,
      price: formatAmount(row.price, ctx),
      publishedAt: formatDate(row.published_at, ctx),
      dir: ctx.dir,
      locale: ctx.locale,
    });

    return new Response(body, {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## Stripping the Internal Header at the Edge

The `X-Locale-Context` header must never reach the browser — it is an internal routing signal and can expose user preference data. Use a response transform to strip it.

```typescript
// workers/entry/src/strip-internal-headers.ts

const INTERNAL_HEADERS = [
  "X-Locale-Context",
  "X-Locale-Context-Strip",
  "X-User-Id",
  "X-Detected-Script",
  "X-Locale-Pipeline",
];

export function stripInternalHeaders(response: Response): Response {
  const h = new Headers(response.headers);
  for (const name of INTERNAL_HEADERS) {
    h.delete(name);
  }
  return new Response(response.body, { ...response, headers: h });
}
```

Apply in the entry Worker's fetch after all subrequests resolve:

```typescript
const upstream = await env.CONTENT_WORKER.fetch(withLocaleCtx(request));
return stripInternalHeaders(upstream);
```

---

## wrangler.toml Service Binding Configuration

```toml
# workers/entry/wrangler.toml

name = "example project-entry"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[[services]]
binding = "CONTENT_WORKER"
service = "example project-content"

[[services]]
binding = "SEARCH_WORKER"
service = "example project-search"

[[services]]
binding = "EMAIL_WORKER"
service = "example project-email"

[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

---

## Anti-patterns

- **Re-negotiating locale in each downstream Worker.** Without a propagated context, downstream Workers either use a hardcoded default or redo D1 lookups — wasting latency and risking divergent results.
- **Passing locale only as a URL query parameter.** A query param is visible in logs, can be cached by intermediate layers, and requires every downstream URL to be constructed carefully. A header travels transparently.
- **Storing the locale context in a Durable Object for the request lifetime.** Durable Objects are designed for long-lived state, not per-request scratch space. The header-propagation pattern has zero overhead beyond header serialization.
- **Trusting the `X-Locale-Context` header if it arrives from external clients.** The entry Worker must set (or overwrite) this header — never read a value the browser sent.
- **Using a plain JSON string in the header.** JSON can contain commas, colons, and quote characters that break header parsers in some middleware. Base64-encode the JSON as shown above.

---

## Gotchas

- `Intl.LocaleMatcher` is not yet universally available in Workers. Guard with a capability check or fall back to a simple priority-list lookup.
- `(request as any).cf.timezone` is present on inbound requests from the internet but may be absent on service binding subrequests (the `cf` object is synthesized by the Cloudflare network layer for external ingress). Always provide a UTC fallback.
- The `calendar` and `numberingSystem` fields from `Intl.Locale.maximize()` are only populated when the BCP 47 tag explicitly includes Unicode extension subtags (e.g., `ar-u-ca-islamic-umalqura-nu-arab`). For plain tags like `ar`, maximize returns the default gregorian/arab — which is correct, but verify your user preferences store the full extended tag if needed.
- Service bindings are synchronous in terms of the Workers runtime model — the entry Worker awaits the subrequest, and the entire chain counts against the CPU time limit (50 ms default; 30 s on Workers Paid). Parallelize independent downstream calls with `Promise.all`.
- `btoa` and `atob` are available globally in Workers for simple base64 encoding. They operate on binary strings, not arbitrary Unicode. JSON.stringify produces only ASCII-safe output for the fields in `LocaleContext`, so `btoa(JSON.stringify(...))` is safe here.

---

## Verification

```typescript
// tests/locale-context.test.ts
import { describe, it, expect } from "vitest";
import {
  encodeLocaleContext,
  decodeLocaleContext,
  DEFAULT_LOCALE_CONTEXT,
} from "../packages/shared/src/locale-context";

describe("locale context serialization", () => {
  it("round-trips through encode/decode", () => {
    const ctx = {
      ...DEFAULT_LOCALE_CONTEXT,
      locale: "ar",
      dir: "rtl" as const,
      currency: "SAR",
      timeZone: "Asia/Riyadh",
      calendar: "islamic-umalqura",
      numberingSystem: "arab",
      explicit: true,
    };
    const encoded = encodeLocaleContext(ctx);
    expect(decodeLocaleContext(encoded)).toEqual(ctx);
  });

  it("returns default context for null header", () => {
    expect(decodeLocaleContext(null)).toEqual(DEFAULT_LOCALE_CONTEXT);
  });

  it("returns default context for corrupted header", () => {
    expect(decodeLocaleContext("not-base64!!")).toEqual(DEFAULT_LOCALE_CONTEXT);
  });
});
```

Run: `npx vitest run tests/locale-context.test.ts`

In production, verify propagation by temporarily logging the `X-Locale-Context` header inside a downstream Worker and checking Cloudflare Workers Logs (Tail Workers) for the expected base64 payload.

---

## Related

- `locale-negotiation-accept-language.md`
- `locale-fallback-chain.md`
- `workers-durable-objects-locale-session-state.md`
- `date-time-timezone-workers-edge-formatting.md`
- `currency-formatting-cloudflare-workers-intl-numberformat.md`

---

## Sources

- Cloudflare Workers Service Bindings: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- BCP 47 Unicode Extension Subtags (UTS #35): https://unicode.org/reports/tr35/
- Cloudflare `cf` object properties: https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- IANA Time Zone Database: https://www.iana.org/time-zones
- `Intl.Locale.prototype.maximize()`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/Locale/maximize
