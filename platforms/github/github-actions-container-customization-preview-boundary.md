# GitHub Actions Container Customization Preview Boundary

**Issue:** Container hooks replace the runner's normal job-container lifecycle. A hanging or incomplete hook can block all jobs, leak networks and credentials, or skip the isolation checks the default runtime supplied.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Treat container customization as a public-preview dependency and pin a tested runner version and hook implementation. It is available only on Linux self-hosted runners.
- Set `ACTIONS_RUNNER_CONTAINER_HOOKS` to an absolute path outside the runner application directory; the script executes with the runner service account's authority.
- Implement and contract-test `prepare_job`, `cleanup_job`, `run_container_step`, and `run_script_step` JSON commands, including response-file state and exit codes.
- Make `cleanup_job` idempotent and able to remove containers, pods, networks, mounts, and temporary credentials after partial preparation.
- Add an internal timeout and watchdog because GitHub documents no timeout setting for the hook script, which runs synchronously and blocks the job.
- Set `ACTIONS_RUNNER_REQUIRE_JOB_CONTAINER=true` when policy requires every job to use the customized container path; otherwise non-container jobs can bypass it.

## Verification
- Test success, pull failure, health-check failure, cancelled job, runner restart, and hook timeout with an empty host before production rollout.
- Confirm stdout and stderr stream to the job log without exposing registry credentials or environment secrets.
- After every scenario, assert no orphaned container, network, mount, pod, or credential remains.

## Gotchas
The example `actions/runner-container-hooks` scripts are starting points for testing, not a production suitability guarantee.

## Official sources
- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/customize-containers
- https://github.com/actions/runner-container-hooks
