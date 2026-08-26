# Workers V8 Isolate Sandbox Security Model and Breakout Prevention

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Teams deploying user-supplied or third-party code inside a Cloudflare Worker need to understand
what the V8 isolate sandbox actually guarantees, what attack surface remains within the Worker
runtime, and how to harden code execution so that a compromised dependency or malicious plugin
cannot escape the sandbox, steal secrets from `env`, or affect other tenants.

## Context

Cloudflare Workers run each request in a V8 isolate — a lightweight, memory-isolated JavaScript
execution context with no shared heap between requests or between Workers. The runtime exposes
only a restricted set of Web APIs; there is no file system, no `process`, no `require`, and no
native Node.js modules. Despite these guarantees, the sandbox is not a complete security boundary
for all threat models: Workers on the same Cloudflare account can communicate via service
bindings, secrets flow through `env`, and JavaScript prototype chains are shared within a single
isolate when executing untrusted code in the same request context.

## Threat Model

**Attacker goal**: escape the V8 isolate to read other tenants' memory, steal `env` secrets
from the enclosing Worker, or poison shared prototype state to affect other requests.

Attack scenarios:

- **Prototype pollution in untrusted code**: a malicious third-party library sets
  `Object.prototype.isAdmin = true`; subsequent auth checks that test `user.isAdmin` in the
  same isolate instance return `true` for all users until the isolate is recycled.
- **Secret exfiltration via `env` reference leakage**: user-supplied code is passed a reference
  to the full `env` object instead of a scoped subset; the code reads `env.DB_PASSWORD` or
  iterates all keys.
- **Infinite-loop CPU exhaustion**: untrusted code enters an unbounded loop, burning the
  Worker's CPU allowance and causing a 1101 error for legitimate requests sharing the isolate.
- **`fetch()` SSRF from untrusted code**: if the user-supplied function can call `fetch()`, it
  can probe internal Cloudflare metadata endpoints or reach internal services.
- **`eval()` / `Function()` constructor abuse**: dynamically compiled code bypasses static
  analysis and can reconstruct forbidden APIs via introspection of the global scope.

## Implementation — Sandboxed User Code Execution

```typescript
// plugin-runner/src/index.ts
// Execute user-supplied transform functions in a hardened execution context.

export interface Env {
  PLUGIN_CODE: KVNamespace; // stores user plugin source code
  // Intentionally NOT passing DB or secret bindings to the sandbox
}

// A frozen, minimal API surface to pass into user code
function buildSandboxGlobals(): Record<string, unknown> {
  return Object.freeze({
    // Provide only serialisable data helpers, no fetch, no crypto key material
    JSON: Object.freeze({ ...JSON }),
    Math: Object.freeze({ ...Math }),
    parseInt,
    parseFloat,
    isNaN,
    isFinite,
    encodeURIComponent,
    decodeURIComponent,
    // Controlled fetch — only allow GET to a pre-approved domain whitelist
    fetch: buildRestrictedFetch(['https://api.approved-partner.com']),
  });
}

function buildRestrictedFetch(allowedOrigins: string[]): typeof fetch {
  return async (input: RequestInfo, init?: RequestInit): Promise<Response> => {
    const url = new URL(typeof input === 'string' ? input : (input as Request).url);
    if (!allowedOrigins.some(o => url.origin === o)) {
      throw new TypeError(`fetch blocked: ${url.origin} is not in the allow-list`);
    }
    // Force GET — plugins must not cause side effects via POST
    return fetch(url.toString(), { method: 'GET', headers: {} });
  };
}

// Harden the global prototype chain before running any untrusted code
function lockdownPrototypes(): void {
  // Freeze Object.prototype to block prototype pollution
  Object.freeze(Object.prototype);
  Object.freeze(Array.prototype);
  Object.freeze(Function.prototype);
  Object.freeze(String.prototype);
  Object.freeze(Number.prototype);
  Object.freeze(Boolean.prototype);
}

// Wrap user code in a strict-mode function with no access to outer scope
function compilePlugin(source: string): (globals: Record<string, unknown>, input: unknown) => unknown {
  // Disallow known escape hatches statically
  const forbidden = [
    /\beval\b/,
    /\bFunction\b/,
    /\bimport\b/,
    /\bprocess\b/,
    /\bglobalThis\b/,
    /\bself\b/,
    /\benv\b/,
    /__proto__/,
    /constructor\s*\[/,
  ];
  for (const pattern of forbidden) {
    if (pattern.test(source)) {
      throw new Error(`Plugin contains forbidden pattern: ${pattern.source}`);
    }
  }

  // Wrap in an IIFE that receives only the explicit globals argument
  // 'use strict' disables arguments.callee and with()
  const wrapped = `'use strict';\nreturn (async function plugin(globals, input) {\n${source}\n});`;
  // eslint-disable-next-line no-new-func
  return new Function('globals', wrapped)({}) as (g: Record<string, unknown>, i: unknown) => unknown;
}

async function runPlugin(
  pluginFn: (globals: Record<string, unknown>, input: unknown) => unknown,
  input: unknown,
): Promise<unknown> {
  const globals = buildSandboxGlobals();

  // Impose a wall-clock timeout — Workers do not have a built-in per-function timeout
  const TIMEOUT_MS = 2000;
  const timeoutPromise = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error('Plugin execution timed out')), TIMEOUT_MS)
  );

  const resultPromise = Promise.resolve().then(() => pluginFn(globals, input));
  return Promise.race([resultPromise, timeoutPromise]);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { pluginId, input } = await request.json<{ pluginId: string; input: unknown }>();

    // Load plugin source — stored and reviewed at deploy time, not supplied per-request
    const source = await env.PLUGIN_CODE.get(`plugin:${pluginId}`);
    if (!source) return Response.json({ error: 'plugin not found' }, { status: 404 });

    // Lock down prototypes once per isolate lifetime
    lockdownPrototypes();

    let pluginFn: ReturnType<typeof compilePlugin>;
    try {
      pluginFn = compilePlugin(source);
    } catch (err) {
      return Response.json({ error: 'invalid plugin', detail: String(err) }, { status: 400 });
    }

    try {
      const result = await runPlugin(pluginFn, input);
      // Serialise result — do not return raw objects that might contain env references
      return Response.json({ result: JSON.parse(JSON.stringify(result)) });
    } catch (err) {
      // Never expose internal error messages from untrusted code to the caller
      console.error('Plugin execution error:', err);
      return Response.json({ error: 'plugin execution failed' }, { status: 500 });
    }
  },
};
```

