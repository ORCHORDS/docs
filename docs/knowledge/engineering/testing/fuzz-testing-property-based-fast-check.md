# Fuzz Testing Property Based Fast Check

Property-based testing asserts invariants about the system under test rather than asserting
specific outputs for specific inputs. The library generates a large number of inputs,
shrinking the ones that cause a failure to the smallest reproducer it can find. Fast-check
is the dominant property-based testing library for JavaScript and TypeScript; it generates
arbitrary values for primitive and composite types, supports custom arbitraries, and
implements shrinking that produces minimal failing cases. Used well, it surfaces defects
that example-based tests miss because no human chose the input that triggered them; used
without discipline, it produces a stream of "failures" caused by invalid inputs that the
SUT was never supposed to accept.

## Scope

Covers the application of fast-check to property-based testing in JavaScript and
TypeScript, including the design of properties, the use of arbitraries, the interpretation
of shrinking output, and the integration with example-based tests. Does not cover native
fuzzing (AFL, libFuzzer) or coverage-guided fuzzing of binaries, and does not cover
property-based testing in other languages (QuickCheck, Hypothesis, jqwik) beyond noting
shared patterns.

## Workflow or implementation guidance

1. **Identify a property, not a test case.** A property is a statement that holds for *all*
   inputs in a domain: "reversing a string twice returns the original",
   "encoding then decoding any JSON value returns the original",
   "the cart total after removing an item equals the cart total before adding it minus the
   item's price". The property is the assertion; the inputs are generated.
2. **Choose the right arbitrary for the domain.** Fast-check's default arbitraries produce
   valid JavaScript values (integers, strings, arrays, objects). For the domain under test,
   the arbitrary must produce only values the SUT is supposed to handle; otherwise the
   generator will produce "failures" that the SUT correctly rejects as invalid input. Custom
   arbitraries constrain the generator: for example, an `arbEmail` that uses a regex, an
   `arbNonEmptyString` that excludes empty strings.
3. **Combine arbitraries to model realistic inputs.** The SUT rarely sees a single value; it
   sees a structured input with relationships between fields (a positive quantity, a
   non-empty list, a date that is not in the past). Build arbitraries that respect those
   relationships. A property tested against an arbitrary that produces invalid combinations
   produces invalid failures.
4. **Use `fc.assert` with `fc.property` for the assertion.** The basic structure is:

```ts
import fc from 'fast-check';

fc.assert(
  fc.property(fc.string(), (s) => reverse(reverse(s)) === s),
  { numRuns: 1000 }
);
```

`numRuns` controls how many inputs the library generates; the default is 100, which is
often too few for shrinking to be useful. Raise it where the property depends on rare
combinations.

5. **Lean on shrinking to produce minimal reproducers.** When the property fails, fast-check
   shrinks the failing input to the smallest version that still fails — a string becomes
   shorter, an array becomes smaller, a number approaches zero. The shrunken input is the
   one to put in a regression test, not the original generated input. A failing property
   whose shrinking is disabled loses its most valuable artefact.
6. **Convert failing properties into regression tests.** A failing property produces a
   reproducible failure; that failure is captured as a fast-check example and added to the
   test suite as a regression case. The example-based test asserts the same property on the
   specific input that triggered it, so the failure is locked in even if the property is
   later modified.
7. **Add preconditions explicitly when the domain is restricted.** A property that holds
   only for non-empty strings is asserted with a precondition: `fc.property(fc.string(),
   (s) => s.length === 0 || ... )` or with `fc.pre(...)` inside the property body.
   Preconditions tell the library to discard invalid inputs rather than treat them as
   failures.
8. **Distinguish property failures from generator bugs.** A failing property is either (a) a
   real defect in the SUT, (b) a generator that produced an invalid input the SUT correctly
   rejects, or (c) a property statement that is wrong. Triage in that order; do not "fix"
   the property to match the SUT without understanding why the property was wrong.
9. **Seed the generator for reproducibility.** Fast-check allows a seed to be set; when a
   failure is captured, the seed is included. Pinning the seed makes the failure
   reproducible across runs and across machines.
10. **Combine with example-based tests, do not replace them.** Property-based tests are
    strongest on round-trip and invariant properties; example-based tests are strongest on
    specific known cases and boundary conditions. The two compose: example-based tests
    pin the known cases, property-based tests sweep the unknown space.

## Controls

- Each property has a name, a description of the invariant it asserts, and an example-based
  regression test for any failure it has produced.
- The generator configuration is committed; changes to `numRuns`, seed, or custom
  arbitraries are reviewed.
- The shrinking output is captured in CI as part of the failure report, not discarded.
- Preconditions are reviewed: a property with no preconditions against a constrained
  domain will generate spurious failures.
- A failing property blocks the build; the regression test must be added before the fix
  is merged.

## Validation evidence

- A deliberately broken implementation (reversing the string with a bug) is detected by the
  property; the shrunken failure is a string of length 1 or 2, not the original long string.
- A regression test derived from a previous property failure is present in the suite; if
  the bug is re-introduced, the test fails.
- Property coverage is documented: which functions have properties, which invariants are
  asserted, which arbitraries are used. Gaps are visible.
- A mutation test against the SUT's logic is killed by the property-based tests where
  example-based tests would have missed it.

## Failure modes and correction

- *Failing properties caused by an overly broad generator.* Tighten the arbitrary; use
  preconditions; do not modify the property to assert "no error is thrown on invalid input"
  unless that is the actual contract.
- *Property modified to "pass" instead of the SUT fixed.* The property is the spec; a
  property that holds by tautology is worse than no property. Refactor the property to
  express the real invariant; if the SUT violates it, fix the SUT.
- *Shrinking disabled.* The failure is captured but the input is huge. Re-enable shrinking;
  the smallest failure is the easiest to debug and the cheapest to assert as a regression.
- *Insufficient `numRuns`.* Rare failures slip through. Raise the count; verify that the
  CI runtime budget accommodates it.
- *Custom arbitrary with bias.* A custom arbitrary that over-samples certain shapes hides
  defects in others. Use Fast-check's built-in arbitraries where possible, and bias
  generators explicitly only with documented reason.
- *Properties drift away from the SUT's contract.* A property suite that has not been
  reviewed in a year describes what the SUT used to do, not what it does now. Tie property
  review to the SUT's design review.

## Limitations

- Property-based testing is weakest on properties that are hard to express as invariants.
  "Looks correct" or "feels responsive" are not properties; they cannot be asserted.
- The generator's quality bounds the test's quality. An arbitrary that misses a corner of
  the input space produces a property that holds in the tested space and fails in the
  untested space.
- Fast-check operates inside the JavaScript runtime; it cannot exercise native code,
  kernel-level behaviour, or external services. A property-based test of a database
  driver is a property-based test of the driver's in-memory layer; the database itself
  needs separate testing.
- The shrinking is sound for the structures fast-check understands. A custom structure
  with an unusual ordering shrinks less effectively; the failure is captured but the
  minimal case may not be minimal enough.
- Property-based tests do not replace manual reasoning about edge cases. A property that
  holds for all generated inputs is not a proof; it is an empirical sample. Confidence
  grows with `numRuns`, never reaches certainty.

## Canonical sources

- fast-check, *fast-check documentation* (arbitraries, properties, shrinking, custom
  generators): https://fast-check.dev/
- fast-check, *Introduction to property-based testing* (the conceptual model behind
  properties, arbitraries, and shrinking): https://fast-check.dev/docs/introduction/
- dubzzz, *fast-check repository* (issue tracker and design discussions for advanced
  features): https://github.com/dubzzz/fast-check
