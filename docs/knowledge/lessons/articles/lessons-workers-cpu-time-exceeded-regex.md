# Workers CPU Time Exceeded — Catastrophic Regex Backtracking

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker handling user-submitted search queries began returning `Error 1101: Worker threw exception` intermittently. Logs showed `CPU Time limit exceeded (50ms)` on requests that contained certain search strings. The Worker had been processing regex-based pattern matching against a catalog index.

---

## Context

The Worker accepted a user-provided search pattern, compiled it into a `RegExp`, and ran it against a list of product slugs using `RegExp.exec()` in a loop. During normal operation this was fast. However, users discovered (accidentally or otherwise) that patterns like `(a+)+b` applied to long non-matching strings triggered catastrophic backtracking inside V8's default regex engine. Cloudflare Workers enforce a hard 50 ms CPU-time wall; once hit the Worker is killed and a 1101 is returned to the client. The Worker had no input sanitisation, no timeout, and no allowlist for pattern complexity.

---

## Root Cause

V8's default `RegExp` engine uses a backtracking NFA that can exhibit exponential time complexity on certain patterns. The canonical bad patterns are nested quantifiers — `(a+)+`, `(a|aa)+`, `([a-zA-Z]+)*` — applied to strings that are long and do not match. Each failed match attempt may generate an exponential number of partial matches before giving up.

```typescript
// BAD — user input compiled directly, no guards
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const raw = url.searchParams.get('pattern') ?? '';

    // Compiling user input verbatim is dangerous
    let re: RegExp;
    try {
      re = new RegExp(raw, 'i');
    } catch {
      return new Response('invalid regex', { status: 400 });
    }

    const catalog = await getCatalog(); // ~5000 slugs
    const matches = catalog.filter(slug => re.exec(slug) !== null);
    return Response.json(matches);
  },
};
```

With a pattern like `(s+)+!` against a 60-character slug that contains no `!`, the engine backtracks through every possible split of the `s` characters before giving up — often millions of partial states, burning far more than 50 ms of CPU time.

---

## Fix

### 1. Use the V8 linear (RE2-compatible) flag

V8 ships an experimental `linear` flag that guarantees O(n) matching time by forbidding constructs that enable backtracking. It rejects patterns that cannot be evaluated linearly.

```typescript
function compileLinear(raw: string, flags = 'i'): RegExp | null {
  try {
    // 'l' (linear) flag: V8 only, available in Workers runtime >= 2024-09-02
    return new RegExp(raw, flags + 'l');
  } catch {
    // Pattern is either syntactically invalid or uses backtracking constructs
    return null;
  }
}
```

### 2. Wrap exec in an AbortController-backed deadline

For runtimes where the linear flag is unavailable or where you need belt-and-suspenders protection:

```typescript
async function execWithDeadline(
  re: RegExp,
  input: string,
  timeoutMs = 5,
): Promise<RegExpExecArray | null> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('regex timeout')), timeoutMs);
    try {
      resolve(re.exec(input));
    } catch (err) {
      reject(err);
    } finally {
      clearTimeout(timer);
    }
  });
}
```

> Note: because Workers JavaScript is single-threaded, a `setTimeout` race only works if `re.exec()` yields — which a synchronously spinning backtracker will not. The only truly reliable options are the `linear` flag or running the match in a subworker via the Sandbox API.

### 3. Pattern allowlist / validation

```typescript
// Reject known-dangerous constructs before compiling
const DANGEROUS = [
  /\(.*\+.*\)\+/, // (x+)+
  /\(.*\|.*\)\*/, // (x|y)*
  /\[.*\]\*.*\+/, // [a-z]*+
];

function isSafePattern(raw: string): boolean {
  for (const guard of DANGEROUS) {
    if (guard.test(raw)) return false;
  }
  // Also cap length
  return raw.length <= 120;
}

// GOOD — full guard stack
export default {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const raw = url.searchParams.get('pattern') ?? '';

    if (!isSafePattern(raw)) {
      return new Response('pattern rejected', { status: 422 });
    }

    const re = compileLinear(raw);
    if (!re) {
      return new Response('pattern uses unsupported constructs', { status: 422 });
    }

    const catalog = await getCatalog();
    const matches = catalog.filter(slug => re.exec(slug) !== null);
    return Response.json(matches);
  },
};
```

---

## Prevention / Detection

```typescript
// Unit test: verify the linear flag rejects catastrophic patterns
import { describe, it, expect } from 'vitest';

describe('compileLinear', () => {
  it('rejects nested quantifiers', () => {
    expect(compileLinear('(a+)+b')).toBeNull();
    expect(compileLinear('(a|aa)+')).toBeNull();
  });

  it('accepts simple patterns', () => {
    expect(compileLinear('hello.*world')).toBeInstanceOf(RegExp);
  });
});
```

```bash
# Canary: hit the endpoint with a known catastrophic pattern and verify 422, not 1101
curl -w '%{http_code}' -o /dev/null -s \
  'https://api.example.com/search?pattern=(s%2B)%2B!'
# Expected: 422
```

---

## Anti-patterns

- **Compiling user input verbatim** — any user can supply a ReDoS pattern; always validate or use the linear engine.
- **Relying on the 50 ms wall as a safety net** — by the time the limit fires the Worker is dead and the user got a 1101; the limit is an emergency brake, not a feature.
- **Static analysis only** — dangerous patterns can be dynamically constructed; runtime guards are mandatory.

---

## Gotchas

- The `l` (linear) flag is V8-specific and not part of the ECMAScript standard. It may be absent in older Workers compatibility dates — pin `compatibility_date` to `2024-09-02` or later.
- Some legitimate patterns (look-aheads, backreferences) are also rejected by the linear engine. Communicate this limitation to users.
- CPU time in Workers is measured differently from wall-clock time. A `setTimeout` race does not protect against synchronous CPU spin.

---

## Verification

```bash
# 1. Deploy the fixed Worker
wrangler deploy

# 2. Confirm safe patterns still work
curl -s 'https://api.example.com/search?pattern=guitar.*case' | jq length

# 3. Confirm catastrophic patterns are blocked
curl -o /dev/null -w '%{http_code}' -s \
  'https://api.example.com/search?pattern=(g%2B)%2Bz'
# => 422

# 4. Check Worker analytics for CPU time p99
wrangler tail --format=json | jq '.cpuTime'
```

---

## Related

- `lessons-workers-fetch-timeout-no-deadline.md`

---

## Sources

- OWASP ReDoS — https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS
- V8 Experimental RegExp Linear Flag — https://v8.dev/blog/non-backtracking-regexp
- Cloudflare Workers Limits — https://developers.cloudflare.com/workers/platform/limits/
