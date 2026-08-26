# GitHub Actions Dynamic Matrix and Fail-Fast Strategies

The `strategy.matrix` lets one job fan out across many configurations (OS,
language version, browser, etc.). Most teams hard-code the matrix or disable
`fail-fast` without understanding the tradeoffs. This article covers generating
matrices dynamically from code/data, tuning `fail-fast` and `max-parallel`, and
debugging the common silent-failure and over-cancellation problems.

## Symptom

- A matrix job with 20 cells cancels all remaining cells the moment cell #2
  fails, hiding 18 real results and making it look like everything is broken.
- You added a new runtime version (e.g., Node 22) and had to edit the workflow
  YAML in five places to add it to the matrix — or worse, you forgot one.
- A matrix cell fails intermittently (flaky E2E, network) and the team cannot
  re-run just that one cell, only the whole matrix.
- A dynamic matrix (generated from a script) sometimes produces zero cells,
  causing the job to be silently skipped with a confusing "This job was
  skipped" status that does not fail the workflow.
- `max-parallel` is set too low (e.g., 1) and a 30-cell matrix takes 40 minutes
  to complete, bottlenecking the whole pipeline.

## Fix

1. **Tune `fail-fast` deliberately, not by default.** The default `true`
   cancels all in-progress and pending jobs on the first failure. For CI
   matrices where each cell is independent (OS/Node versions), set
   `fail-fast: false` to see all failures at once. Keep `true` for
   expensive integrated jobs (deploy pipelines) where the first failure makes
   the rest pointless — the default saves compute minutes.

2. **Generate the matrix dynamically from code or JSON** to avoid hand-editing
   YAML. Emit JSON from a job, consume it via `fromJson()`:
   ```yaml
   jobs:
     detect:
       outputs:
         matrix: ${{ steps.set.outputs.matrix }}
       steps:
         - id: set
           run: echo "matrix=$(jq -c '{node: .versions}' versions.json)" >> $GITHUB_OUTPUT
     test:
       needs: detect
       strategy:
         fail-fast: false
         matrix: ${{ fromJson(needs.detect.outputs.matrix) }}
       steps:
         - run: echo "Testing Node ${{ matrix.node }}"
   ```

3. **Use `matrix.include`/`matrix.exclude`** to add specific combos without
   exploding the cross-product, or remove impossible combos. Note: `include`
   with a key already in the cross-product **replaces** that cell rather than
   merging — the generated cell is dropped silently.

4. **Set `max-parallel` based on your concurrency limits.** If you hit API rate
   limits or external service limits (e.g., SauceLabs browser slots), cap it:
   `strategy: { max-parallel: 4 }`. This is a **per-job** setting — two matrix
   jobs running concurrently each get their own budget.

5. **Handle the empty-matrix case explicitly.** A dynamic matrix that resolves
   to `{}` causes the job to be skipped. If skipping should fail the workflow:
   ```yaml
   - if: ${{ needs.detect.outputs.matrix == '{}' }}
     run: exit 1
   ```

## Gotchas

- `fail-fast: false` means you pay for **all** matrix cells even if cell #1 is a
  real failure — on a 50-cell billable matrix this can be expensive. Weigh
  debugging visibility against cost.
- **You cannot re-run a single matrix cell** via the UI "Re-run failed jobs"
  button in older GitHub versions. The "Re-run only failed jobs" option requires
  Actions runner version 2.297+; verify it is available on your enterprise.
- `matrix.include` with a key that already exists in the cross-product
  **replaces** that cell rather than merging — if your include has the same
  `os`+`node` as a generated combo, the generated cell is dropped silently.
- A dynamic matrix job whose generator script fails (exit non-zero) will cause
  `needs.detect` to fail, but the downstream `test` job with
  `matrix: ${{ fromJson(...) }}` will show a cryptic "Invalid matrix
  'object'" error instead of pointing at the real script failure.
- `max-parallel` is a **per-job** setting, not global — two matrix jobs running
  concurrently each get their own `max-parallel` budget, so total runner usage
  can still spike.
- Matrix variable names must be valid identifiers (lowercase, no dashes).
  `matrix.my-os` is invalid YAML reference syntax; use `matrix.my_os`.
- Windows matrix cells are roughly **2x more expensive** (billing multiplier)
  than Linux for the same job — a 3-OS matrix costs ~5/3 of a Linux-only one.
- If a matrix cell exceeds its `timeout-minutes`, GitHub cancels **only that
  cell** (good), but if `fail-fast: true`, it also cancels siblings (bad).

## Sources

- [Using a matrix for your jobs (GitHub Docs)](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs)
- [Jobs strategy reference (GitHub Docs)](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idstrategy)
- [Dynamic matrix generation examples (GitHub Actions community)](https://github.com/orgs/community/discussions/26634)
- [GitHub Actions billing and execution time (GitHub Docs)](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
