# approval-testing

**Issue:** Validating complex outputs through human review and approval rather than coded assertions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Outputs such as generated reports, emails, or rendered HTML are too complex for assertion-by-assertion testing but need to be verified for correctness.

## Pattern / Solution
Approval testing workflow:

1. Run the test — it produces an "actual" file.
2. Open a diff tool to compare "actual" against the "approved" (golden) file.
3. If the diff looks correct, copy actual to approved and commit.
4. Future runs diff against the approved file; any deviation fails the test.

Using `approvaltests` for TypeScript:

```ts
import { verify } from "approvals/lib/Approvals";

test("monthly report matches approved output", () => {
  const report = generateMonthlyReport(fixtures.june);
  verify(report); // writes .received.txt; diffs with .approved.txt
});
```

Store approved files in version control alongside tests. Treat approval diffs in PRs as the primary review artefact for output-heavy features.

## Gotchas
- Approval tests require a human in the loop for the first approval — they are not fully automated out of the box.
- Normalise volatile data (dates, IDs) before approval to avoid false failures.
- Do not approve a file you haven't read — the point is that a human verified the output.

## Related
- golden-master-testing
- snapshot-testing-pitfalls
- characterization-tests
