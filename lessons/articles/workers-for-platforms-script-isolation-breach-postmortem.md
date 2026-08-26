# Workers for Platforms Script Isolation Breach Postmortem

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

A SaaS platform using Cloudflare Workers for Platforms (WfP) discovered that a malicious customer script uploaded to a dispatch namespace was able to read environment variable values belonging to a sibling customer script executing in the same dispatch namespace during the same time window. The breach was exploited to exfiltrate API keys stored in the platform operator's Worker environment (not the customer Worker's environment). The root cause was a misconfigured outbound Worker that inadvertently forwarded the platform's `env` bindings to customer scripts via a request context object that should have been scrubbed before dispatch.

## Context

Workers for Platforms allows a SaaS operator to accept user-uploaded JavaScript (or WASM) and execute it inside Cloudflare's infrastructure. Each customer script is isolated in its own V8 isolate. The dispatch namespace routes incoming requests to the correct customer Worker by `script_name`. The isolation guarantee is at the V8 level — customer scripts cannot directly access each other's memory. However, the isolation does **not** protect against:

1. The operator's dispatch Worker (the "user Worker gateway") forwarding platform-level secrets as HTTP headers or request body fields to the customer Worker.
2. Customer scripts using `fetch()` to reach operator-internal endpoints that are accessible from Workers (e.g., internal KV namespaces not protected by binding-level access control).
3. Serialized context objects (e.g., a `RequestContext` class instance) being passed to customer scripts as constructor arguments or via `globalThis`.

The specific failure in this incident was the operator's dispatch Worker serializing `env` into a JSON body field for a "context initialization" pattern borrowed from a non-WfP codebase, where the pattern was safe because scripts were internal.

---

## 1. The Vulnerable Pattern (Do Not Use)

```typescript
// DANGEROUS: dispatch Worker leaking platform env to customer script
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const scriptName = request.headers.get("X-Customer-Id");
    if (!scriptName) return new Response("Missing customer ID", { status: 400 });

    const dispatcher = env.DISPATCH_NAMESPACE.get(scriptName);

    // BUG: serializing `env` and passing it to the customer script
    const enrichedRequest = new Request(request, {
      body: JSON.stringify({
        originalBody: await request.text(),
        // This leaks ALL platform env vars — KV namespace IDs, API keys, etc.
        platformContext: { ...env },
      }),
      method: "POST",
      headers: { ...Object.fromEntries(request.headers), "Content-Type": "application/json" },
    });

    return dispatcher.fetch(enrichedRequest);
  },
} satisfies ExportedHandler<Env>;
```

---

## 2. Safe Dispatch Pattern

```typescript
// SAFE: dispatch Worker passes only an explicit, scrubbed context
interface CustomerContext {
  customerId: string;
  plan: "free" | "pro" | "enterprise";
  rateLimitTier: number;
  // Never include: API keys, KV namespace IDs, internal URLs, credentials
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const customerId = request.headers.get("X-Customer-Id");
    if (!customerId) return new Response("Missing customer ID", { status: 400 });

    // Validate customer exists and is authorized
    const customerMeta = await env.CUSTOMERS_KV.get<CustomerContext>(customerId, "json");
    if (!customerMeta) return new Response("Unknown customer", { status: 403 });

    const dispatcher = env.DISPATCH_NAMESPACE.get(customerId, {
      outbound: {
        // Outbound Worker handles egress filtering — defined separately
        worker: { service: env.OUTBOUND_WORKER },
        params: [
          // Only pass safe, customer-scoped context
          { name: "customerId", value: customerId },
          { name: "plan", value: customerMeta.plan },
        ],
      },
    });

    // Strip operator-internal headers before forwarding
    const safeHeaders = new Headers(request.headers);
    const INTERNAL_HEADERS = [
      "cf-connecting-ip", // expose only if explicitly needed
      "x-internal-token",
      "x-platform-secret",
    ];
    for (const h of INTERNAL_HEADERS) safeHeaders.delete(h);

    const safeRequest = new Request(request, { headers: safeHeaders });
    return dispatcher.fetch(safeRequest);
  },
} satisfies ExportedHandler<Env>;
```

---

## 3. Outbound Worker: Egress Filtering

The outbound Worker intercepts all `fetch()` calls made by customer scripts and can block calls to internal infrastructure.

```typescript
// outbound-worker/src/index.ts
// Declared as the outbound Worker in the dispatch namespace config

const BLOCKED_HOSTS = [
  "internal.example.com",
  "metadata.google.internal", // cloud metadata endpoints
  "169.254.169.254",          // AWS/GCP IMDS
  "100.100.100.200",          // Alibaba Cloud IMDS
];

const BLOCKED_PREFIXES = [
  "https://api.cloudflare.com", // operators must not allow customer scripts to call CF API
];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Block SSRF targets
    for (const blocked of BLOCKED_HOSTS) {
      if (url.hostname === blocked || url.hostname.endsWith(`.${blocked}`)) {
        console.error(`[outbound] Blocked request to ${url.hostname} from customer script`);
        return new Response("Blocked by platform policy", { status: 403 });
      }
    }

    for (const prefix of BLOCKED_PREFIXES) {
      if (request.url.startsWith(prefix)) {
        console.error(`[outbound] Blocked internal API call: ${request.url}`);
        return new Response("Blocked by platform policy", { status: 403 });
      }
    }

    // Strip any operator-specific headers that customer script may have injected
    const cleanHeaders = new Headers(request.headers);
    cleanHeaders.delete("x-internal-token");
    cleanHeaders.delete("authorization"); // prevent credential injection if operator adds auth at dispatch layer

    return fetch(new Request(request, { headers: cleanHeaders }));
  },
} satisfies ExportedHandler<Env>;
```

