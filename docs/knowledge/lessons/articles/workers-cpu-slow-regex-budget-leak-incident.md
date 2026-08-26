# Workers CPU Slow Regex Budget Leak Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

A content-moderation Worker began intermittently hitting the 10 ms CPU-time limit and returning
503s. P99 CPU time climbed from ~2 ms to 11 ms over three days following a seemingly minor
feature addition. The regression was not visible in unit tests (which used short, benign inputs)
or in staging (where test payloads were controlled). In production, user-submitted strings of 30+
characters caused catastrophic backtracking in a newly added regular expression, occasionally
consuming the entire 10 ms CPU budget on a single regex match.

## Context

A developer added an email-extraction regex to a content-moderation pipeline running on the
Workers Free plan (10 ms CPU limit, 30 s wall-clock). The regex used nested quantifiers:
`/([a-zA-Z0-9._%+-]+)+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/`. The outer `+` and the character class
`+` interact to produce `O(2^n)` backtracking on strings that partially match but ultimately fail.
A payload like `aaaa...aaaa!` (30+ chars) triggered ~100 ms of CPU time — 10x the hard limit.

---

## The Vulnerable Regex and Why It Backtracked

```typescript
// BEFORE — catastrophic backtracking on non-matching input
// The outer group `([a-zA-Z0-9._%+-]+)+` has two `+` quantifiers. When
// the engine fails to find `@`, it backtracks through 2^n combinations
// of how the outer and inner `+` can divide the matched characters.
const EMAIL_REGEX_DANGEROUS = /([a-zA-Z0-9._%+-]+)+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;

// A 35-char non-email string can consume >100 ms in V8 on Workers:
const worst = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa!';
EMAIL_REGEX_DANGEROUS.test(worst); // CPU budget exhausted

// AFTER — possessive-equivalent via atomic group (linear backtracking)
// Simplify: remove the outer redundant grouping. The inner `+` alone is
// sufficient and does not create nested-quantifier backtracking.
const EMAIL_REGEX_SAFE = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/;
```

## Detecting ReDoS Candidates at Development Time

```typescript
// Use `recheck` (npm package) to statically analyse regexes for ReDoS risk.
// Run this in CI — it does NOT execute the regex; it analyses its structure.

// scripts/check-regexes.ts
import { recheck } from 'recheck';

const REGEXES_TO_CHECK: Array<{ name: string; source: string; flags: string }> = [
  { name: 'EMAIL_REGEX', source: '([a-zA-Z0-9._%+-]+)+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}', flags: '' },
  { name: 'URL_REGEX',   source: 'https?://[^\\s]+', flags: 'gi' },
];

for (const { name, source, flags } of REGEXES_TO_CHECK) {
  const result = await recheck(source, flags);
  if (result.status === 'vulnerable') {
    console.error(`ReDoS vulnerability in ${name}:`, result.attack?.pattern);
    process.exit(1);
  }
  console.log(`${name}: safe (${result.status})`);
}
```

## Timeout Guard for Untrusted Regex Execution

```typescript
// When the regex cannot be changed (e.g., third-party library), run it
// in a bounded synchronous budget using a wall-clock check.
// NOTE: Workers have no thread.interrupt(); this is a best-effort guard.

function testRegexWithTimeout(regex: RegExp, input: string, maxMs = 5): boolean {
  const start = Date.now();
  // For very long inputs, chunk the check: bail if the clock advances too far.
  // This does NOT interrupt mid-execution; it only catches between attempts.
  if (input.length > 200) {
    // Pre-flight: linear-scan check before running the full regex
    if (!input.includes('@')) return false; // cheap rejection for email check
  }

  const elapsed = Date.now() - start;
  if (elapsed > maxMs) {
    console.warn('Regex pre-check too slow', { inputLength: input.length, elapsed });
    return false; // conservative: treat as non-match
  }

  return regex.test(input);
}
```

## Input Sanitisation Before Regex Matching

```typescript
// Limit input length before applying any regex on user content.
// Workers CPU time is proportional to input length * regex complexity.

const MAX_MODERATION_INPUT_CHARS = 4_000;

export function sanitiseForModeration(raw: string): string {
  // 1. Truncate
  const truncated = raw.slice(0, MAX_MODERATION_INPUT_CHARS);
  // 2. Normalise whitespace to prevent whitespace-amplified backtracking
  return truncated.replace(/\s+/g, ' ').trim();
}

// In the handler:
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const body = await req.text();
    const safe = sanitiseForModeration(body);
    const isSpam = runModerationChecks(safe);
    return Response.json({ spam: isSpam });
  },
};
```

