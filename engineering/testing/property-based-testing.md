# Property-Based Testing

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your test suite has hundreds of example-based tests with hardcoded inputs
and expected outputs, yet bugs still slip through because edge cases were
not anticipated. Adding new test cases is a manual process of imagining
what might go wrong. You find bugs in production that could have been
caught by testing with a wider range of inputs.

## Context

Property-based testing (PBT) inverts the example-based approach: instead
of specifying individual inputs and outputs, you define *properties* that
must hold for all valid inputs, and the framework generates hundreds or
thousands of random inputs to find counterexamples. When a failing input
is found, the framework *shrinks* it to the smallest reproducing case.
PBT was pioneered by Haskell's QuickCheck (2000) and has mature
implementations in every major language. In 2026, PBT adoption is
accelerating as AI-assisted test generation makes property definition
easier and as teams discover that PBT finds entire classes of bugs that
example-based tests miss.

## Core concepts

### Properties vs. examples

```
Example-based: add(2, 3) === 5
Property-based: for all (a, b): add(a, b) === add(b, a)  // commutativity
```

Properties describe *invariants* — things that must always be true
regardless of the specific input. Common property patterns:

| Pattern | Description | Example |
|---|---|---|
| **Round-trip** | encode then decode returns original | `parse(serialize(x)) === x` |
| **Idempotence** | applying twice equals applying once | `sort(sort(x)) === sort(x)` |
| **Invariant** | a condition always holds | `sorted(x).length === x.length` |
| **Commutativity** | order doesn't matter | `merge(a, b) === merge(b, a)` |
| **Oracle** | compare against known-correct implementation | `fastSort(x) === referenceSort(x)` |
| **No crash** | function doesn't throw for any valid input | `parse(randomString)` doesn't throw |

### Shrinking

When a random input triggers a failure, shrinking reduces it to the
minimal counterexample. A failing array `[42, -7, 0, 13, -99, 5]` might
shrink to `[-1, 0]` — the smallest input that still triggers the bug.

Good shrinking is what makes PBT practical. Without it, debugging a
failure caused by a 200-element random array is impractical.

## Language implementations

### JavaScript/TypeScript — fast-check

```typescript
import fc from 'fast-check';

// Property: sorting is idempotent
test('sort is idempotent', () => {
  fc.assert(
    fc.property(fc.array(fc.integer()), (arr) => {
      const sorted = [...arr].sort((a, b) => a - b);
      const sortedTwice = [...sorted].sort((a, b) => a - b);
      expect(sorted).toEqual(sortedTwice);
    })
  );
});

// Property: JSON round-trip
test('JSON round-trip preserves data', () => {
  fc.assert(
    fc.property(fc.jsonValue(), (value) => {
      expect(JSON.parse(JSON.stringify(value))).toEqual(value);
    })
  );
});
```

**Custom arbitraries (generators):**

```typescript
const userArbitrary = fc.record({
  name: fc.string({ minLength: 1, maxLength: 100 }),
  age: fc.integer({ min: 0, max: 150 }),
  email: fc.emailAddress(),
  role: fc.constantFrom('admin', 'user', 'guest'),
});

test('user serialization round-trip', () => {
  fc.assert(
    fc.property(userArbitrary, (user) => {
      expect(deserializeUser(serializeUser(user))).toEqual(user);
    })
  );
});
```

### Python — Hypothesis

```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers()))
def test_sort_preserves_length(xs):
    assert len(sorted(xs)) == len(xs)

@given(st.text())
def test_encode_decode_roundtrip(s):
    assert decode(encode(s)) == s
```

### Other languages

| Language | Library | Notes |
|---|---|---|
| Rust | proptest, quickcheck | proptest has better shrinking |
| Java/Kotlin | jqwik | JUnit 5 integration |
| Go | rapid | Integrated shrinking |
| Elixir | StreamData | Built into ExUnit |
| C# | FsCheck | Works with xUnit/NUnit |

## Integrating PBT with example-based tests

PBT does not replace example-based tests — it complements them:

```
Example-based tests: document specific behaviors, serve as documentation
Property-based tests: explore the input space, find edge cases

Use together:
  - Example tests for specific business rules ("premium users get 20% discount")
  - Property tests for invariants ("discount never exceeds original price")
  - Example tests for regression cases (bugs found by PBT become examples)
```

When PBT finds a bug, add the minimal counterexample as an example-based
test. This creates a regression test that is fast to run and documents
the specific edge case.

## Anti-patterns

- **Testing implementation, not properties** — writing properties that
  duplicate the implementation logic does not find bugs. Properties
  should describe *what* must be true, not *how* it is computed.
- **Ignoring shrink quality** — custom generators without shrinking
  produce failures with 500-character random strings instead of minimal
  counterexamples. Always define shrinking for custom arbitraries.
- **Too few runs** — the default 100 iterations may miss rare edge
  cases. For critical code, increase to 1,000+ iterations. In CI, use
  fewer iterations for speed and run extended suites nightly.
- **Filtering instead of mapping** — using `fc.pre(condition)` or
  `assume()` to reject most generated values wastes iterations. Map
  generators to produce only valid inputs directly.

## Gotchas

- **Randomness and CI reproducibility** — PBT failures are
  non-deterministic by default. Use seed logging (fast-check and
  Hypothesis both log the seed on failure) so failing runs can be
  replayed exactly.
- **Slow properties** — each property runs hundreds of times. If the
  function under test is slow (database access, network calls), PBT
  becomes impractical. Mock external dependencies or test pure logic only.
- **Floating-point properties** — floating-point arithmetic violates
  many mathematical properties (associativity, distributivity). Use
  approximate equality or restrict to integer arithmetic.
- **State machine testing** — advanced PBT can model stateful systems as
  state machines, generating sequences of operations and checking
  invariants after each step. This is powerful but complex to set up.

## Verification

- Property-based tests exist for all serialization round-trips.
- Custom arbitraries have defined shrinking behavior.
- CI logs the random seed for every PBT run.
- Counterexamples found by PBT are added as example-based regression tests.
- PBT iteration count is configured appropriately (lower in CI, higher
  in nightly).

## Related

- `documentation/categories/testing/event-driven-async-api-testing.md`
- `documentation/categories/testing/mobile-app-testing-automation-frameworks.md`
- `documentation/categories/testing/api-contract-testing.md`

## Source URLs (verified 2026-08-16)

- fast-check documentation — https://fast-check.dev/
- Hypothesis documentation — https://hypothesis.readthedocs.io/
- proptest (Rust) — https://proptest-rs.github.io/proptest/
- PBT guide (Increment) — https://increment.com/testing/in-praise-of-property-based-testing/
