# GitHub Actions Reusable Workflow Permission Inheritance

Reusable workflows (`workflow_call`) are the recommended way to share CI/CD
logic across repos. They introduce a subtle but critical security boundary:
**the caller's `permissions:` and the called workflow's `permissions:` interact
in non-obvious ways**, and a misconfiguration can silently strip needed scopes
(causing mysterious failures) or leak excess scopes to untrusted callers.

## Symptom

- A reusable workflow worked perfectly when tested in its own repo, but when a
  caller invokes it, the job fails with `Error: Resource not accessible by
  integration` (HTTP 403 from the GitHub API).
- A caller workflow that should only have read access to the repo is able to
  push commits or create releases through the reusable workflow — the
  `permissions:` block in the caller was ignored.
- A security audit flags that your reusable workflow grants `contents: write`
  to all callers, but only 2 of 20 callers actually need it.
- You added `permissions: {}` (read-all-revoked) to a caller, expecting the
  reusable workflow to run read-only, but it still successfully pushed a tag.
- The `GITHUB_TOKEN` inside the reusable workflow has a different scope set
  than the same job had before you refactored it into a reusable workflow.

## Why it happens

GitHub's token scoping rules for reusable workflows are:

1. **The caller workflow's `permissions:` sets the maximum available scopes**
   for the `GITHUB_TOKEN` passed into the called workflow.
2. **The called workflow's `permissions:` can only restrict, never expand**,
   the scopes it receives from the caller.
3. **If the caller specifies no `permissions:`**, the token uses the repo/org
   default (often `contents: write` and `pull-requests: write` on classic
   repos) — the called workflow inherits this broad scope silently.
4. **If the called workflow specifies no `permissions:`**, it inherits whatever
   the caller passed, which may be broader than intended.

The danger: a reusable workflow designed to publish releases (`contents: write`)
can be called by any repo that links it. If the caller has a broad default
token, the reusable workflow silently gets write access even if the caller's
maintainer didn't realize it.

## Fix

1. **Always set explicit `permissions:` in both caller and called workflow.**
   The caller defines the ceiling; the called workflow should declare exactly
   what it needs:
   ```yaml
   # caller
   jobs:
     ci:
       uses: org/shared-workflows/.github/workflows/ci.yml@v2
       permissions: { contents: read, checks: write }
   ```
   ```yaml
   # called workflow
   on: { workflow_call: {} }
   permissions: { contents: read, checks: write }
   ```

2. **In the called workflow, set `permissions:` to the minimum that works.**
   Never leave it unset — an unset block inherits whatever the caller passed.

3. **Document required caller permissions** in the workflow's README or
   `workflow_call` inputs so caller maintainers know required scopes upfront.

4. **Use `secrets: inherit` carefully.** It forwards **all** caller secrets,
   including ones the called workflow doesn't need. Prefer explicit mapping:
   `secrets: { deploy-token: ${{ secrets.DEPLOY_TOKEN }} }`.

## Gotchas

- `permissions: {}` (empty object) in the **caller** revokes all token scopes,
  including read — the called workflow will fail on even a basic `actions/
  checkout`. Use `permissions: { contents: read }` as a safe minimum.
- The `id-token: write` permission needed for OIDC federation **must be set on
  the caller**, not just the called workflow — setting it only on the called
  workflow has no effect, because the caller's ceiling doesn't include it.
- A reusable workflow called via `workflow_call` **cannot call another reusable
  workflow** beyond 4 levels of nesting — GitHub silently fails the 5th-level
  call with a generic error.
- The `GITHUB_TOKEN` in a reusable workflow is **the caller's token**, not a
  fresh one — rate limits, IP allow-list membership, and enterprise policies
  all follow the caller repo, not the repo hosting the shared workflow.
- `permissions:` blocks are **not merged** between caller and called — the
   called workflow's block completely replaces what it would have inherited.
- Self-hosted runner groups used by a called workflow must be **accessible to
  the caller repo** — a shared workflow referencing `runs-on: [self-hosted,
  prod]` will fail if the caller isn't in that runner group.
- GitHub's 2026 Actions security roadmap pushes **"secure by default" reusable
  workflows** — expect the current "inherit if unset" behavior to tighten; pin
  shared workflow versions (`@v1`, `@<commit-sha>`) to avoid surprise breakage.

## Sources

- [Reusing workflows (GitHub Docs)](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [Permissions for the GITHUB_TOKEN (GitHub Docs)](https://docs.github.com/en/actions/security-guides/automatic-token-authentication)
- [What's coming to our GitHub Actions 2026 security roadmap (GitHub Blog)](https://github.blog/news-insights/product-news/whats-coming-to-our-github-actions-2026-security-roadmap/)
- [Security hardening for GitHub Actions (GitHub Docs)](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [Reusable workflows vs composite actions (Adrian Moftakhar / community)](https://github.blog/2022-02-10-use-reusable-workflows-to-avoid-duplication/)
