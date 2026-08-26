# Workers Compatibility Flags Runtime Behavior

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker behaves differently from local `wrangler dev` versus production, or you upgrade `compatibility_date` and observe breakage in `fetch`, `streams`, `FormData`, or `crypto` behavior. You need to understand which compatibility flags are active, what runtime behavior they change, and how to opt in or opt out of specific flags without changing the date.

## Context

Cloudflare gates breaking runtime changes behind `compatibility_date` — a date in wrangler.toml that opts the Worker into all flags enabled by that date. Individual flags can be enabled earlier (`compatibility_flags = ["flag_name"]`) or disabled even if the date implies them (`compatibility_flags = ["disable:flag_name"]` syntax, or the corresponding disable flag). Flags govern behaviors in fetch, streams, FormData, crypto, global scope, and Node.js compatibility. Understanding the flag system is critical when debugging cross-environment differences.

## Reading Active Flags at Runtime

```typescript
// Workers does not expose a runtime API to enumerate active flags,
// but you can probe behavior to infer which flags are in effect.

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const diagnostics: Record<string, boolean> = {};

    // Probe: streams_enable_constructors — ReadableStream accepts start callback
    try {
      const rs = new ReadableStream({ start(c) { c.close(); } });
      diagnostics["streams_enable_constructors"] = true;
    } catch {
      diagnostics["streams_enable_constructors"] = false;
    }

    // Probe: formdata_parser_supports_files — File objects preserved in FormData
    const fd = new FormData();
    fd.set("f", new File(["x"], "x.txt"));
    diagnostics["formdata_parser_supports_files"] = fd.get("f") instanceof File;

    // Probe: nodejs_compat — Buffer available in global scope
    diagnostics["nodejs_compat"] = typeof (globalThis as Record<string, unknown>)["Buffer"] !== "undefined";

    return Response.json(diagnostics);
  },
} satisfies ExportedHandler<Env>;

interface Env {}
```

## Explicitly Enabling Flags Before Their Date

```toml
# wrangler.toml — pin an older date but opt into specific new behaviors
name = "my-worker"
compatibility_date = "2024-09-23"

# Enable specific flags ahead of their scheduled date
compatibility_flags = [
  "nodejs_compat",                   # Node.js Buffer, process, path, etc.
  "streams_enable_constructors",     # WHATWG Streams constructors
  "formdata_parser_supports_files",  # File objects in FormData
  "global_navigator",                # navigator.userAgent in global scope
  "fetch_refuses_unknown_protocols", # fetch() throws on non-http(s) URLs
]
```

## Disabling a Flag Implied by the Compatibility Date

```toml
# wrangler.toml — use a recent date but revert one breaking behavior
name = "my-worker"
compatibility_date = "2025-11-01"

# This date enables `no_global_navigator_no_op` which removes navigator stubs;
# if a dependency relies on the stub, disable the new behavior explicitly.
compatibility_flags = [
  "disable:global_navigator",
]
```

## Node.js Compat Flag — What It Enables

```typescript
// With nodejs_compat flag active, these Node.js APIs are available in scope:
import { Buffer } from "node:buffer";
import { createHash, randomBytes } from "node:crypto";
import path from "node:path";
import { EventEmitter } from "node:events";

export default {
  async fetch(): Promise<Response> {
    const hash = createHash("sha256").update("hello").digest("hex");
    const buf = Buffer.from("cloudflare", "utf8");
    const dir = path.dirname("/static/assets/file.js");

    return Response.json({ hash, hex: buf.toString("hex"), dir });
  },
} satisfies ExportedHandler;
```

## Fetch Behavior Flags

```typescript
// fetch_refuses_unknown_protocols: fetch("ftp://...") throws TypeError
// Without this flag it silently fails or returns a network error.

// Probe this at startup to fail fast if a dependency calls non-HTTP fetch
const PROBE_UNKNOWN_PROTOCOL = async (): Promise<boolean> => {
  try {
    await fetch("data:text/plain,test");
    return false; // flag not active; fetch silently handled it
  } catch (e) {
    return e instanceof TypeError; // flag active; TypeError thrown
  }
};

// http_headers_getsetcookie: Headers.getSetCookie() returns string[]
// Active since 2023-03-01; if you need the old single-value behavior,
// do not upgrade past that date or use disable flag.
function getSetCookies(headers: Headers): string[] {
  // Polyfill for environments where flag may not be active
  if (typeof headers.getSetCookie === "function") {
    return headers.getSetCookie();
  }
  return headers.get("set-cookie")?.split(", ") ?? [];
}
```

## Using Flags in Vitest Worker Environment

```typescript
// vitest.config.ts — mirror production flags in tests
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        // Vitest picks up compatibility_date and compatibility_flags from wrangler.toml
        // Override here only if testing a specific flag transition:
        miniflare: {
          compatibilityDate: "2025-11-01",
          compatibilityFlags: ["nodejs_compat", "streams_enable_constructors"],
        },
      },
    },
  },
});
```

## Anti-patterns

- Relying on `compatibility_date` alone to gate flag behavior without knowing which flags that date activates — check the Cloudflare changelog for each date.
- Using `nodejs_compat` as a blanket fix for missing globals without checking if only `nodejs_compat_v2` is needed — v2 adds additional modules and has different `process.env` behavior.
- Disabling flags with comments in wrangler.toml instead of the `disable:` prefix — wrangler only respects the `disable:` prefix form.
- Testing locally without matching `compatibility_flags` to production — `wrangler dev` defaults apply if wrangler.toml is missing flags, causing environment drift.

## Gotchas

- `nodejs_compat` and `nodejs_compat_v2` are mutually exclusive; enabling both causes a wrangler validation error.
- Some flags cannot be disabled after a certain `compatibility_date` — Cloudflare marks them as "locked"; attempting to disable a locked flag is a no-op with a wrangler warning.
- The `export_commonjs_namespace` flag affects how CommonJS modules interop with ES modules; enabling it changes what `module.exports` exposes to `import` statements.
- Flags set in the Cloudflare dashboard override wrangler.toml flags for deployed Workers — always verify the effective flag set in the dashboard under Workers > Settings > Compatibility.
- `wrangler dev --remote` uses the same flags as production; `wrangler dev` (local) uses Miniflare which may not implement all flags identically.

## Verification

```bash
# See all flags introduced by a compatibility date
curl -sS "https://developers.cloudflare.com/workers/configuration/compatibility-dates/changelog/" \
  | grep -A2 "2025-"

# Check the deployed Worker's active compatibility date and flags in the dashboard
wrangler deployments list --name my-worker

# Validate wrangler.toml flags syntax before deploy
wrangler deploy --dry-run --outdir /tmp/worker-dist
```

## Related

- `workers-compatibility-date-upgrade-governance.md` — upgrade workflow and governance for compatibility dates
- `workers-nodejs-compatibility.md` — Node.js compat flag in depth
- `workers-vitest-pool-integration-testing.md` — matching flags in Vitest
- `workers-best-practices.md` — wrangler.toml baseline configuration
- `dynamic-workers-capability-and-cost-boundaries.md` — tier limits affected by flags

## Sources

- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/flags/
- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- https://developers.cloudflare.com/workers/testing/vitest-integration/configuration/
