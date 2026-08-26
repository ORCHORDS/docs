# Container Image Security — Scanning, Hardening, and Supply-Chain Signing

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your CI pipeline builds a Docker image from `node:20` and pushes it
to the registry without scanning. A vulnerability report reveals the
base image contains 47 high-severity CVEs in OS packages your
application never uses. The container runs as root with write access
to the entire filesystem. A developer previously baked an API key
into a `RUN` command — the key persists in the image layer history
even after a subsequent `RUN rm` command. No one can verify whether
the image in production matches the one that passed CI.

## Context

Container security is a layered defense model: vulnerability scanning
(Trivy, Grype, Snyk Container) catches known CVEs, minimal base
images (distroless, scratch) reduce attack surface, multi-stage
builds strip build tools from production images, supply-chain signing
(Cosign/Sigstore) provides integrity verification, and runtime
security (Falco, seccomp, AppArmor) detects exploitation after
deployment. No single tool is sufficient — each layer addresses a
different threat. Scanning must happen before push (so vulnerable
images never reach the registry) and continuously after deployment
(new CVEs are published against unchanged images).

## Scanning tools

```
Tool            Scope                       Integration
──────────────────────────────────────────────────────────────
Trivy           OS packages, language deps, GitHub Actions,
(Aqua)          IaC misconfigs, secrets,    GitLab CI, CLI
                licenses — single binary

Grype           OS packages, language deps  Pairs with Syft
(Anchore)       — SBOM-driven deep          for SBOM-first
                dependency analysis         scanning

Snyk Container  OS packages, language deps  PR checks, base
                — adds base image upgrade   image upgrade
                recommendations             suggestions
```

```bash
# Trivy — scan and fail build on critical/high findings
trivy image myapp:latest \
  --severity CRITICAL,HIGH \
  --exit-code 1

# Grype — scan from SBOM
syft myapp:latest -o cyclonedx-json > sbom.json
grype sbom:sbom.json --fail-on high
```

## Minimal base images

```
Image type     Contents                Use case
──────────────────────────────────────────────────────────────
Full (debian,  OS + shell + package    Development, debugging
ubuntu, node)  manager + tools         (NOT production)

Alpine         Minimal OS + musl libc  Small footprint, some
               + apk package manager   compatibility issues

Distroless     App + runtime deps      Production runtimes
(gcr.io/       only — NO shell, NO     (Node.js, Java, Python,
distroless/*)  package manager         Go)

Scratch        Completely empty base   Statically linked
                                       binaries (Go, Rust)

Fewer packages = fewer CVEs = smaller image = faster pulls
```

## Multi-stage build pattern

```dockerfile
# Stage 1: Build (full SDK image)
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --production=false
COPY . .
RUN npm run build

# Stage 2: Production (minimal runtime)
FROM gcr.io/distroless/nodejs20-debian12
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
USER 1000
CMD ["dist/server.js"]
```

```
Multi-stage benefits:
  → Build tools, compilers, dev deps stripped from final image
  → Source code not included in production image
  → Final image contains only compiled artifacts + runtime
  → Typical size reduction: 1.2 GB → 150 MB
```

## Dockerfile hardening checklist

```
Security control         Implementation
──────────────────────────────────────────────────────────────
Non-root user            USER 1000 (or named user via adduser)
                         Never leave default root

Read-only filesystem     docker run --read-only
                         K8s: readOnlyRootFilesystem: true
                         Use tmpfs/volumes for writable paths

No secrets in layers     NEVER use ENV/ARG/COPY for secrets
                         Use BuildKit: RUN --mount=type=secret
                         Or runtime injection (Vault, K8s Secrets)

Pin base image digests   FROM alpine@sha256:abc123...
                         Not mutable tags (latest, 20, alpine)

Drop Linux capabilities  --cap-drop=ALL
                         Add back only what is needed

Minimal COPY scope       COPY specific files, not COPY . .
                         Use .dockerignore for .git, .env, etc.
```

## Image signing with Cosign/Sigstore

```
Keyless signing (CI/CD):

  1. Fulcio (Sigstore CA) issues short-lived certificate
  2. Certificate binds ephemeral keypair to OIDC identity
     (GitHub Actions OIDC token, Google, Microsoft)
  3. Image signed with ephemeral private key
  4. Private key discarded immediately after signing
  5. Signature recorded in Rekor (public transparency log)
  6. Verification relies on log entry, not key custody

Commands:
  # Sign (keyless, in CI)
  cosign sign --yes ghcr.io/org/app@sha256:abc123...

  # Verify (enforce at deploy time)
  cosign verify \
    --certificate-identity=https://github.com/org/app/.github/workflows/build.yml@refs/heads/main \
    --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
    ghcr.io/org/app

  Enforce via admission controllers:
    → Kyverno ClusterPolicy with cosign verification
    → OPA Gatekeeper with Sigstore constraints
    → Only signed images admitted to cluster
```

