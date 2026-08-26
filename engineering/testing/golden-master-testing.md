# golden-master-testing

**Issue:** Detecting regressions in complex output by comparing against a saved reference
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A report generator, code formatter, or serialiser produces hundreds of lines of output. Writing manual assertions for every field is impractical.

## Pattern / Solution
Capture a "golden master" — the full output of the system today — and compare future runs against it:

```ts
import { toMatchFile } from "jest-file-snapshot";

test("invoice PDF text content matches golden master", async () => {
  const text = await extractText(generateInvoice(sampleOrder));
  expect(text).toMatchFile("__golden__/invoice.txt");
});
```

On first run, the file is created. Subsequent runs diff against it. Review diffs in PRs the same way you review code changes.

To update the golden master intentionally:
```bash
# Jest snapshots equivalent
jest --updateSnapshot
# or delete the file and re-run
```

## Gotchas
- Golden masters encode current behaviour including bugs — treat a first-time green run with suspicion.
- Avoid golden masters for output with timestamps, UUIDs, or other volatile fields; normalise those before comparison.
- Large golden files make PRs unreadable; consider hashing or diffing only key sections.

## Related
- characterization-tests
- approval-testing
- snapshot-testing-pitfalls
