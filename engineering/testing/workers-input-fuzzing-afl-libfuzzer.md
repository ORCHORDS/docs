# Fuzz Testing Cloudflare Workers Input Parsing with AFL/LibFuzzer Patterns

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your Cloudflare Worker parses untrusted input in several places: JSON bodies, URL query strings,
JWT payloads, binary MessagePack from a mobile SDK, and multipart form uploads. Unit tests cover
known edge cases, but a malformed MessagePack packet with a deeply-nested structure causes an
unhandled exception that returns a 500 to a real user. You want to feed the input-parsing code a
stream of mutated inputs — automatically — to discover crashes, hangs, and assertion failures
before attackers do.

## Context

True native AFL/LibFuzzer cannot run inside the V8 isolate that hosts Cloudflare Workers.
However, the **fuzzing pattern** — mutation-based corpus iteration, coverage feedback, crash
triage — can be applied to Worker input-parsing logic using:

1. **`@jazzer.js/fuzzer`** (Jazzer.js) — a Node.js LibFuzzer port that runs JavaScript fuzz
   targets directly. Since Workers code is TypeScript compiled to standard JS, you extract the
   parsing logic into a shared package, fuzz it in Node, then deploy the same code to the Worker.

2. **Offline corpus-based property tests** — when a full fuzzer is impractical in CI, use
   `fast-check` with a saved corpus of previously discovered interesting inputs (seeds), giving
   structure-aware mutation on top of a fixed seed set.

3. **`wrangler dev` + AFL-style input feeding** — for end-to-end fuzzing, feed mutated HTTP
   requests to a locally-running Worker via `curl` loops driven by `radamsa` (a general-purpose
   mutator).

This article covers all three approaches and explains when to use each.

---

## Approach 1: Jazzer.js Fuzz Target for Shared Parsing Logic

Extract the parsing logic into a shared workspace package so it can be tested both by the fuzz
runner (Node) and by the Worker (V8 isolate).

### Extracting the parser

```ts
// packages/parsers/src/message-pack.ts
import { decode } from '@msgpack/msgpack';

export interface ParseResult {
  ok: true;
  data: unknown;
} | {
  ok: false;
  error: string;
}

/**
 * Safely parse a MessagePack buffer. Returns a ParseResult — never throws.
 * Enforces a max nesting depth to prevent stack overflow from crafted payloads.
 */
export function parseMessagePack(buffer: Uint8Array): ParseResult {
  try {
    const data = decode(buffer, { maxStrLength: 65_536, maxBinLength: 1_048_576 });
    if (!isWithinDepthLimit(data, 20)) {
      return { ok: false, error: 'max nesting depth exceeded' };
    }
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

function isWithinDepthLimit(value: unknown, remaining: number): boolean {
  if (remaining <= 0) return false;
  if (Array.isArray(value)) {
    return value.every(v => isWithinDepthLimit(v, remaining - 1));
  }
  if (value !== null && typeof value === 'object') {
    return Object.values(value as object).every(v => isWithinDepthLimit(v, remaining - 1));
  }
  return true;
}
```

### Jazzer.js fuzz target

```ts
// packages/parsers/fuzz/message-pack.fuzz.ts
/**
 * Jazzer.js fuzz target.
 * Run: npx jazzer fuzz/message-pack.fuzz.ts -- -max_total_time=300
 *
 * Install: pnpm add -D @jazzer.js/fuzzer
 */
import { parseMessagePack } from '../src/message-pack';

/**
 * The default export is the fuzz target function.
 * Jazzer.js calls it with a mutated Buffer on every iteration.
 */
export default function fuzz(data: Buffer): void {
  // Convert Node Buffer to Uint8Array for compatibility with the parser.
  const input = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);

  const result = parseMessagePack(input);

  // Invariant: the function must never throw — it always returns a ParseResult.
  // Jazzer.js catches thrown errors and reports them as crashes.
  // If we reach this line without a throw, the invariant holds.

  if (result.ok) {
    // Invariant: if parsing succeeds, data must be JSON-serialisable.
    // (Workers will JSON.stringify the parsed value before sending to D1.)
    JSON.stringify(result.data);
  }
}
```

