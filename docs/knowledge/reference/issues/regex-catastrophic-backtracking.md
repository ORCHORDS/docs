# regex-catastrophic-backtracking

**Issue:** A regex with nested quantifiers causes exponential backtracking, blocking the event loop on crafted input (ReDoS)
**Date:** 2026-08-11
**Status:** documented

## Symptom
A regex match call hangs or takes seconds on a short input string. CPU spikes to 100%. In a web server context this is a denial-of-service vector.

## Root cause
Patterns like `(a+)+`, `(a|a)+`, or `(a*)*` have exponential worst-case time complexity. The regex engine tries all possible groupings before concluding no match.

## Fix
1. Rewrite the pattern to avoid ambiguity using possessive quantifiers or atomic groups (not available in JS natively).
2. Use a linear-time regex engine: the `re2` npm package wraps Google RE2.
3. Validate input length before applying the regex.
```ts
import RE2 from 're2';
const safe = new RE2(/^([a-z]+\s?)+$/);
safe.test(input); // linear time
```

## Detection
Use `safe-regex` npm package:
```bash
npx safe-regex '(a+)+'
```
Or ESLint plugin `eslint-plugin-security` rule `detect-unsafe-regex`.

## Related
- `event-loop-blocking-json-stringify.md`
