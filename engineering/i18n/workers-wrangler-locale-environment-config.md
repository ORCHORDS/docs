# Locale Configuration via wrangler.toml Environment Variables

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Locale settings — supported locales, default locale, and fallback chain rules — are
hard-coded in TypeScript source, making it painful to update them without a code deploy
or to vary them between staging and production environments.

## Context
Cloudflare Workers exposes static configuration through `[vars]` in `wrangler.toml` and
through secrets bound as environment variables. Locale configuration is a prime candidate
for this treatment: it changes more often than business logic, it must differ between
environments (a staging Worker might support fewer locales), and it needs to be read at
runtime without importing a large locale-data bundle. This pattern externalizes locale
policy into the deployment manifest and validates it at Worker startup.

---

## wrangler.toml Configuration

```toml
# wrangler.toml

name = "my-app"
main = "src/worker.ts"
compatibility_date = "2026-01-01"

[vars]
# Comma-separated list of supported BCP-47 locale tags (order matters: priority order)
SUPPORTED_LOCALES = "en,fr,de,es,pt-BR,ja,zh-Hant"

# The locale to use when no match is found in SUPPORTED_LOCALES
DEFAULT_LOCALE = "en"

# Maximum number of subtags to walk in a fallback chain (prevents infinite loops)
LOCALE_FALLBACK_DEPTH = "4"

# Locale used for server-side logging and internal error messages (not user-facing)
INTERNAL_LOCALE = "en"

# Feature-flag: allow experimental locales not yet fully translated ("true"/"false")
ALLOW_PARTIAL_LOCALES = "false"

[env.staging.vars]
SUPPORTED_LOCALES = "en,fr,de"
DEFAULT_LOCALE = "en"
LOCALE_FALLBACK_DEPTH = "3"
ALLOW_PARTIAL_LOCALES = "true"

[env.production.vars]
SUPPORTED_LOCALES = "en,fr,de,es,pt-BR,ja,zh-Hant"
DEFAULT_LOCALE = "en"
LOCALE_FALLBACK_DEPTH = "4"
ALLOW_PARTIAL_LOCALES = "false"
```

---

## Parsing and Validating Locale Config at Startup

Parse the environment strings once at module scope so the cost is paid only on cold start,
not on every request:

```typescript
// src/lib/locale-config.ts

export interface LocaleConfig {
  supportedLocales: string[];
  defaultLocale: string;
  fallbackDepth: number;
  internalLocale: string;
  allowPartialLocales: boolean;
}

export interface Env {
  SUPPORTED_LOCALES: string;
  DEFAULT_LOCALE: string;
  LOCALE_FALLBACK_DEPTH: string;
  INTERNAL_LOCALE: string;
  ALLOW_PARTIAL_LOCALES: string;
}

/** Memoized config; reset between tests by reassigning cachedConfig. */
let cachedConfig: LocaleConfig | null = null;

export function getLocaleConfig(env: Env): LocaleConfig {
  if (cachedConfig) return cachedConfig;

  const supported = env.SUPPORTED_LOCALES
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  if (supported.length === 0) {
    throw new Error("[locale-config] SUPPORTED_LOCALES must not be empty");
  }

  const defaultLocale = env.DEFAULT_LOCALE?.trim();
  if (!defaultLocale) {
    throw new Error("[locale-config] DEFAULT_LOCALE must be set");
  }

  if (!supported.includes(defaultLocale)) {
    throw new Error(
      `[locale-config] DEFAULT_LOCALE "${defaultLocale}" is not in SUPPORTED_LOCALES`,
    );
  }

  const fallbackDepth = parseInt(env.LOCALE_FALLBACK_DEPTH ?? "4", 10);
  if (isNaN(fallbackDepth) || fallbackDepth < 1 || fallbackDepth > 10) {
    throw new Error("[locale-config] LOCALE_FALLBACK_DEPTH must be an integer 1–10");
  }

  cachedConfig = {
    supportedLocales: supported,
    defaultLocale,
    fallbackDepth,
    internalLocale: env.INTERNAL_LOCALE?.trim() || defaultLocale,
    allowPartialLocales: env.ALLOW_PARTIAL_LOCALES === "true",
  };

  return cachedConfig;
}

/**
 * Resolves the best supported locale for a requested locale tag.
 * Walks the BCP-47 subtag chain up to `fallbackDepth` steps,
 * then returns `defaultLocale` if nothing matches.
 */
export function resolveLocale(requested: string, config: LocaleConfig): string {
  const normalized = requested.replace(/_/g, "-").trim();
  const parts = normalized.split("-");

  for (let depth = parts.length; depth > 0 && depth >= parts.length - config.fallbackDepth; depth--) {
    const tag = parts.slice(0, depth).join("-");
    if (config.supportedLocales.includes(tag)) {
      return tag;
    }
  }

  return config.defaultLocale;
}
```

