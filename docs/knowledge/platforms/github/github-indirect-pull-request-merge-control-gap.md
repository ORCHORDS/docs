# GitHub indirect pull-request merge control gap

**Issue:** GitHub can mark a pull request merged when its head commits become reachable from the base branch outside that pull request—for example, through another pull request or a direct push to the default branch. The indirectly merged pull request can show `merged` even though its own branch-protection requirements were not satisfied.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Treat the pull-request `merged` boolean as repository state, not proof that that pull request passed reviews, checks, conversations, deployment gates, or merge-queue policy.
- Block direct pushes to protected default and release branches for ordinary actors, including administrators where the risk model requires it.
- Define a stacked-pull-request policy: dependency direction, allowed merge method, review scope, required checks, and how superseded pull requests are closed.
- Make release and compliance automation verify the incorporated commit, required checks, approvals, provenance, and actual base-branch reachability.
- Detect newly merged pull requests whose merge path or audit evidence does not match an approved merge event, and route them for review.
- Minimize ruleset and branch-protection bypass actors and alert on their pushes.
- Preserve the default-branch ref update, actor, commit graph, related pull requests, check suites, reviews, and merge method.

## Implementation and tests

Create two test pull requests where the second contains the first pull request’s commits. Merge the containing pull request with each supported merge method and observe whether the first is marked indirectly merged. Separately test an authorized direct default-branch push in a sandbox. Confirm automation distinguishes the indirect state and does not emit a false “all controls passed” assertion.

Exercise a failed required check, pending review, unresolved conversation, and missing deployment on the indirectly merged pull request. Verify the release gate evaluates the commit that entered the protected branch rather than trusting the secondary pull request state.

## Gotchas and applicability

Reachability depends on commit topology and merge method. Squash or rebase can create different commits, so test the configured repository behavior. Closing a pull request is not equivalent to reverting commits that already reached the base branch.

GitHub calls this uncommon, but the consequence matters wherever merged-state events drive deployment, ticket closure, compliance evidence, or billing.

## Official sources

- [GitHub Docs: Pull request merges—indirect merges](https://docs.github.com/en/pull-requests/reference/pull-request-merges#indirect-merges)
- [GitHub Docs: Deploying code](https://docs.github.com/en/pull-requests/concepts/deploying-code)
