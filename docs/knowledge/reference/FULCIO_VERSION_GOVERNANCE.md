---
title: Sigstore Fulcio Certificate Authority Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: Sigstore project (https://www.sigstore.dev/); CNCF graduated Fulcio 1.4.x (October 2024), 1.5.x (February 2025), 1.6.x (June 2025), 1.7.x (November 2025), 1.8.x (March 2026), 1.9.x (July 2026); Fulcio OIDC issuance; trust root in TUF (sigstore-root); OIDC issuers (GitHub Actions, GitLab, Google, Buildkite)
---

# Sigstore Fulcio Certificate Authority Version Governance

## Scope

This card governs how `orchords-docs` evaluates Sigstore Fulcio, the short-lived, OIDC-bound signing certificate authority used by Cosign keyless signing and gitsign. It is the reference input for any KB card that cites OIDC-issuance flows, keyless signature verification, or trust-root rotation.

## Why this card exists

Fulcio issues X.509 code-signing certificates bound to an OIDC identity (e.g. `https://github.com/<org>/<repo>/.github/workflows/release.yml@refs/tags/v1.2.3`). A KB card that signs "keyless" but does not bind to a Fulcio version, OIDC issuer allow-list, and trust-root pin produces certificates whose identity claims cannot be re-verified once Fulcio rotates its root. Without a documented issuer scope, a CI job that successfully signs may still produce a certificate whose OIDC claim is rejected by the verifier.

## Version support matrix (2026-09)

| Fulcio | Released | EoL | Notes |
|---|---|---|---|
| 1.6.x | June 2025 | ~6 months after next minor | stable, OIDC claim profile v1 |
| 1.7.x | November 2025 | ~6 months after next minor | stable, certificate transparency log |
| 1.8.x | March 2026 | ~6 months after next minor | stable, OIDC claim profile v2 |
| 1.9.x | July 2026 | current | stable, multi-issuer per workload identity |

Policy:

- Support the current minor and the previous minor (N-1).
- Pin the Fulcio trust root via the sigstore-root TUF repository; never pin by raw PEM in long-lived configuration.
- OIDC issuer allow-lists must enumerate exact issuer URLs and required claims per workload identity.
- Certificate transparency inclusion is required for production issuance; treat absence as a release-blocker.
- Upgrade window: ≤ 3 months after a new minor release.

## OIDC issuer scope guidance

- Allow only the OIDC issuer that the workload identity federates with (e.g. GitHub Actions → `https://token.actions.githubusercontent.com`).
- Require the OIDC claim `sub` to match the expected workflow identity pattern; reject wildcard matches in production.
- For multi-cloud deployments, declare an explicit allow-list per cloud provider; do not rely on issuer default.
- Document the Fulcio issuance policy in a `fulcio-policy.yaml` next to the workload identity configuration.

## Trust-root and revocation guidance

- Track sigstore-root TUF updates; consume root rotations through the TUF client, never by file replace.
- Treat a compromised Fulcio intermediate as a certificate-transparency event, not as a Cosign event.
- Plan a keyless-signing pause during an active root rotation; document the pause and re-baseline on resume.
- Maintain a mirror of the TUF root metadata for air-gapped verifiers; re-sync on every release-train bump.

## Compatibility notes

- Cosign 2.x+ and Cosign 3.x follow Fulcio within ±1 minor.
- Rekor checkpoint observation is required at every Fulcio certificate-issuance event.
- The OIDC claim profile v2 (Fulcio 1.8.x+) requires verifiers updated to Cosign 2.4+ and sigstore-go 0.5+.
- Self-hosted Fulcio deployments must mirror the upstream CT log or run a private CT log with public inclusion proof availability.

References: `https://www.sigstore.dev/`, `https://github.com/sigstore/fulcio`, `https://github.com/sigstore/sigstore-root`, Fulcio I-D `draft-davidson-sigstore-fulcio`.
