# supply-chain-integrity-sigstore

**Issue:** Unsigned artifacts in CI/CD pipelines allow tampered packages to reach production undetected
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Build artifacts (container images, npm packages, binaries) published without cryptographic signatures can be tampered with between build and deployment. Sigstore provides keyless, identity-based signing tied to OIDC tokens from CI providers.

## Pattern / Solution
```bash
# Sign a container image with cosign (Sigstore)
cosign sign --key cosign.key ghcr.io/org/app:sha-abc123

# Keyless signing using OIDC (GitHub Actions — no long-lived keys)
cosign sign ghcr.io/org/app:sha-abc123
# Uses GitHub Actions OIDC token automatically

# Verify before deployment
cosign verify --certificate-identity=https://github.com/org/app/.github/workflows/release.yml@refs/heads/main \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  ghcr.io/org/app:sha-abc123
```
```bash
# Sign npm packages with provenance (npm 9.5+)
npm publish --provenance
# Embeds SLSA provenance + Sigstore signature into package
```

## Gotchas
- Keyless signing stores signatures in the public Rekor transparency log — don't sign private/confidential artifacts this way.
- Policy enforcement (OPA Gatekeeper, Kyverno) must be configured to reject unsigned images in Kubernetes.
- Signature verification must happen at deploy time, not just at build time.
- `cosign verify` failures are silent unless your admission controller or deploy script checks exit codes.

## Related
- `dependency-confusion-attack.md`
- `container-image-signing.md`
- `slsa-supply-chain.md`
