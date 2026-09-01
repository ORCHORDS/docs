# GitHub Actions Cache Trust Boundaries

## Purpose

GitHub Actions dependency caches improve workflow speed, but restored cache contents are not signed or verified. A workflow that restores a poisoned cache can execute attacker-controlled files if cached paths contain build tools, generated scripts, package-manager state, or other executable content.

## Current GitHub cache model

GitHub scopes caches primarily by branch or tag, not by workflow or job identity. A workflow run can restore caches from its current branch and the default branch. Pull-request workflows can also restore caches from the base branch, including pull requests from forks.

Caches created by `pull_request` runs are scoped to the pull request merge ref and cannot normally be restored by the base branch or unrelated pull requests.

For low-trust events that resolve to the default branch, GitHub restricts cache writes. Events such as `pull_request_target`, `issue_comment`, and `workflow_run` can read default-branch caches but cannot create or overwrite caches in that default-branch scope. GitHub recommends restore-only cache operations when that is the intended behavior.

## Governance pattern

1. Treat every restored cache as untrusted input.
2. Never store secrets, tokens, private keys, credentials, or other sensitive values in cached paths.
3. Limit cache writes to trusted workflow triggers and hardened jobs.
4. Prefer restore-only behavior for low-trust workflows that need performance benefits but should not influence later privileged jobs.
5. Include dependency-lock or other integrity-relevant inputs in cache keys where practical.
6. Keep privileged workflows capable of regenerating dependencies when a cache is absent or rejected.
7. Delete caches after a known poisoning event, compromised workflow, or major build-toolchain change.
8. Review shared cache keys across workflows; branch scoping does not isolate caches by job purpose.

## Base-branch readability

Because pull requests can read base-branch caches, cache data must be safe for contributors who can open pull requests to access indirectly. This is a confidentiality boundary, not only an integrity concern.

A cache should therefore contain reproducible or public build material, not internal configuration or credentials.

## Cache poisoning

Low-trust cache poisoning becomes dangerous when a later trusted workflow restores attacker-influenced files and executes or trusts them. GitHub's default-branch write restrictions reduce this risk, but custom workflow behavior and caches written from trusted-but-compromised events still require review.

## Failure modes

- Storing credentials in a cache can expose them to pull-request workflows.
- Assuming cache content is authenticated because GitHub stored it creates false trust.
- Using broad restore prefixes can restore older or less-specific content than expected.
- Sharing one cache key across unrelated workflow purposes can cross security boundaries.
- Ignoring cache-save warnings on low-trust triggers can hide a mistaken workflow design.

## Sources

- GitHub Docs — Dependency caching reference: https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- GitHub Docs — Dependency caching concepts: https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching
- GitHub Docs — Managing caches: https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manage-caches

## Scope note

This article covers GitHub Actions cache security and access boundaries. Package-manager integrity, artifact signing, and dependency verification remain separate controls.