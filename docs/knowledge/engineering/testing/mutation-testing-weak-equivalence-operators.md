# Mutation Testing Weak Equivalence Operators

Mutation testing is strongest when the mutants it generates represent real, distinct
defects. When two mutants produce the same observable behaviour, they are *equivalent* and
the test suite cannot distinguish them — the mutation score treats them as survivors, but
the gap is in the generator, not in the tests. Some mutation operators generate more
equivalent mutants than others, and some mutations are structurally weak in the sense
that the defect they represent is rarely a defect at all. Understanding the strength of
each operator — which defects it reliably captures and which it cannot — is the
prerequisite to designing a mutation suite that improves test quality rather than one
that pads the score with survivors nobody can fix.

## Scope

Covers the design choices around mutation operators in Stryker and similar JavaScript and
TypeScript mutation tools, with a focus on operators whose strength is variable: `String`,
`Array`, `Boolean`, `Conditional`, `Logical`, `Unary`, and the various arithmetic and
relational operators. Applies to any project that runs mutation testing as a quality gate.
Does not cover the academic taxonomy of mutation operators, nor mutation testing in
non-JavaScript ecosystems.

## Workflow or implementation guidance

1. **Treat the operator list as a defect taxonomy.** Each operator models a class of
   defect: `Conditional` models predicate inversions and dead branches, `Arithmetic`
   models off-by-one and operator-confusion defects, `Equality` models `==` versus `===`
   regressions, `Boolean` models truth-value errors. The operator list in the Stryker
   configuration is a statement about which defects the team is willing to test for. A
   configuration that includes every operator is a configuration that has not been
   thought about.
2. **Distinguish strong operators from weak operators.** Strong operators (for example,
   `Conditional`, `Boolean`, `Logical`) generate mutants that, when killed, prove the test
   suite exercises the relevant logic branch. Weak operators (for example, `String`,
   `Array`) generate mutants that often survive because the change does not matter — a
   string literal mutated to a different string often produces a response that no test
   asserts on, and an empty array mutated to a single element often goes unnoticed.
3. **Configure weak operators with explicit exclusion.** Stryker accepts an
   `excludedMutations` list in the mutator configuration. Excluding `StringLiteral` is a
   common starting point; the operator generates many survivors, each requiring triage,
   and the value of catching a "the wrong error message" defect is low compared to the
   cost of triage. Document the exclusion with the rationale.
4. **Use `StringLiteral` and `ArrayDeclaration` only where the literal is testable.** A
   string that flows into a user-visible message is a defect worth catching; a string that
   is a logging detail or an internal identifier is not. Configure the inclusion of
   string-mutation operators at the per-file level, not globally, where the file's
   responsibilities justify the operator.
5. **Treat `Conditional` and `Boolean` as mandatory.** These operators generate mutants
   that map directly to defects the team cares about: a condition the wrong way round, a
   branch always-true or always-false. A mutation suite that excludes them is not testing
   the SUT's decision logic.
6. **Combine mutation operators with mutation states.** Stryker mutators can be configured
   with `mutator.state` for some operators, allowing finer-grained generation: `Arithmetic`
   can mutate to a sibling operator or to a constant; `Equality` can mutate to a different
   equality or to the negation. The state configuration is the second axis of the defect
   taxonomy — a state of `Arithmetic.Boundary` catches off-by-one specifically.
7. **Track equivalent mutants explicitly.** Stryker cannot detect equivalent mutants
   automatically. The team must mark them in the report (or via the Stryker API) with the
   rationale — "this conditional is never reachable because the previous branch returns" —
   so they do not inflate the apparent gap.
8. **Re-evaluate the operator list after every incident.** A defect that escaped to
   production is a defect class the mutation suite did not catch. If the corresponding
   operator was excluded, the exclusion was wrong; if the operator was included, the
   surviving mutant was not triaged. Both are signals that the operator configuration
   needs adjustment.
