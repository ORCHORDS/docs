# Boundary Value Analysis Equivalence Partitioning

Two black-box specification techniques drive the test cases that find the most defects per
minute invested. *Equivalence partitioning* groups inputs into sets that the specification
treats identically, so a single representative test exercises the whole set instead of one test
per value. *Boundary value analysis* observes that defects cluster at the edges of those sets,
not in their middles, and so concentrates cases on the boundaries: the smallest valid value,
the largest valid value, the value just below the lower bound, the value just above the upper
bound. The two techniques compose: equivalence partitioning decides what to ignore, boundary
value analysis decides what to hit. Used together they are the cheapest formal justification for
test selection in any specification-driven test plan.

## Scope

Covers the application of equivalence partitioning and boundary value analysis to functional
test design for any component whose behaviour is specified in terms of inputs, outputs, or
state transitions. Applies to unit tests, integration tests, and acceptance tests alike; the
technique is independent of the level of the test. Does not cover combinatorial pair-wise or
N-wise techniques that build on top of these foundations, and does not cover statistical
testing where the input distribution is part of the test goal.

## Workflow or implementation guidance

1. **Read the specification for partitions.** A *partition* is a contiguous range of values (or
   values of the same type) that the specification declares equivalent. Common partition
   sources include:
   - numeric ranges with explicit lower and upper bounds: `0 <= age <= 150`;
   - enumerated types: payment method in `{card, invoice, wallet}`;
   - character classes: identifiers matching `^[A-Z][A-Z0-9]{2,7}$`;
   - date ranges: `startDate <= endDate <= startDate + 365 days`;
   - state transitions: a session is `anonymous`, `authenticated`, or `expired`.
   For each partition, name a *valid* representative value. These representatives are the
   minimum test set that exercises the happy path.
2. **List the boundaries of each partition.** A boundary is any point at which the
   specification's rule changes — the minimum, the maximum, the on/off edge, the first valid
   value and the first invalid value. For each boundary, prepare:
   - the boundary value itself;
   - the value just inside the boundary (one below minimum, one above maximum);
   - the value just outside the boundary (one below minimum's invalid side, one above
     maximum's invalid side).
   The "just outside" cases are where off-by-one defects live.
3. **Treat off-by-one boundaries explicitly.** A common defect is a `>` versus `>=` mistake
   in the implementation. Boundary cases prove the difference by design: test `n-1`, `n`, and
   `n+1` for any boundary `n`. Where the boundary is a date or time, test the last second of
   the valid range and the first second of the invalid range — not just the day boundary.
4. **Combine partitions only when the specification does.** If a function accepts a partition
   for argument `a` and another for argument `b`, the test set is not the cross product;
   testing one representative per partition is usually enough. Cross product is combinatorial
   testing, a different technique that should be applied deliberately.
5. **Document the partitioning itself.** A test plan that lists the partitions and the chosen
   representatives is auditable and reviewable. A test plan that lists only "test various
   inputs" cannot be defended when a defect lands in an untested corner.
6. **Apply the same technique to outputs and state, not only inputs.** The output of a tax
   calculator has partitions (zero tax, standard rate, higher rate, exempt) with boundaries at
   each threshold. State machines have boundary transitions (anonymous to authenticated at
   login, authenticated to expired at expiry). Treating output and state as part of the
   partitioning prevents the test set from being input-only and missing behavioural edges.
7. **Treat invalid equivalence partitions as first-class.** The invalid sets are where error
   handling lives. A specification that says "reject empty string" defines an empty-string
   partition that must be exercised; the test asserts the rejection contract, not just that
   something fails.

Illustrative boundaries for a function `discount(quantity, customerType)` whose specification
states `quantity` is an integer in `[1, 1000]` and `customerType` is in `{standard, premium}`:

- Equivalence representatives: `(500, standard)`, `(500, premium)`.
- Boundaries for `quantity`: `1`, `0`, `2`, `1000`, `1001`.
- Boundaries for `customerType`: any value not in the enumeration (for example `"guest"`)
  is an invalid representative; the specification may either reject it or treat it as
  `standard` — either way the behaviour must be tested.
- Combined boundary cases: `(1, premium)`, `(0, standard)`, `(1000, premium)`,
  `(1001, standard)`, `(500, "guest")`.

## Controls

- Each test case in the suite has a documented partition and a named boundary or representative
  role. Tests without that annotation are rejected in review.
- Coverage by partition is tracked: every valid and invalid partition has at least one test.
  Gaps are visible.
- Boundary tests are mandatory for any new parameter: a pull request that introduces a new
  field with implicit ranges is rejected until partitions and boundaries are documented and
  tested.
- Boundary value tables are revisited when the specification changes. The test plan is a
  derived artefact and must be regenerated, not only extended.

## Validation evidence

- A mutation-testing run that targets boundary conditions (replacing `>` with `>=`,
  `off-by-one` shifts) reports the boundary tests as killing those mutants. If mutants survive,
  the boundary is not actually exercised.
- A review shows every specification clause has at least one partition and that every boundary
  has both on and off cases.
- A defect that escaped to production can be traced back to a partition or boundary that was
  either not enumerated or not tested; the retrospective updates the test plan to close the gap.

## Failure modes and correction

- *Testing every value in a partition.* Replace with representatives. If the test set looks
  linear in the input range, the partitioning has not been done.
- *Missing the just-outside boundary.* A test set that hits `0` and `100` but not `-1` and
  `101` invites off-by-one defects to slip through. Add the off-boundary cases deliberately.
- *Ignoring output partitions.* Symptom is a test suite that exercises inputs but never
  asserts the boundary between output states. Re-derive partitions from the output
  specification, not only the input.
- *Cross-product explosion.* Symptom is a test suite that runs a representative from every
  input partition combined with a representative from every other input partition. Replace
  with one representative per partition, plus targeted cross-partition boundary cases where
  interactions matter.
- *Equivalence asserted but not justified.* A partition labelled "valid" without a citation
  to the specification is a guess. Require the citation in the test plan.
- *Float boundaries.* Boundary value analysis on floating-point inputs is sensitive to the
  precision the implementation uses. Test the boundary plus the smallest representable step
  above and below, and pin the comparison tolerance rather than relying on exact equality.

## Limitations

- The techniques assume the specification is the source of truth. A specification that
  contradicts itself or omits partitions produces a test plan that codifies the contradiction.
- Equivalence partitioning only groups values the specification treats identically. Where two
  values are nominally equivalent but the system treats them differently (time zones, locales,
  encoding), the partitioning is wrong and must be revised.
- Boundary value analysis handles scalar and ordered ranges well but is weaker for non-ordered
  sets — for example, complex object graphs or graph-structured state machines — where
  transition coverage and state-pair coverage may be more appropriate.
- The techniques do not generate test oracles. They tell you *which* values to try, not
  *what* the correct output is. The oracle still has to come from the specification or the
  implementation's intent.
- Used in isolation they under-cover concurrency, timing, and resource exhaustion. Boundary
  value analysis on `timeoutMs` does not by itself find the deadlock that emerges under load.

## Canonical sources

- ISTQB, *Certified Tester Foundation Level (CTFL) syllabus* (definitions of equivalence
  partitioning and boundary value analysis, plus worked examples): https://istqb.org/downloads/category/2-foundation-level-documents.html
- ISTQB, *Certified Tester Foundation Level (CTFL) syllabus* (companion glossary of test
  design techniques used by the CTFL programme).
- Deque Systems, *axe-core rule descriptions* (cross-reference for accessible boundary design,
  for example numeric input controls where boundary handling has user-facing impact):
  https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md
