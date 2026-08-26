# Property-based testing, shrinking, and reproducible failures

**Issue:** Hand-picked examples miss broad input spaces, while uncontrolled generated tests can produce flaky or irreproducible failures.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Property-based testing generates inputs from declared strategies and checks invariants across them. Hypothesis shrinks a failing generated example toward a simpler counterexample and can retain useful examples in its example database.

State properties as externally meaningful invariants, not replicas of implementation logic. Preserve the minimized counterexample, test configuration, and environment needed to reproduce a failure. A generated pass complements, rather than replaces, targeted examples, integration tests, and regression cases.

## Operational controls

- Bound input sizes, deadlines, and example counts from measured suite budgets.
- Avoid nondeterministic external services and shared mutable state inside properties.
- Convert important minimized failures into explicit regression examples.
- Keep the example database scoped to compatible tests and trust boundaries.
- Do not suppress health checks without recording and reviewing the reason.
- Distinguish a reproducible product defect from a flaky environment failure.

## Verification

1. Seed a known defect and confirm the framework finds and shrinks it.
2. Re-run the displayed counterexample directly.
3. Run from an empty example database and confirm correctness does not depend on cached cases.
4. Execute repeatedly and in parallel to expose isolation defects.
5. Track test duration and generated-example counts in CI.

## Sources

- [Hypothesis: How Hypothesis works](https://hypothesis.readthedocs.io/en/latest/explanation/how-hypothesis-works.html)
- [Hypothesis: Settings](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.settings)
- [Hypothesis: Example database](https://hypothesis.readthedocs.io/en/latest/reference/api.html#hypothesis.database.ExampleDatabase)
