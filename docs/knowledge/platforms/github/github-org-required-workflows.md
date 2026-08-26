# github-org-required-workflows

**Issue:** Security and compliance teams need guarantees like "no repository merges code without running our SAST/secret-scan/license workflow." Per-repo required status checks decay the moment a new repo is created without them. GitHub's organization ruleset rule "Require workflows to pass before merging" (public beta 2023, generally available since October 2023 for Enterprise plans) solves this: a workflow file living in a central `.github` repository runs against every targeted repo and its checks become merge-blocking. The feature is powerful but plan-gated and full of trigger and path semantics that break naive setups — this article captures how to deploy it correctly and what still requires the classic per-repo approach.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the Mechanism Works

1. **Ruleset-hosted, not per-repo.** You do not configure required workflows in each repository. An org admin creates an organization ruleset (Settings → Rules → Rulesets), adds the "Require workflows to pass before merging" rule, and references the workflow by filename plus the `.github` repo it lives in. Targeting uses the ruleset's standard repo selectors: all repos, patterns like `service-*`, or explicit lists, with exclusions.
2. **Central workflow, target checkout.** The referenced workflow executes in the context of each target repository (its branch, its `GITHUB_TOKEN`), even though the file itself is versioned in the org-wide `.github` repo. The workflow typically checks out the target repo explicitly to scan it.
3. **Merge gate semantics.** Once the ruleset is Active on a branch (default branch or patterns), pull requests targeting that branch cannot merge until the required workflow's check run succeeds. Bypass lists, merge queue interaction, and "evaluate" vs "active" modes behave like every other ruleset rule (see `github-rulesets-2026.md`).
4. **Enterprise plan gate.** Required workflows are available on GitHub Enterprise Cloud (and Enterprise Server); they do not exist for Free or Team orgs, where the fallback is a Terraform/gh-script that adds per-repo required checks plus new-repo templating.
5. **Multiple workflows compose.** A ruleset can require several workflows (SAST, secrets, license) and rulesets stack on the same branches; each contributes its own required check runs to the PR's merge box.

## Trigger and Path Semantics

1. **PR-centric triggers only.** Required workflows fire on `pull_request`, `pull_request_target`, and `merge_group` events — never on plain `push`. Anything that must run on push (deploy, nightly) still needs a repo-local workflow; do not try to smuggle it through the required-workflow rule.
2. **Skipped ≠ passed.** If the required workflow does not run for a given PR (path filters excluding everything, or the event never firing), its check stays pending and the PR is unmergeable — the same class of gotcha documented in `github-actions-self-hosted-runners-2026.md`. Never path-filter a required workflow to nothing; instead always run it and let an early change-detection job succeed fast.
3. **Reference the exact filename.** The rule binds to the workflow file's name in the `.github` repo (e.g., `compliance.yml`); renaming or restructuring that file breaks every protected PR in the org until the ruleset is updated. Treat renames as change-managed events with a checklist.
4. **Default-branch checkout of the central repo.** The workflow file is always read from the default branch of its home repository; changes to it take effect on the next PR evaluation, so the `.github` repo itself needs strict review protection — it is now org-wide supply chain.
5. **Forks and PRs from forks.** Required workflows run against fork PRs subject to the same first-time-contributor approval rules as any workflow; policy-compliance repos that accept outside PRs should pair the ruleset with an approval gate.

## Deployment Playbook

1. **Central `.github` repository first.** Consolidate org-wide workflows (SAST, secret scanning as defense-in-depth on top of push protection, SBOM, license check) into one `.github` repo with CODEOWNERS limited to the platform/security team and required reviews enforced.
2. **Evaluate mode rollout.** Create the ruleset in "Evaluate" state for one to two weeks; the eval status on PRs (not blocking) reveals repos where the workflow never triggers or fails, before anything blocks merges.
3. **Canary repos, then patterns.** Target one low-traffic service repo, fix fallout, widen to `*-service` patterns, then all repos. Keep a standing exclusion list (mirror repos, docs-only repos) with documented justification and expiry dates.
4. **Pair with enforcement bypass policy.** Decide who can bypass (break-glass role, not individuals) and alert on bypass usage via audit log streaming, same as other ruleset rules.
5. **Codify in IaC.** Rulesets are manageable via the REST rulesets API and Terraform's github_organization_ruleset resource; keep the required-workflow ruleset in code so its targeting and workflow references are reviewable and revertable.

## Fallbacks for Non-Enterprise Orgs

1. **Org-wide workflow templates.** Publish workflow snippets via the `.github` repo's workflow-templates directory so new repos scaffold the checks locally; combine with a repo template that has required checks pre-configured.
2. **Compliance sweep instead of gate.** A scheduled org-wide job enumerates repos (gh api `/orgs/{org}/repos`) and fails/alerts on any repo missing the required check in its branch protection — detection after the fact rather than prevention.
3. **Ruleset alternative via required checks.** Where only some repos matter, classic per-repo required status checks remain adequate; automate their presence with the same sweep script so new repos cannot drift.

## Pitfalls

1. **Silent org sprawl mismatch.** Patterns target repo names only; a team naming a service outside the pattern (typo, new prefix) escapes the gate — the compliance sweep from the fallback section is worth running even on Enterprise.
2. **Runaway minutes.** The required workflow runs on every PR of every targeted repo; keep it incremental (changed-file aware) or it becomes the org's largest CI line item (see `ci-budget-exhaustion-migration.md`).
3. **Rename breakage.** Renaming the central workflow file bricks merges org-wide; alert on edits to the `.github` repo and include ruleset review in the checklist for such PRs.
4. **merge_group duplication.** With merge queues enabled, the workflow can run twice (PR then merge_group); cache aggressively or scope expensive steps to the merge_group event only when the queue already revalidates.
