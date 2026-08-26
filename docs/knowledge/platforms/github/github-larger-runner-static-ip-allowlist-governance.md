# GitHub Larger-Runner Static-IP Allowlist Governance

**Issue:** Allowlisting dynamic GitHub-hosted runner addresses is brittle. Larger-runner static ranges can narrow network access, but a shared runner pool still creates a broad workload trust boundary.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use static IP ranges only where GitHub Enterprise Cloud and the runner platform support them.
- Dedicate runner groups and ranges by trust tier and destination sensitivity rather than sharing one allowlist broadly.
- Restrict repository access to each runner group and minimize outbound destination privileges.
- Track assigned ranges as configuration, monitor changes, and remove them when a runner pool is retired.

## Verification

- Run an authorized workflow and verify destination access from every address in the assigned range.
- Run a repository outside the allowed runner group and confirm it cannot select the runner.
- Rotate or recreate a pool and verify stale firewall entries are removed.

## Gotchas

- A larger runner is an autoscaling pool, not one fixed machine; all addresses in its assigned range are usable.
- macOS larger runners do not support static IP addresses.

## Official sources

- https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/manage-larger-runners
- https://docs.github.com/en/actions/reference/runners/larger-runners