### Running the fuzzer locally

```bash
# Install Jazzer.js.
pnpm add -D @jazzer.js/fuzzer

# Run for 5 minutes with a seed corpus directory.
npx jazzer fuzz/message-pack.fuzz.ts \
  -- \
  -max_total_time=300 \
  -max_len=65536 \
  -seed_corpus=fuzz/seeds/message-pack/

# On crash: Jazzer.js writes the crashing input to crash-<hash>.bin.
# Reproduce a crash:
npx jazzer fuzz/message-pack.fuzz.ts -- crash-abc123.bin
```

### Seed corpus

A seed corpus gives the fuzzer meaningful starting inputs, dramatically reducing time to find
interesting behaviour.

```bash
# fuzz/seeds/message-pack/
# Each file is a valid or interesting MessagePack byte sequence.

# Generate a variety of seeds using the @msgpack/msgpack encoder.
node -e "
const {encode} = require('@msgpack/msgpack');
const fs = require('fs');

const samples = [
  {},
  { key: 'value', num: 42 },
  new Array(100).fill({ nested: { deep: true } }),
  { bin: new Uint8Array(1024) },
  { str: 'a'.repeat(65535) },
];

samples.forEach((s, i) => {
  fs.writeFileSync(\`fuzz/seeds/message-pack/seed-\${i}.msgpack\`, Buffer.from(encode(s)));
});
"
```

---

## Approach 2: fast-check with a Persisted Crash Corpus

When Jazzer.js is too heavyweight for CI, use `fast-check` with a seed file that includes
previously discovered interesting inputs. This is slower to find new bugs but deterministic and
fast to reproduce.

```ts
// packages/parsers/src/__tests__/message-pack.fuzz.test.ts
import fc from 'fast-check';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { parseMessagePack } from '../message-pack';

const SEEDS_DIR = path.resolve(__dirname, '../../fuzz/seeds/message-pack');

describe('parseMessagePack – property tests', () => {
  // Load all known-interesting seeds as examples.
  const seedExamples = readdirSync(SEEDS_DIR, { withFileTypes: true })
    .filter(d => d.isFile())
    .map(d => [new Uint8Array(readFileSync(path.join(SEEDS_DIR, d.name)))] as const);

  test('never throws on arbitrary byte sequences', () => {
    fc.assert(
      fc.property(fc.uint8Array({ maxLength: 65_536 }), (bytes) => {
        // Must not throw — always return a ParseResult.
        expect(() => parseMessagePack(bytes)).not.toThrow();
      }),
      {
        numRuns: 10_000,
        seed: 42,            // Deterministic seed for CI reproducibility.
        examples: seedExamples,
      },
    );
  });

  test('successful parses produce JSON-serialisable output', () => {
    fc.assert(
      fc.property(fc.uint8Array({ maxLength: 65_536 }), (bytes) => {
        const result = parseMessagePack(bytes);
        if (result.ok) {
          expect(() => JSON.stringify(result.data)).not.toThrow();
        }
      }),
      { numRuns: 10_000, seed: 42, examples: seedExamples },
    );
  });

  test('depth limit prevents stack overflow on pathological nesting', () => {
    // Construct a maximally nested array by hand.
    // [[[[...]]]] 200 levels deep.
    let nested: unknown = 'leaf';
    for (let i = 0; i < 200; i++) nested = [nested];

    const { encode } = require('@msgpack/msgpack');
    const encoded = new Uint8Array(encode(nested));

    const result = parseMessagePack(encoded);
    // Either fails the depth check or succeeds — must not throw.
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/depth/i);
  });
});
```

---

## Approach 3: Radamsa + wrangler dev for HTTP-Level Fuzzing

For end-to-end fuzzing of the full Worker request path (including routing, auth middleware, and
response serialisation), feed mutated HTTP request bodies to a locally-running `wrangler dev`
instance using `radamsa`.

