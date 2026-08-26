# container-image-signing

**Issue:** Container images deployed without signature verification allow malicious or tampered images into production
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Supply chain attacks targeting container registries can substitute legitimate images with backdoored versions. Without signature verification at admission time, these images run with full pod privileges inside Kubernetes clusters.

## Pattern / Solution
```yaml
# Kubernetes — Kyverno policy to enforce signed images
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: require-image-signatures
spec:
  validationFailureAction: Enforce
  rules:
    - name: verify-image-signature
      match:
        any:
          - resources:
              kinds: [Pod]
      verifyImages:
        - imageReferences: ["ghcr.io/org/*"]
          attestors:
            - count: 1
              entries:
                - keyless:
                    subject: "https://github.com/org/*"
                    issuer: "https://token.actions.githubusercontent.com"
```
```bash
# Docker Content Trust (older alternative)
export DOCKER_CONTENT_TRUST=1
docker pull org/app:latest  # fails if not signed
```

## Gotchas
- Image tags are mutable — pin by digest (`image@sha256:...`) in production manifests.
- Signed images must be verified at every pull point — including init containers and sidecars.
- Rotating signing keys requires re-signing all existing image tags or they fail verification.
- Private registries need Cosign configured with registry credentials for verification.

## Related
- `supply-chain-integrity-sigstore.md`
- `container-security-2026.md`
- `sbom-vulnerability-scanning.md`