---

## Using Locale Config in the Request Handler

```typescript
// src/worker.ts

import { getLocaleConfig, resolveLocale, type Env } from "./lib/locale-config";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Parse and validate config on first request (cached thereafter)
    const config = getLocaleConfig(env);

    // Detect requested locale: explicit query param > cookie > Accept-Language > CF header
    const url = new URL(request.url);
    const requestedLocale =
      url.searchParams.get("locale") ??
      parseCookieLocale(request.headers.get("Cookie")) ??
      parseAcceptLanguage(request.headers.get("Accept-Language")) ??
      (request as any).cf?.timezone?.split("/")[0]?.toLowerCase() ?? // very rough
      config.defaultLocale;

    const resolvedLocale = resolveLocale(requestedLocale, config);

    // Attach to request context for downstream handlers
    const localeContext = { requestedLocale, resolvedLocale, config };

    // Example: return resolved locale info
    return new Response(
      JSON.stringify({
        requested: requestedLocale,
        resolved: resolvedLocale,
        supported: config.supportedLocales,
        default: config.defaultLocale,
      }),
      {
        headers: {
          "Content-Type": "application/json",
          "Content-Language": resolvedLocale,
          Vary: "Accept-Language",
        },
      },
    );
  },
};

function parseCookieLocale(cookieHeader: string | null): string | null {
  if (!cookieHeader) return null;
  const match = cookieHeader.match(/(?:^|;\s*)locale=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function parseAcceptLanguage(header: string | null): string | null {
  if (!header) return null;
  // Take the highest-quality tag
  return header
    .split(",")
    .map((part) => {
      const [tag, q] = part.trim().split(";q=");
      return { tag: tag.trim(), q: q ? parseFloat(q) : 1.0 };
    })
    .sort((a, b) => b.q - a.q)[0]?.tag ?? null;
}
```

---

## Anti-patterns

- **Putting locale lists in secrets** — `wrangler secret put` is for sensitive values
  (API keys, tokens); locale lists are not sensitive and belong in `[vars]` where they are
  visible in the dashboard and source-controlled in `wrangler.toml`.
- **Reading `env.SUPPORTED_LOCALES` inside every request** — string splitting and
  validation on the hot path is wasteful; parse once at module scope or on first request
  and cache.
- **Using environment names (`staging`, `production`) as locale signals** — environments
  control which config values are injected; locale resolution logic should be
  environment-agnostic.
- **Not validating DEFAULT_LOCALE is in SUPPORTED_LOCALES** — this creates a
  permanently unreachable default and silent failures in fallback resolution.

---

## Gotchas

- `wrangler.toml` `[vars]` values are always strings; parse integers (`parseInt`) and
  booleans (`=== "true"`) explicitly — there is no automatic coercion.
- Values set in `[vars]` are visible in the Cloudflare dashboard; do not put locale-tagged
  feature flags that reveal unreleased markets there.
- Module-scope caching (`cachedConfig`) persists for the lifetime of a Worker isolate
  (potentially hours); if you update `wrangler.toml` vars and redeploy, the old cache
  is cleared because the deploy creates new isolates.
- The `[env.production]` section in `wrangler.toml` overrides `[vars]` for the named
  environment; a bare `[vars]` block applies to the default (development) environment.

---

## Verification

```bash
# Check resolved locale for a staging deploy
curl "https://staging.my-app.workers.dev/?locale=pt-BR"
# Expect: {"requested":"pt-BR","resolved":"en","supported":["en","fr","de"],...}
# (pt-BR is not in staging SUPPORTED_LOCALES → falls back to "en")

# Production should support pt-BR
curl "https://my-app.workers.dev/?locale=pt-BR"
# Expect: {"requested":"pt-BR","resolved":"pt-BR","supported":[...],...}

# Verify vars are set correctly
wrangler whoami
wrangler deployments list
npx wrangler tail --env production | grep locale-config
```

---

## Related

- `locale-fallback-chain.md`
- `locale-fallback-strategies-2026.md`
- `locale-negotiation-accept-language.md`
- `locale-url-routing-workers-middleware.md`
- `workers-locale-context-service-bindings.md`

---

## Sources

- <https://developers.cloudflare.com/workers/wrangler/configuration/#environment-variables>
- <https://developers.cloudflare.com/workers/wrangler/environments/>
- <https://developers.cloudflare.com/workers/runtime-apis/bindings/variables-and-secrets/>
- <https://www.rfc-editor.org/rfc/rfc5646> (BCP-47 language tag syntax)
