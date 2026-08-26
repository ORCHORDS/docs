# github-commit-signing-verification

**Issue:** Commit metadata is trivially forgeable — nothing in plain Git binds an author name/email to the human who wrote the code. Supply-chain guidance (SLSA, internal audit, and the 2025 enterprise baseline) therefore pushes orgs toward signed commits and GitHub's Verified badge. But enforcement without a plan breaks every bot: CI committers, Dependabot/Renovate, release automation, and developer machines without signing configured all start failing `GH009` push rejections the day a ruleset requires signatures. This article covers the signing methods available in 2025-2026, which to standardize on for humans versus automation, and how to enforce without a week of breakage.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Signing Method Landscape

1. **SSH signing (humans-first).** Since Git 2.34, any SSH key can sign commits; developers add it under Settings → SSH and GPG keys with type "Signing key" and set `git config gpg.format ssh`. It reuses keys developers already have, works offline, and GitHub docs list GPG/SSH as the best choice for most individuals — the lowest-friction default for an org rollout.
2. **GPG (the incumbent).** Traditional and still common in enterprise; the burden is key generation, expiry management, and revocation certificates. Fine where a key-management practice exists, painful where it does not.
3. **gitsign keyless (Sigstore).** The sigstore/gitsign helper signs commits and tags keylessly using an ephemeral certificate bound to your GitHub OIDC identity; nothing long-lived to protect or rotate. Trade-offs: signing requires internet (OIDC round-trip), verification depends on Sigstore/Fulcio infrastructure, and offline or air-gapped workflows do not fit it.
4. **Password-manager and platform keys.** 1Password, YubiKey-backed GPG/SSH, and similar tooling sign via the SSH format; centralize on SSH-format signing and these integrate without extra policy.
5. **Bots and GitHub Apps.** Commits created with an App's installation token (or via the REST contents API) are not automatically GPG-signed; they need their own signing identity or an exemption strategy — the single most common source of breakage when signature rules turn on (already flagged in `github-rulesets-2026.md`).

## Enforcement Mechanics

1. **Rulesets, not legacy branch protection.** The "Require signed commits" rule (ruleset rule type `required_signatures`) applies to target branches; GitHub verifies signatures at push time and rejects unsigned pushes. Legacy branch protection offers the same rule but org-level rulesets let you target `*` once with bypass lists instead of configuring every repo.
2. **Verified badge semantics.** The badge appears when the signature is cryptographically valid and the key is associated with the verified email on the signer's GitHub account; a valid signature from an unregistered key shows "Unverified" — onboarding must include uploading keys, not just creating them.
3. **Vigilant mode.** Personal setting that flags unsigned commits even when not enforced, showing "Unverified" prominently for accounts with it on; useful as an org-awareness phase before hard enforcement.
4. **Merge strategy interplay.** Squash merges are re-signed by GitHub (showing Verified via GitHub's web-flow key); merge commits preserve child commit signatures only if the merge itself is signed locally. Standardize: enforce signing on feature branches and let squash-merge handle the final commit.
5. **Tags and releases.** Tag signing (`git tag -s` or gitsign) is separate from commit signing; release automation that creates tags in CI needs the same signing setup as commits or its tags show unsigned.

## Rollout Playbook

1. **Inventory signers first.** Enumerate everything that pushes: developers (SSH/GPG adoption), CI jobs (bot identity), Dependabot/Renovate (bot PRs), release automation (tags). Each gets a signing path or an explicit bypass before enforcement.
2. **SSH default for humans.** Publish a one-page setup (config lines, key upload as Signing key, `commit.gpgsign true`) and verify via the Verified badge on a test commit in each team; treat missing badges as onboarding bugs, not user error.
3. **gitsign for CI and bots.** In Actions, install gitsign and sign commits created by workflows (version bumps, generated code, release commits) using the workflow's OIDC identity — no stored secrets, and signatures attest to the job identity, dovetailing with artifact attestation practices (`github-actions-artifact-attestations.md`).
4. **Staged enforcement.** Evaluate-mode ruleset → vigilant-mode awareness → active enforcement on one service repo → org-wide pattern, mirroring the required-workflows rollout; keep a break-glass bypass role and audit every bypass.
5. **Verify in review.** Train reviewers that Verified is a precondition for merge on protected branches (the badge is visible in the commit list); for high-assurance repos, add a CI verification step (`git verify-commit` with published keys or gitsign's cosign-based verify) so history tampering fails a check.

## Pitfalls

1. **The bot wall.** Turning on required signatures breaks Dependabot/Renovate/auto-merge bots that push unsigned commits; configure their signing (or rely on squash-merge re-signing) before enforcement, and expect the fix window to be measured in days.
2. **Key rotation gaps.** Rotated or expired GPG keys turn old history "Unverified" retroactively; SSH signing with long-lived keys or gitsign's re-verification model avoids most churn, but preserve revoked keys where history validation matters.
3. **Email mismatch.** Signing with a key whose identity does not match the account's verified email yields valid-but-unverified commits; enforce corporate email verification before rollout.
4. **Offline workflows.** gitsign requires connectivity; air-gapped or restricted-egress runners (see `github-actions-egress-firewall.md`) need an egress allowance to Sigstore endpoints or an SSH/GPG fallback identity for the bot.
5. **Signature ≠ review.** Signing proves identity, not approval quality; pair it with CODEOWNERS and required reviews rather than treating Verified as the whole supply-chain story.
