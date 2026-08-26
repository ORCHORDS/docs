# GitHub Actions Workflow Dependency Locking (2026)

## Overview
Workflow dependency locking is a 2026 GitHub Actions security roadmap feature
that pins reusable workflows, composite actions, and the transitive graph of
actions they call to a verified, reviewable state. It is the CI equivalent of a
package lockfile: once a workflow is reviewed and approved, subsequent runs
will not silently pick up a new version of a referenced action, reusable
workflow, or nested action unless the lock is explicitly updated and re-approved.

This closes the gap between "I reviewed the workflow" and "what actually ran",
which has historically been the highest-impact Actions supply-chain blind spot.

## Symptom
You open a PR that only changes application code, but the Actions run executes a
different version of a reusable workflow than the one your security team
approved last quarter. Symptoms include:
- A reusable workflow in `./.github/workflows/` begins behaving differently
  even though no commit touched the workflow file.
- `pull_request_target` runs an action whose `@main` ref was force-pushed by a
  compromised maintainer upstream.
- An audit shows a job that referenced `org/reusable-workflow/.github/workflows/ci.yml@main`
  resolved to a commit SHA no one on your team recognizes.
- A dependency-review-action pass is green but the action that performed the
  review was itself swapped.

## Gotchas
- `@main`, `@master`, and `@v1` floating refs are resolved at run time, not at
  review time. Locking only helps if the lock is enforced; reviewing a PR with
  a floating ref and then relying on the ref is still dangerous.
- Lockfiles are per-workflow and per-job. A reusable workflow called from
  another repo has its own lock surface; locking your caller workflow does not
  lock what the callee resolves unless it also opts in.
- The lock is only as trustworthy as the signing/attestation behind it. Pair
  dependency locking with artifact attestations (`actions/attest-build-provenance`)
  so the locked ref is bound to a reviewed build provenance.
- Lock updates must go through the same review path as the original workflow.
  Automation that auto-bumps locks on a schedule (analogous to Dependabot)
  can re-introduce the exact risk locking is meant to prevent if those PRs are
  auto-merged.
- Fork-PR runs are a special case: the lock applies to the base ref, but
  workflow files from the fork's branch are what actually run for
  `pull_request` events. Confirm which event your critical jobs use.

## How It Works
A lock entry records the resolved commit SHA for every action and reusable
workflow reference reachable from a workflow run, plus the digest of any
composite action's `action.yml`. At run time, Actions compares the live
resolution against the lock and fails closed (or warns, per policy) on drift.

```yaml
# .github/workflows/locked-ci.yml
name: Locked CI
on: [pull_request]

# The lock policy is declared at workflow scope and inherited by jobs.
lock-policy:
  mode: enforce              # enforce | warn | off
  scope: transitive          # direct | transitive
  update-branch: deps/lock   # auto-PR target when drift is detected

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4            # resolved + locked
      - uses: ./.github/actions/build        # local composite, digest-locked
      - uses: secure-org/reusable-deploy/.github/workflows/deploy.yml@main
                                          # ^ transitive ref, locked to a SHA
```

## Verifying and Updating the Lock
- `gh actions-lock verify` (or the equivalent in the Actions UI) reports any
  reference whose resolved SHA differs from the lock.
- `gh actions-lock update --commit <sha>` updates a single entry; prefer this
  over bulk re-locking so reviewers can see exactly what changed.
- Require lock-file changes to be reviewed by a CODEOWNER for
  `.github/actions-lock.json`.

## Pairing With Other Controls
Dependency locking is one layer. Combine it with:
- SHA pinning of first-party action refs (see
  `actions-policy-sha-pinning-and-blocklists-2026.md`).
- `pull_request_target` avoidance, or strict path filtering if unavoidable
  (see `github-actions-path-filters.md`).
- Dependency review action for third-party packages
  (`github-dependency-review.md`).
- Build provenance attestations
  (`github-actions-artifact-attestations.md`).

## Common Failure Modes
1. **Lock drift on reusable workflows from other orgs.** The other org retags
   `@v1` to a new commit; your lock catches it but your job now fails. Treat
   the failure as a feature, not noise — investigate before updating.
2. **Self-hosted runner cache.** A cached action layer on a self-hosted runner
   can mask drift because the runner serves the old bits. Purge the
   `~/.cache/actions` equivalent when debugging lock issues.
3. **Dispatched runs bypass the lock.** `workflow_dispatch` with manual inputs
   may skip the enforce path depending on policy. Verify the policy applies to
   all event types you use.

## Summary
Workflow dependency locking converts "I think what ran is what I reviewed" into
"what ran is cryptographically bound to what I reviewed." Adopt it on any
workflow that deploys, signs artifacts, or runs with elevated secrets first,
then roll out to the rest.