## SBOM generation

```
Generate:
  # Syft (CycloneDX format)
  syft myapp:latest -o cyclonedx-json > sbom.json

  # Trivy (CycloneDX format)
  trivy image myapp:latest --format cyclonedx > sbom.json

Attach as OCI attestation:
  cosign attest --predicate sbom.json \
    --type cyclonedx \
    ghcr.io/org/app@sha256:abc123...

Formats:
  CycloneDX — security-audit focused
  SPDX      — license-compliance focused

Continuously diff SBOMs to catch drift from
unpinned or rebuilt base images.
```

## Runtime security

```
Tool            Mechanism              Detects
──────────────────────────────────────────────────────────────
Falco           eBPF / kernel module   Unexpected shell spawn,
                                       sensitive file reads,
                                       outbound connections

seccomp         Syscall filtering      Blocks dangerous syscalls
                                       (Docker default blocks ~44)

AppArmor        Mandatory access       File/network/capability
                control profiles       access restrictions

Runtime security catches zero-days and misconfig exploitation
that build-time scanning cannot detect.
```

## CI/CD integration

```yaml
# GitHub Actions — Trivy scan with SARIF upload
- name: Scan image
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: 'myorg/myapp:${{ github.sha }}'
    format: 'sarif'
    output: 'trivy-results.sarif'
    severity: 'CRITICAL,HIGH'
    exit-code: '1'

- name: Upload scan results
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: 'trivy-results.sarif'
```

## Anti-patterns

- **Scanning only at build time** — new CVEs are published daily
  against unchanged images. Schedule regular re-scans of deployed
  images in the registry.
- **Trusting mutable tags** — `FROM node:20` resolves to different
  content over time. Pin digests (`FROM node:20@sha256:...`) for
  reproducibility and verifiable signing.
- **Broad `COPY . .` without `.dockerignore`** — copies `.git`,
  `.env`, credentials, and other sensitive files into the image
  layer history.
- **Signing without enforcement** — signing images with Cosign
  but not enforcing verification at deploy time (via Kyverno or
  Gatekeeper) makes signing decorative, not protective.
- **Scanning only application dependencies** — ignoring OS-level
  packages in the base image misses the majority of CVEs in
  full-distribution base images.

## Gotchas

- **Secrets persist in layer history** — even if a file is deleted
  in a later `RUN` command, it remains accessible in prior layers
  via `docker history` or layer extraction. Use BuildKit secret
  mounts, not ENV/COPY/ADD.
- **NVD enrichment delays** — NVD can be slow to enrich CVEs after
  initial publication. Use multiple vulnerability databases (OSV,
  GitHub Advisory, distro-specific) for faster coverage.
- **Distroless has no shell** — debugging requires `kubectl debug`
  ephemeral containers or copying a debug tool in. Plan debugging
  strategy before adopting distroless in production.
- **Alpine musl vs glibc** — some applications (especially those
  with native bindings) fail on Alpine due to musl libc
  incompatibilities. Test thoroughly before switching from
  Debian-based to Alpine-based images.

## Verification

- Trivy or Grype scans run before image push in CI.
- Base images pinned by digest, not mutable tag.
- Multi-stage builds strip build tools from production images.
- Containers run as non-root with read-only filesystem.
- No secrets in image layers (BuildKit secret mounts used).
- Images signed with Cosign and verification enforced at deploy.
- SBOM generated and attached as OCI attestation.
- Scheduled re-scans configured for deployed images.

## Related

- `documentation/categories/security/supply-chain-slsa-sigstore-verification.md`
- `documentation/categories/deploy/infrastructure-drift-detection-remediation.md`
- `documentation/categories/compliance/eu-cyber-resilience-act-cra-software.md`

## Source URLs (verified 2026-08-16)

- Sigstore Cosign — Signing Overview — https://docs.sigstore.dev/cosign/signing/overview/
- aquasecurity/trivy-action GitHub Action — https://github.com/aquasecurity/trivy-action
- AWS EKS Best Practices — Image Security — https://docs.aws.amazon.com/eks/latest/best-practices/image-security.html
- OSV.dev — Open Source Vulnerability Database — https://osv.dev/
