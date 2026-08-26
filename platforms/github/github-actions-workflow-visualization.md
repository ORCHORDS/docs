# github-actions-workflow-visualization

**Issue:** Using GitHub's workflow graph and tooling to understand complex workflow job dependencies
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workflows with many jobs and dependencies are hard to reason about from YAML alone. Visualisation helps identify bottlenecks and unnecessary sequencing.

## Pattern / Solution
Built-in: GitHub renders a job dependency graph under the Actions run detail page. Each job box shows duration, and dependencies are drawn as arrows.

Dependencies drive the graph:
```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
  test:
    needs: lint
  build:
    needs: test
  deploy:
    needs: build
```
Optimise by parallelising independent jobs:
```yaml
jobs:
  test-unit:
    runs-on: ubuntu-latest
  test-integration:
    runs-on: ubuntu-latest
  lint:
    runs-on: ubuntu-latest
  build:
    needs: [test-unit, test-integration, lint]
```
Validate syntax locally:
```bash
brew install actionlint
actionlint .github/workflows/*.yml
```

## Gotchas
- `needs` creates a hard dependency — if a needed job is skipped, the dependent job is also skipped by default.
- Use `if: always()` on a job to run it even if dependencies fail or skip.
- The visual graph only shows the current run — use the workflow YAML for design-time analysis.
- Long chains create a critical path that determines minimum total runtime.

## Related
- `github-actions-cancel-redundant.md`
- `github-actions-timeout-jobs.md`
- `github-actions-monorepo-affected.md`
