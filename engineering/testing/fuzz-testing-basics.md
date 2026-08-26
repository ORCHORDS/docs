# fuzz-testing-basics

**Issue:** Using fuzzing to find crashes and security vulnerabilities from malformed input
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Parsers, serializers, and input handlers may crash or behave unexpectedly on malformed or adversarial input. Fuzzing finds these automatically.

## Pattern / Solution
JavaScript fuzzing with `@jazzer.js/core`:
```ts
// fuzz/parseJson.fuzz.ts
import { FuzzedDataProvider } from "@jazzer.js/core";

export function fuzz(data: Buffer): void {
  const fuzzed = new FuzzedDataProvider(data);
  const input = fuzzed.consumeString(1000);
  try {
    JSON.parse(input); // should never throw unhandled
  } catch {
    // expected — JSON.parse throws on invalid input
  }
}
```

For Go: use `go test -fuzz=FuzzMyFunc`.
For Rust: use `cargo fuzz`.

Corpus-based fuzzing: store interesting inputs in `fuzz/corpus/`:
```bash
npx jazzer fuzz/parseJson.fuzz.ts --corpus fuzz/corpus/
```

## Gotchas
- Fuzzing finds crashes, not semantic bugs
- Run fuzzing in CI with time limits: `--fuzz-duration=60s`
- Track corpus between runs for faster coverage

## Related
- `property-based-testing-fast-check.md`
- `security-testing-zap.md`
