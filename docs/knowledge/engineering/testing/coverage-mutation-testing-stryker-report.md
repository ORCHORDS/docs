# Coverage Mutation Testing Stryker Report

Line and branch coverage answer the question *was this line executed?* — a question that a
test suite of `assert(true)` can pass perfectly. Mutation testing asks the harder question:
*if this line were wrong, would the test suite notice?* A mutation testing tool introduces
small, behaviour-preserving changes (mutants) into the code under test, runs the test suite
against each mutant, and reports which mutants were *killed* (a test failed) and which
*survived* (the suite did not notice). The surviving mutants are the gaps. Stryker for
JavaScript and TypeScript is the dominant implementation: the mutation score, the per-mutant
report, and the threshold configuration are the artefacts that turn mutation testing from a
research activity into an engineering gate.

## Scope

Covers the production use of Stryker in a JavaScript or TypeScript repository: project
configuration, mutation operators and their equivalence classes, the interpretation of the
Stryker report, the integration of mutation score thresholds into CI, and the follow-through
on surviving mutants. Does not cover the academic foundations of mutation testing, other
mutation tools (PIT, Mull, Cosmic-Ray), or non-mutation quality signals such as property-based
or fuzz testing.

## Workflow or implementation guidance

1. **Start from a small, focused scope.** Running Stryker on the whole codebase on the first
   attempt produces a report too large to triage and a CI run too long to be useful. Begin
   with a directory the team owns, where line coverage is already above 80%, and where
   coverage gaps have historically been a problem. The report is a quality artefact, not a
   vanity metric; a small high-quality report beats a large noisy one.
2. **Pick the mutation operators deliberately.** Stryker's mutators include `Arithmetic`,
   `Array`, `Block`, `Boolean`, `Conditional`, `Equality`, `Logical`, `Object`, `String`,
   `Unary`, and others. Each operator generates mutants of a specific shape. Choosing
   operators is choosing which defects to look for: `Conditional` and `Boolean` catch
   predicate inversions and dead branches, `Arithmetic` catches off-by-one and operator
   mistakes, `Equality` catches `==` versus `===` regressions. The set should reflect the
   defects the team has actually shipped, not the full default set.
3. **Configure mutator equivalence.** Two mutants are *equivalent* if no test can distinguish
   them — for example, `a < b` mutated to `a <= b` when `b` is never equal to `a` in the
   test inputs. Stryker cannot detect all equivalences automatically; the team must mark
   equivalent mutants by hand, with the rationale recorded. A surviving mutant that is
   actually equivalent should be marked as such in the report, not silently left to inflate
   the apparent gap.
4. **Treat the report as a backlog, not as a pass/fail.** A first Stryker run typically
   surfaces dozens of surviving mutants. Categorise each one:
   - *Test gap*: a real test would have killed the mutant; write one.
   - *Dead code*: the mutated line is unreachable in production paths; delete the code or
     write a test that demonstrates it.
   - *Equivalent*: the mutant produces the same observable behaviour; mark it equivalent.
   - *Trivial*: `String` mutants that produce an obviously wrong string; ignore only after
     explicit review.
5. **Wire a mutation score threshold into CI.** Stryker's `thresholds` configuration sets a
   minimum mutation score (for example, `high: 80`, `low: 60`, `break: 50`). The `break`
   threshold fails the build. Set thresholds based on the team's current score, not on an
   aspirational number: a threshold that the codebase cannot meet today is a CI that turns
   red on every push until someone tunes it down. Tune it up as the gap closes.
6. **Capture the HTML report as an artefact.** Stryker produces a per-mutant HTML report
   that engineers can navigate. Persist the report for each CI run; reviewing the diff of
   reports between runs shows whether the score improved because tests were added or because
   mutants were marked equivalent.
7. **Re-run on PR that touches uncovered code.** A PR that introduces a function with no
   tests is precisely the PR where Stryker's signal is most valuable. Running Stryker on the
   PR's diff, or at least on the changed files, catches the regression before merge.
8. **Use incremental mode for large codebases.** Stryker's incremental mode only re-mutates
   files that changed since the last full run. The full run is the baseline; the incremental
   runs keep the signal fresh without a multi-hour pipeline stage.

A representative Stryker configuration for a TypeScript service:

```json
{
  "mutate": ["src/**/*.ts", "!src/**/*.test.ts"],
  "mutator": { "name": "javascript", "excludedMutations": ["StringLiteral"] },
  "thresholds": { "high": 80, "low": 60, "break": 50 },
  "reporters": ["html", "json", "clear-text"]
}
```

The `html` reporter is persisted as a build artefact; the `clear-text` reporter surfaces the
score in the CI log.

## Controls

- Stryker configuration committed to the repository; changes to mutation operators or
  thresholds reviewed like any production change.
- Mutation score threshold wired into CI; the build fails when the threshold is missed.
- Per-mutant report archived per CI run, with the diff between successive runs reviewable.
- Equivalent mutants are explicitly tagged with a rationale; the count of tagged mutants is
  monitored to prevent over-tagging.
- A triage backlog of surviving mutants, owned by the team, with the same review cadence as
  the regular test backlog.

## Validation evidence

- A deliberate mutation injected by hand into a file under test is killed by the test suite
  in CI; the Stryker run on the same code shows the mutant as killed.
- The mutation score trends upward over time without a corresponding drop in line coverage,
  indicating genuine test improvement rather than test deletion.
- A PR that deletes a test reduces the mutation score, even if line coverage remains high —
  the suite notices the missing test because mutants that were killed are now surviving.
- The equivalent-mutant tagging rate stays within an expected range; an unusually high rate
  is reviewed.

## Failure modes and correction

- *Score stuck because tests are tautological.* Replace `assert(true)`-style tests with
  assertions that exercise the mutated behaviour; line coverage cannot help here, mutation
  testing can.
- *Threshold set above what the suite can meet.* Lower the threshold and tune up over time;
  a CI that is always red is a CI that gets disabled.
- *Mutation operators too broad.* The CI runs for hours and most mutants are trivial. Limit
  operators, exclude generated code, and use incremental mode.
- *Surviving mutants all equivalent.* Tag them with rationale; the score is then comparable
  across runs.
- *Report not reviewed.* The HTML report is the artefact that converts a number into action;
  if no one opens it, the score is decoration.
- *Mutation testing run only on `main`.* Mutations introduced by a PR are caught after merge.
  Run Stryker on the PR or on the diff, not only on the merged branch.

## Limitations

- Mutation testing is slow. A full run can take orders of magnitude longer than the test
  suite itself; incremental mode and reduced operators are mitigations, not eliminations.
- Mutation testing cannot find defects that no small mutation can introduce. Algorithmic
  errors, design flaws, and concurrency bugs require other techniques.
- Equivalent mutants are a long-standing problem; even with explicit tagging, the score is
  an under-estimate of test quality.
- Mutation testing reports the gap; it does not write the missing test. A failing mutant is
  a task on a backlog, not a finished improvement.
- Threshold-driven gates discourage nuanced interpretation of the report. A 60% score with
  critical mutants surviving is worse than a 70% score with no critical mutants surviving;
  treat the report as a prioritisation input, not a single number.

## Canonical sources

- Stryker Mutator, *Stryker documentation* (configuration, mutators, incremental mode, and
  threshold semantics): https://stryker-mutator.io/docs/
- Stryker Mutator, *Stryker JS getting started*: https://stryker-mutator.io/docs/stryker-js/getting-started/
- Stryker Mutator, *Stryker JS configuration reference*:
  https://stryker-mutator.io/docs/stryker-js/configuration/
