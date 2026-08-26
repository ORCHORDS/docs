# Mutation testing, surviving mutants, and threshold governance

**Issue:** High line coverage can coexist with assertions that do not detect incorrect behavior.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Mutation testing makes controlled changes to production code and checks whether the test suite fails. A killed mutant indicates detection; a surviving mutant identifies either an assertion gap, equivalent behavior, unreachable code, or unsuitable mutation.

Use mutation score as diagnostic evidence, not a universal quality percentage. Review survivors individually and set CI break thresholds from an established baseline. Scope early adoption to changed or critical code to control runtime.

## Controls

- Run the unmodified suite first and stop on existing failures.
- Pin the mutation tool and configuration.
- Exclude generated code only with documented rationale.
- Investigate timeouts separately from genuine kills.
- Prevent blanket ignore rules from hiding weak tests.
- Ratchet thresholds gradually after reviewing equivalent mutants.

## Verification

1. Introduce a known weak assertion and confirm a survivor.
2. Strengthen the assertion and confirm the mutant is killed.
3. Repeat runs to detect nondeterministic outcomes.
4. Measure runtime and worker resource use.
5. Review threshold failures before changing the threshold.

## Sources

- [Stryker Mutator documentation](https://stryker-mutator.io/docs/)
- [StrykerJS configuration](https://stryker-mutator.io/docs/stryker-js/configuration/)
