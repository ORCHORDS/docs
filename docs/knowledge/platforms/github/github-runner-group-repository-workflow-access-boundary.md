# GitHub Runner-Group Repository and Workflow Access Boundary

**Issue:** Labels route jobs by capability but do not authorize them. A broadly accessible runner group can let an unintended repository or workflow execute on privileged self-hosted infrastructure.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Use runner groups as the trust boundary and labels only for execution characteristics. Restrict each group to selected repositories whenever broad access is unnecessary.
- For Enterprise Cloud, restrict workflow access as well. Specify the full owner, repository, workflow path, and a fully qualified branch, tag, or preferably full commit SHA.
- Account for the rule that only jobs directly defined in an allowed workflow gain access; test reusable-workflow call chains explicitly.
- Use an enterprise-owned group when workflows from more than one organization need access; an organization-owned group cannot authorize workflows from another organization.
- Move newly registered runners out of the default group deliberately. A runner belongs to only one group at a time.
- Keep public and untrusted-fork workflows away from persistent or privileged self-hosted runners and review group membership and policy drift.

## Verification
- Queue jobs from an allowed workflow, a disallowed workflow in the same repository, and a disallowed repository; only the first can acquire the runner.
- Change a protected workflow ref and confirm a SHA-pinned allowlist does not silently follow it.
- Inventory group ownership, member runners, repository access, workflow access, and default-group residents on a schedule.

## Gotchas
A matching `runs-on` label does not grant access, and a restrictive label name is not a security control.

## Official sources
- https://docs.github.com/en/actions/concepts/runners/runner-groups
- https://docs.github.com/en/enterprise-cloud@latest/actions/how-tos/manage-runners/self-hosted-runners/manage-access