---

## 4. Audit Logging for Customer Script Egress

Every outbound fetch from a customer script should be logged with the customer ID for forensic purposes.

```typescript
// outbound-worker/src/index.ts — enhanced with logging
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const customerId = request.headers.get("X-Dispatch-Customer-Id") ?? "unknown";
    const targetHost = new URL(request.url).hostname;

    const isBlocked = BLOCKED_HOSTS.some((h) => targetHost === h || targetHost.endsWith(`.${h}`));

    ctx.waitUntil(
      env.ANALYTICS.writeDataPoint({
        blobs: [customerId, request.method, targetHost, isBlocked ? "blocked" : "allowed"],
        doubles: [Date.now()],
        indexes: [customerId],
      })
    );

    if (isBlocked) return new Response("Blocked", { status: 403 });

    return fetch(request);
  },
} satisfies ExportedHandler<Env>;
```

---

## 5. Scanning Uploaded Scripts for Dangerous Patterns

Before accepting a customer script into the dispatch namespace, run a static analysis pass to reject obviously dangerous patterns.

```typescript
// upload-validator/src/index.ts
const DANGEROUS_PATTERNS = [
  /globalThis\s*\.\s*env/g,           // attempt to read platform globals
  /process\s*\.\s*env/g,              // Node.js env (not available in Workers, but signals intent)
  /\beval\s*\(/g,                      // dynamic code execution
  /new\s+Function\s*\(/g,             // dynamic code execution
  /WebAssembly\s*\.\s*instantiateStreaming/g, // WASM from external URL
  /importScripts\s*\(/g,              // external script import
];

export function validateCustomerScript(code: string): { safe: boolean; violations: string[] } {
  const violations: string[] = [];

  for (const pattern of DANGEROUS_PATTERNS) {
    const matches = code.match(pattern);
    if (matches) {
      violations.push(`Forbidden pattern detected: ${pattern.source} (${matches.length} occurrences)`);
    }
  }

  return { safe: violations.length === 0, violations };
}
```

---

## Anti-patterns

- Passing `env` (or any subset of it) to customer scripts as a serialized object, constructor argument, or header — `env` contains binding handles that, while not directly serializable to raw secrets, expose namespace IDs that can be used to construct internal API calls.
- Using the dispatch Worker's own `fetch` credentials for downstream calls on behalf of customer scripts — customer scripts that can influence the URL or headers of these fetches can pivot to internal services.
- Skipping the outbound Worker in development and only adding it in production — security controls need to be present in all environments to be tested.
- Trusting customer-provided script names (`script_name`) without validation against an allowlist — an attacker can enumerate dispatch namespace script names by trying common names.
- Logging the full request body of customer script `fetch()` calls to a shared log stream — this can leak customer data between tenants via the log pipeline.

## Gotchas

- `DISPATCH_NAMESPACE.get(scriptName)` does not validate that `scriptName` exists; it returns a dispatcher stub that fails at runtime with a non-obvious error. Validate script existence from your customer DB before dispatching.
- The outbound Worker receives requests from **all** customer scripts in the namespace, not just the one you think is active. The `X-Dispatch-Customer-Id` header is set by the platform (dispatch Worker), not by the customer script — treat it as authoritative only if you set it yourself.
- Workers for Platforms dispatch namespace scripts have their own `cpu_ms` and memory limits separate from the dispatch Worker. A rogue customer script that spins the CPU will not affect other customers' isolates, but will affect billing.
- The `outbound` configuration in `DISPATCH_NAMESPACE.get()` is set at dispatch time per-request, not globally for the namespace — ensure the outbound Worker is specified on every `get()` call, not just the first one.
- Static analysis of customer scripts catches obvious bad patterns but cannot prevent all SSRF or data exfiltration attempts. Defense in depth via outbound Worker filtering is mandatory.

## Verification

```bash
# List scripts in the dispatch namespace
wrangler dispatch-namespace list-scripts --namespace my-namespace

# Verify outbound Worker is configured for the namespace
wrangler dispatch-namespace get --namespace my-namespace

# Test that outbound Worker blocks internal calls
# Upload a test script that attempts to fetch an internal URL and confirm 403

# Review Analytics Engine for any suspicious egress patterns
# Filter by customerId and look for calls to 169.254.x.x, metadata endpoints, etc.
wrangler analytics-engine query \
  "SELECT blob1 AS customer, blob3 AS host, count() AS hits \
   FROM egress_log \
   WHERE blob4 = 'blocked' \
   GROUP BY customer, host ORDER BY hits DESC LIMIT 20"
```

## Related

- `workers-for-platforms-dispatch-namespace-quota-exhaustion.md`
- `insider-threat-is-real.md`
- `security-review-before-not-after.md`
- `pen-test-surprises-are-expensive.md`
- `dont-log-pii-in-production.md`
- `rate-limit-before-you-need-it.md`

## Sources

- Cloudflare Workers for Platforms documentation: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/
- Dispatch namespaces: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/reference/how-workers-for-platforms-works/
- Outbound Workers: https://developers.cloudflare.com/cloudflare-for-platforms/workers-for-platforms/configuration/outbound-workers/
- OWASP SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
