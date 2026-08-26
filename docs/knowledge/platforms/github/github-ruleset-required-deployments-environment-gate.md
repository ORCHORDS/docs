# GitHub ruleset required-deployments environment gate

**Issue:** A passing build does not prove that a specific commit was deployed successfully to a representative environment. GitHub’s required-deployments rule can block merging until changes are successfully deployed to selected environments, but an incorrectly triggered deployment or a mismatched environment can leave the rule ineffective or permanently pending.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Configure the rule on the repository’s targeted protected branch and select exact, governed environment names.
- Do not assume an organization-level ruleset can carry this rule; GitHub documents required deployments as unavailable for rulesets created at the organization level.
- Ensure the pre-merge workflow creates a deployment for the pull-request commit being evaluated and reports a terminal successful deployment status only after real verification.
- Protect the environment with appropriate branch or tag restrictions, reviewers, secrets, and deployment-protection rules.
- Keep deployment-success permission limited to trusted workflows or integrations and audit status writers.
- Avoid a circular trigger in which deployment begins only after the merge that the deployment gate blocks.
- Govern ruleset bypass actors and record any bypass as an exception.
- Define failure, cancellation, supersession, timeout, rollback, and environment-unavailable behavior.

## Implementation and tests

In a sandbox repository, require a staging environment and open a pull request. Verify merge is blocked before deployment, remains blocked for an in-progress or failed status, and becomes available only when the same candidate commit has a successful deployment to the exact environment.

Test an environment-name typo, renamed or deleted environment, deployment of the base SHA, deployment of an older head SHA, rerun after a force-push, unauthorized status attempt, canceled run, and bypass. Confirm the gate re-evaluates the latest pull-request head and retains auditable deployment evidence.

## Gotchas and applicability

This is a before-merge environment gate, not an approval inside a post-merge production job. A successful staging deployment proves only the checks represented by that environment. External side effects may already exist before merge, so use isolated resources and cleanup.

Ruleset and environment features vary by plan and GitHub product; verify the current target repository’s options.

## Official sources

- [GitHub Docs: Available rules for rulesets](https://docs.github.com/en/enterprise-cloud@latest/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-deployments-to-succeed-before-merging)
- [GitHub Docs: About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#about-branch-protection-settings)