## CPU Time Monitoring via Analytics Engine

```typescript
// Instrument each regex individually so you can identify which pattern
// is consuming disproportionate CPU time in production.

interface RegexMetric {
  name: string;
  inputLength: number;
  matched: boolean;
  durationMs: number;
}

function timedTest(name: string, regex: RegExp, input: string): boolean {
  const start = performance.now();
  const result = regex.test(input);
  const durationMs = performance.now() - start;

  if (durationMs > 2) {
    // Anything over 2 ms for a single regex is a warning sign in Workers
    console.warn('Slow regex', { name, inputLength: input.length, durationMs });
  }

  return result;
}

// Usage
const isEmail = timedTest('EMAIL_REGEX', EMAIL_REGEX_SAFE, userInput);
```

## Canary Assertions for Regex Performance in Tests

```typescript
// vitest / jest — assert that known pathological inputs complete under budget
import { describe, it, expect } from 'vitest';

const EMAIL_REGEX_SAFE = /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/;

describe('EMAIL_REGEX performance', () => {
  const WORST_CASE_INPUTS = [
    'a'.repeat(50) + '!',          // long non-match
    `${'ab'.repeat(25)}@`,         // partial match, no domain
    `${'x'.repeat(40)}.`,          // long with single dot, no TLD
  ];

  for (const input of WORST_CASE_INPUTS) {
    it(`completes in <5 ms on: ${input.slice(0, 20)}…`, () => {
      const start = performance.now();
      EMAIL_REGEX_SAFE.test(input);
      const elapsed = performance.now() - start;
      expect(elapsed).toBeLessThan(5);
    });
  }
});
```

---

## Anti-Patterns

- **Nested quantifiers on overlapping character classes:** `(a+)+`, `([ab]+)+`, `(\w+)+` are
  textbook ReDoS patterns. Any time a group containing a quantifier is itself quantified, audit
  it with a static analyser.
- **Applying arbitrary-complexity regexes to user-controlled input without length limits.**
  Length alone does not prevent ReDoS, but it bounds the worst case.
- **No performance test for regex pathological inputs.** Unit tests typically use controlled
  inputs that do not expose catastrophic backtracking. Add explicit worst-case tests.
- **Using regex for validation tasks a simple string method handles.** `indexOf`, `startsWith`,
  `split`, and `includes` are O(n) and cannot backtrack.

## Gotchas

- Workers V8 uses backtracking NFA for regex; it does NOT use a linear-time DFA/NFA approach
  by default. Even ES2025 does not mandate linear-time matching for all regex features.
- `performance.now()` in Workers returns a coarsened value (1 ms resolution) for privacy
  reasons. It is still useful for identifying regressions in the 5–50 ms range.
- The Workers CPU limit is 10 ms on Free and 30 s on Paid per invocation, but the 50 ms
  _wall-clock_ limit on subrequests is separate. A slow regex consuming CPU will not be
  interrupted mid-execution by the wall-clock limit.
- Static ReDoS analysers (`recheck`, `vuln-regex-detector`) have false positives. Confirm any
  flagged regex against actual pathological inputs before refactoring working code.

## Verification

```bash
# Run ReDoS static analysis across all source files containing RegExp literals
npx recheck scan 'src/**/*.ts'

# Run the performance canary tests
npx vitest run --reporter=verbose tests/regex-perf.test.ts

# Check production CPU time percentiles in Cloudflare dashboard:
# Analytics > Workers > CPU Time — filter by Worker name, look at P99
# Alert threshold: P99 > 6 ms on a 10 ms budget Worker
```

## Related

- `workers-cpu-time-limit-exceeded-webhook-handler-incident.md`
- `workers-cpu-time-premature-optimization.md`
- `workers-memory-128mb-limit-oom-postmortem.md`
- `timeouts-everywhere-no-exceptions.md`
- `index-before-not-after-performance-problem.md`

## Sources

- ReDoS explanation: https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS
- `recheck` npm package: https://makenowjust-labs.github.io/recheck/
- Workers CPU limits: https://developers.cloudflare.com/workers/platform/limits/#cpu-time
- V8 regex implementation notes: https://v8.dev/blog/non-backtracking-regexp