```bash
#!/usr/bin/env bash
# scripts/fuzz-worker-http.sh
#
# Prerequisites:
#   - wrangler dev running on port 8787 (start separately)
#   - radamsa installed: brew install radamsa / apt-get install radamsa
#   - jq installed

set -euo pipefail

WORKER_URL="http://localhost:8787"
ENDPOINT="/v1/items/import"
SEED_FILE="fuzz/seeds/http/item-import-valid.json"
ITERATIONS=500
CRASH_DIR="fuzz/crashes/http"
mkdir -p "$CRASH_DIR"

echo "Fuzzing $ENDPOINT for $ITERATIONS iterations..."

for i in $(seq 1 $ITERATIONS); do
  # radamsa mutates the seed file on each run.
  MUTATED=$(radamsa "$SEED_FILE")

  # Send the mutated body to the Worker.
  STATUS=$(curl -s -o /tmp/fuzz-response.txt -w "%{http_code}" \
    -X POST "$WORKER_URL$ENDPOINT" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TEST_TOKEN" \
    --data-raw "$MUTATED" \
    --max-time 10 \
    || echo "000")

  # Workers should never return 500 on malformed input — only 400/422.
  if [[ "$STATUS" == "500" || "$STATUS" == "000" ]]; then
    CRASH_FILE="$CRASH_DIR/crash-$(date +%s)-$i.json"
    echo "$MUTATED" > "$CRASH_FILE"
    echo "CRASH at iteration $i (status=$STATUS) → $CRASH_FILE"
    cat /tmp/fuzz-response.txt
  fi

  # Throttle to avoid overwhelming the local dev server.
  sleep 0.05
done

echo "Done. Crashes saved to $CRASH_DIR"
```

### Seed file example

```json
// fuzz/seeds/http/item-import-valid.json
{
  "items": [
    {
      "sku": "FEN-STRAT-001",
      "name": "Fender Stratocaster",
      "priceUsd": 1299,
      "stock": 5,
      "tags": ["guitar", "electric"]
    }
  ],
  "source": "catalog-sync-v2",
  "timestamp": "2026-08-22T00:00:00Z"
}
```

---

## Integrating Crash-Found Inputs as Regression Tests

When a fuzzer finds a crash, save the crashing input as a regression test fixture so the bug
cannot silently return.

```ts
// packages/parsers/src/__tests__/message-pack.regression.test.ts
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { parseMessagePack } from '../message-pack';

const CRASHES_DIR = path.resolve(__dirname, '../../fuzz/crashes/message-pack');

describe('parseMessagePack – crash regression suite', () => {
  // Dynamically load every crash file found by the fuzzer.
  const crashFiles = (() => {
    try {
      return readdirSync(CRASHES_DIR, { withFileTypes: true })
        .filter(d => d.isFile())
        .map(d => path.join(CRASHES_DIR, d.name));
    } catch {
      return []; // Directory does not exist yet — no crashes found.
    }
  })();

  if (crashFiles.length === 0) {
    test.skip('no crash regressions found', () => {});
  }

  for (const file of crashFiles) {
    test(`crash regression: ${path.basename(file)}`, () => {
      const bytes = new Uint8Array(readFileSync(file));
      expect(() => parseMessagePack(bytes)).not.toThrow();
    });
  }
});
```

---

## CI Integration

```yaml
# .github/workflows/fuzz.yml
name: Fuzz Tests

on:
  schedule:
    - cron: '0 1 * * 0'   # Weekly Sunday 01:00 UTC
  workflow_dispatch:

jobs:
  jazzer-fuzz:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Run Jazzer.js fuzz (10 minutes)
        run: |
          cd packages/parsers
          npx jazzer fuzz/message-pack.fuzz.ts \
            -- -max_total_time=600 -seed_corpus=fuzz/seeds/message-pack/
        continue-on-error: true   # Crashes are captured as artifacts, not CI failures.

      - name: Save crashes
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: jazzer-crashes
          path: packages/parsers/crash-*.bin
          if-no-files-found: ignore
          retention-days: 90

  property-fuzz:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Run fast-check property fuzz tests
        run: pnpm --filter @example-org/example-repo test -- --testPathPattern=fuzz
```