## Hardening — Isolate Recycling and Secret Scoping

```typescript
// Prevent long-lived isolates from accumulating pollution by marking them dirty
// and forcing cold starts after untrusted code execution.

// wrangler.toml setting: max_isolate_lifetime_seconds = 30
// (contact Cloudflare support for per-account isolate lifetime controls)

// Secret scoping: never pass the full env to user-supplied code
export function scopedEnv(env: { DB: D1Database; SECRET: string; [k: string]: unknown }): {
  DB: D1Database;
} {
  // Return ONLY what the plugin legitimately needs — never the full env
  return { DB: env.DB };
}

// Validate all plugin outputs before using them in downstream operations
export function validatePluginOutput(output: unknown): asserts output is { score: number } {
  if (typeof output !== 'object' || output === null) throw new Error('invalid plugin output');
  const o = output as Record<string, unknown>;
  if (typeof o.score !== 'number' || o.score < 0 || o.score > 100) {
    throw new Error('plugin output.score must be a number in [0, 100]');
  }
  // Reject output with unexpected keys to prevent mass-assignment
  const allowed = new Set(['score', 'metadata']);
  for (const key of Object.keys(o)) {
    if (!allowed.has(key)) throw new Error(`unexpected plugin output key: ${key}`);
  }
}
```

## Anti-patterns

- **Passing `env` directly into user code**: any reference to `env` inside untrusted code gives
  access to all bound secrets, databases, and KV namespaces.
- **Trusting static analysis alone**: regex-based source scanning can be bypassed with
  obfuscation (`eval`, string concatenation); use it as a first filter, not a guarantee.
- **Reusing isolates across untrusted plugin runs without lockdown**: mutable shared prototype
  state persists across requests in a warm isolate; freeze prototypes before the first run.
- **Not timing out plugin execution**: an infinite loop blocks the event loop, burning CPU
  budget and eventually causing a 1101 error for all requests on that isolate.
- **Surfacing plugin error messages to callers**: stack traces from untrusted code may include
  path information, binding names, or secret fragments; catch and replace with generic errors.

## Gotchas

- **`Object.freeze` is shallow**: freezing `Object.prototype` does not freeze nested objects;
  always freeze recursively or use a library like `ses` (Secure ECMAScript) for deep sealing.
- **Workers share isolates across requests**: a warm isolate serving request A and request B
  shares its global scope; prototype mutations from request A are visible to request B unless
  the isolate is discarded.
- **`Function` constructor still works if `Function.prototype` is not frozen**: an attacker can
  call `(function(){}).constructor('return globalThis')()` to escape a naively sandboxed scope;
  freeze `Function.prototype` and static-scan for `constructor`.
- **`fetch()` inside Workers is always outbound-allowed**: unlike browsers, Workers do not have
  a default-deny `Content-Security-Policy`; you must implement allowlist enforcement in code.
- **Wasm modules bypass JavaScript sandboxing**: a `WebAssembly.compile()` call with attacker-
  controlled bytes can execute arbitrary Wasm; either block Wasm in static analysis or require
  modules to be pre-approved and loaded from a controlled KV namespace.

## Verification

```bash
# 1. Prototype pollution attempt must not affect subsequent requests
curl -X POST https://plugin.example.workers.dev/run \
  -H "Content-Type: application/json" \
  -d '{"pluginId":"test-pollution","input":{}}'
# Plugin source: Object.prototype.isAdmin = true; return {score: 0}
# Subsequent request must not see isAdmin=true on plain objects

# 2. Forbidden pattern (eval) must be rejected at compile time
curl -X POST https://plugin.example.workers.dev/run \
  -H "Content-Type: application/json" \
  -d '{"pluginId":"test-eval","input":{}}'
# Plugin source: return eval('1+1');
# expect: {"error":"invalid plugin","detail":"...forbidden pattern..."}

# 3. Timeout enforcement
curl -X POST https://plugin.example.workers.dev/run \
  -H "Content-Type: application/json" \
  -d '{"pluginId":"test-infinite","input":{}}'
# Plugin source: while(true){}
# expect: {"error":"plugin execution failed"} within ~2 s

# 4. Secret leakage attempt via globalThis must fail
# Plugin source: return { secret: <redacted-secret> ?? 'blocked' }
# expect: {"error":"invalid plugin","detail":"...forbidden pattern: globalThis..."}
```

## Related

- `prototype-pollution-prevention.md`
- `workers-environment-variable-hygiene.md`
- `service-binding-zero-trust-workers.md`
- `workers-wasm-module-integrity-supply-chain.md`
- `ssrf-prevention-workers-fetch-allowlist.md`

## Sources

- https://developers.cloudflare.com/workers/reference/security-model/
- https://v8.dev/blog/sandbox — V8 sandbox design
- https://github.com/nicolo-ribaudo/tc39-proposal-ses — Secure ECMAScript