9. **Prefer stronger assertions over operator exclusion.** A weak operator generates
   survivors because the tests do not assert strongly enough. Adding an assertion that
   distinguishes the mutated value from the original kills the mutant and improves the
   test's quality. Operator exclusion is the cheaper but less educational fix.
10. **Calibrate the threshold against the operator set.** A mutation score threshold that
    was set with the full operator list in place is too high once weak operators are
    excluded. Recalibrate after every operator change; the threshold measures the gap, and
    the gap depends on which mutants exist.

A representative Stryker mutator configuration with weak operators excluded:

```json
{
  "mutator": {
    "name": "javascript",
    "excludedMutations": [
      "StringLiteral",
      "ArrayDeclaration"
    ]
  }
}
```

The rationale (operator generates many equivalent mutants that pad the score without
exercising real defects) is committed alongside the configuration change.

## Controls

- The mutator configuration is committed and reviewed; changes to the operator list or
  states are treated as defect-policy changes, not as tooling tweaks.
- Equivalent mutants are tagged in the Stryker report with rationale; the count is
  monitored to prevent over-tagging.
- The mutation threshold is recalibrated when the operator set changes; a threshold that
  no longer matches the configuration is flagged.
- A regression that escaped to production is reviewed against the operator list; if the
  operator was excluded, the exclusion is reversed in the next change.
- The weak-operator exclusions are revisited at every major release; the rationale is
  re-examined rather than copied forward by default.

## Validation evidence

- A defect class that the mutation suite was configured to catch (for example, predicate
  inversion) is observed to be killed by the suite; the corresponding operator survives
  the test runs.
- An operator that was excluded on the rationale "generates equivalent mutants" is
  reviewed after a release; if new evidence suggests it would catch real defects, it is
  re-enabled with a baseline reset.
- The mutation score trends upward as weak-operator exclusions are offset by stronger
  assertions in the tests, not by more operator exclusions.
- The equivalent-mutant tagging rate is bounded; an unusual spike in tagging is
  investigated as a possible over-tagging pattern.

## Failure modes and correction

- *Operator list copied from a tutorial.* Review against the team's defect history; exclude
  only what is genuinely weak; include what catches the defects the team actually ships.
- *Weak operator excluded without rationale.* Document the rationale in the configuration
  file or in the test strategy doc; undocumented exclusions are reversed in the next review.
- *Strong operator excluded to lower the bar.* Reverse the exclusion; lower the threshold
  instead.
- *Equivalent mutant tagging used to game the score.* The tag is visible to reviewers; an
  over-tagged report loses its meaning. Calibrate the tag against the defect it would
  catch.
- *Threshold not recalibrated after operator change.* Re-anchor the threshold against the
  current operator set; a mismatch is itself a defect.
- *Mutation states misunderstood.* Use the state axis deliberately to model specific
  defect classes; do not toggle states without understanding what they generate.

## Limitations

- The strong/weak distinction is not universal. An operator that is weak in one codebase
  may be strong in another where the code under test depends heavily on string comparison
  or array ordering.
- Mutation testing cannot generate mutants that no small mutation can represent. A design
  flaw or a missing requirement is outside the operator taxonomy.
- The taxonomy of defects the operator models is an approximation. A `Conditional`
  mutation does not catch every predicate bug; it catches the ones its generation rules
  express.
- Operator exclusion is a permanent configuration change. Excluding a weak operator that
  later becomes strong (because the SUT's design changed) requires the team to remember
  to re-enable it.
- Stryker's mutator support varies across language features; exotic syntax or new
  language features may not have corresponding operators at all.

## Canonical sources

- Stryker Mutator, *Stryker documentation* (mutator configuration, equivalence handling,
  and threshold semantics): https://stryker-mutator.io/docs/
- Stryker Mutator, *Stryker JS configuration reference* (operator list, states, and
  exclusion syntax): https://stryker-mutator.io/docs/stryker-js/configuration/
- fast-check, *Introduction to property-based testing* (complementary technique for
  invariants that are difficult to express as mutations): https://fast-check.dev/docs/introduction/
