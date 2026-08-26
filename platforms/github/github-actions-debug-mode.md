# github-actions-debug-mode

**Issue:** Enabling debug logging in GitHub Actions to diagnose failing workflows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workflow logs sometimes lack enough detail to diagnose failures. Debug mode adds verbose step-level and runner-level output.

## Pattern / Solution
Enable for a single re-run:
- Click "Re-run jobs" → "Enable debug logging" in the GitHub UI.

Enable via secrets (persists across runs):
```
Repository secret: <redacted-secret> = true
Repository secret: <redacted-secret> = true
```
Print debug messages in steps:
```bash
echo "::debug::Variable value is $MY_VAR"
echo "::notice::Deployment started at $(date)"
echo "::warning::Config file not found, using defaults"
echo "::error::Required secret is missing"
```
Group log output:
```bash
echo "::group::Installing dependencies"
npm ci
echo "::endgroup::"
```

## Gotchas
- `ACTIONS_STEP_DEBUG` outputs each shell command before executing it (like `set -x`).
- `ACTIONS_RUNNER_DEBUG` outputs runner-level diagnostic information (environment, PATH, etc.).
- Debug logs are not shown by default even when enabled — select "Debug" in the log level filter.
- Debug secrets should be removed after investigation; they add noise to every subsequent run.
- Workflow commands (`::debug::`) are printed in the log but are not searchable by default in the UI.

## Related
- `github-actions-timeout-jobs.md`
- `github-actions-workflow-visualization.md`
