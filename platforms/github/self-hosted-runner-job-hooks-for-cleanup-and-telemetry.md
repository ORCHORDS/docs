# Self-hosted runner job hooks for cleanup and telemetry

**Issue:** Persistent self-hosted runners can carry workspace residue, resource leaks, or incomplete telemetry between jobs, while workflow-authored cleanup is easy to skip after cancellation.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

GitHub Actions supports runner-administrator job management hooks configured with `ACTIONS_RUNNER_HOOK_JOB_STARTED` and `ACTIONS_RUNNER_HOOK_JOB_COMPLETED`. Use them for host-owned setup, observation, and cleanup that must sit outside repository workflow definitions.

Hooks execute on the runner host and therefore belong to a privileged administrative trust boundary. Keep them minimal, versioned, time-bounded, and independent of untrusted workflow data. A hook must not weaken or skip the repository's required checks.

## Operational controls

- Store hook scripts outside workflow-writable paths and restrict ownership and permissions.
- Avoid printing environment variables, tokens, or job payloads.
- Put destructive cleanup behind exact validated workspace and container labels; never use broad paths or unresolved variables.
- Bound hook duration and make failures observable.
- Preserve required diagnostics before cleanup.
- Roll out to a canary runner group and keep a tested disable path.
- Pair hooks with ephemeral runners where stronger job isolation is required.

## Verification

1. Exercise successful, failed, timed-out, and cancelled jobs.
2. Confirm start and completion telemetry contains no secrets.
3. Verify cleanup affects only resources belonging to the completed job.
4. Deliberately fail a hook and confirm runner and check behavior match policy.
5. Run consecutive hostile test jobs and confirm no workspace or process state crosses the boundary.

## Sources

- [GitHub Docs: Running scripts before or after a job](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/run-scripts)
- [GitHub Docs: Self-hosted runners reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)
- [GitHub Docs: Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