---

## Anti-patterns

**Running the fuzzer against the production or staging Worker.**
Malformed inputs with large payloads can trigger Worker CPU limits, consume D1 write quota, or
pollute production data. Always fuzz against `wrangler dev --local` or an isolated test
environment.

**Treating the absence of crashes as "the code is secure."**
A 5-minute fuzzing session explores only a fraction of the input space. Fuzzing reduces risk; it
does not eliminate it. Combine with static analysis (e.g. `semgrep`) and manual code review for
parsing-heavy code paths.

**Not saving the crashing corpus.**
If a fuzzer run finds a crash but the crashing input is not committed as a regression test, the
next refactor can silently re-introduce the bug. Always save crash files and add them to the
regression suite.

**Fuzzing at the JSON level when the actual risk is the binary protocol layer.**
Use the appropriate seed format. If your Worker parses MessagePack, fuzz with MessagePack seeds.
Fuzzing the JSON wrapper around a binary payload will not reach the binary parser.

---

## Gotchas

- **Jazzer.js requires Node 18+** — it uses the V8 coverage API for feedback. The Worker's V8
  isolate is irrelevant; Jazzer.js runs the extracted parsing code in a regular Node process.

- **`@msgpack/msgpack` enforce limits at decode time** — the `maxStrLength` / `maxBinLength`
  options must be set explicitly; the defaults are unbounded and can cause OOM on crafted inputs.

- **`fast-check` seed = 42 is deterministic only with the same fc version** — pin
  `fast-check` in `package.json` and include the version in the seed hash if you commit
  corpus outputs.

- **radamsa output may not be valid UTF-8** — pass `-H "Content-Type: application/octet-stream"`
  when fuzzing binary-accepting endpoints, or ensure `curl` sends raw bytes. JSON endpoints
  should get `application/json` so the Worker's input layer sees the correct content type.

---

## Verification

```bash
# 1. Run the Jazzer fuzz target for 30 seconds locally.
cd packages/parsers
npx jazzer fuzz/message-pack.fuzz.ts -- -max_total_time=30 \
  -seed_corpus=fuzz/seeds/message-pack/
# Expect output: "#<N> DONE" with no crash lines.

# 2. Run the fast-check property tests.
pnpm --filter @example-org/example-repo test -- --testPathPattern=fuzz
# All 10,000 iterations should pass.

# 3. Reproduce a synthetic crash to confirm the regression harness works.
node -e "
  const {encode} = require('@msgpack/msgpack');
  const fs = require('fs');
  let v = 'x';
  for (let i = 0; i < 300; i++) v = [v];
  fs.writeFileSync('packages/parsers/fuzz/crashes/message-pack/synthetic-deep.bin',
    Buffer.from(encode(v)));
"
pnpm --filter @example-org/example-repo test -- --testPathPattern=regression
# The synthetic crash should be replayed and the test should pass (no throw).

# 4. Run the HTTP fuzzer against wrangler dev.
npx wrangler dev --local --port 8787 &
sleep 3
bash scripts/fuzz-worker-http.sh
# Expect 0 crashes logged to fuzz/crashes/http/.
```

---

## Related

- `fuzz-testing-basics.md`
- `go-fuzzing-corpus-and-regression-promotion.md`
- `schema-driven-api-fuzzing-schemathesis.md`
- `property-based-testing-fast-check-workers.md`
- `property-based-testing-shrinking-and-reproducible-failures.md`
- `workers-test-patterns.md`

## Sources

- Jazzer.js: https://github.com/CodeIntelligenceTesting/jazzer.js
- fast-check: https://fast-check.io/
- radamsa: https://gitlab.com/akihe/radamsa
- @msgpack/msgpack decode options: https://github.com/msgpack/msgpack-javascript#readme
- OWASP Fuzzing guide: https://owasp.org/www-community/Fuzzing
