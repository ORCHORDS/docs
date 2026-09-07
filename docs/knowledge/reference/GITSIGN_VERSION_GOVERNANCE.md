---
title: Sigstore gitsign Commit Signing Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: Sigstore project (https://www.sigstore.dev/); gitsign 0.10.x (May 2024), 0.11.x (October 2024), 0.12.x (March 2025), 0.13.x (August 2025), 0.14.x (February 2026), 0.15.x (July 2026); Fulcio OIDC identity; Rekor inclusion proof; SSH and X.509 signature modes
---

# Sigstore gitsign Commit Signing Version Governance

## Scope

This card governs how `orchords-docs` evaluates Sigstore gitsign, the Git commit-signing tool that uses Fulcio for OIDC-issued short-lived certificates and Rekor for inclusion proofs. It is the reference input for any KB card that cites "keyless" or OIDC-bound Git commit signing, supply-chain attestation tied to a committer identity, or Git protection rules requiring signature verification.

## Why this card exists

gitsign eliminates the long-lived GPG/SSH signing key by binding each commit signature to a short-lived Fulcio certificate tied to the committer's OIDC identity. A KB card that asserts "commits are signed" without binding to a gitsign version, signature mode (SSH vs. X.509), Fulcio OIDC issuer, and Rekor inclusion policy produces commits whose signatures a third party cannot verify once the Fulcio root rotates, and whose signature can be silently bypassed if the Git hosting provider's protection rule misconfigures the verification predicate.

## Version support matrix (2026-09)

| gitsign | Released | EoL | Notes |
|---|---|---|---|
| 0.12.x | March 2025 | ~6 months after next minor | stable, X.509 default |
| 0.13.x | August 2025 | ~6 months after next minor | stable, SSH signature mode GA |
| 0.14.x | February 2026 | ~6 months after next minor | stable, native Rekor v2 client |
| 0.15.x | July 2026 | current | stable, multi-issuer Fulcio binding |

Policy:

- Support the current minor and the previous minor (N-1).
- The signature mode must be declared in the developer onboarding guide (X.509 default; SSH opt-in for hosts that do not yet verify X.509+Rekor).
- The OIDC issuer must match the developer's identity provider; verify on every workstation provisioning.
- Rekor inclusion proof must be persisted alongside the signature; treat missing inclusion as an unsigned commit.
- Upgrade window: ≤ 3 months after a new minor release.

## Signing and verification guidance

- Default to X.509+Rekor mode for new repositories.
- Use SSH mode only when the Git host (e.g. legacy self-hosted GitLab) cannot consume the X.509+Rekor predicate.
- For repository protection rules, require both a valid signature and a verifiable Rekor inclusion; do not accept either alone.
- On every workstation provisioning, run `gitsign verify` against a known commit to confirm the OIDC issuer and trust-root pin are current.
- Maintain a documented key-compromise response that names the Fulcio OIDC issuer and the Rekor shard used by the team.

## Compatibility notes

- gitsign follows Fulcio within ±1 minor and Rekor within ±1 minor.
- GitHub, GitLab, and Gitea require repository-protection-rule updates before any gitsign migration.
- SSH mode requires a per-developer SSH certificate authority configuration; document it in the developer onboarding guide.
- The native Rekor v2 client (gitsign 0.14+) requires Rekor 2.4.x or later.

References: `https://www.sigstore.dev/`, `https://github.com/sigstore/gitsign`, `https://github.com/sigstore/sigstore-go`, gitsign I-D `draft-meunier-sigstore-gitsign`.
