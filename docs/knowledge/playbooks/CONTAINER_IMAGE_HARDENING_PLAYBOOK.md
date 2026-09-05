# Container Image Hardening Playbook

## Purpose

Harden container images end-to-end: base image selection, multi-stage build, vulnerability scanning, signing, and runtime hardening. Aligns with NIST SP 800-190 § 4 (Image Countermeasure) and CIS Docker Benchmark v1.6.

## Audience

Platform engineers, application developers, security engineers.

## Pre-conditions

1. The reference cards are current: `OCI_RUNTIME_VERSION_GOVERNANCE.md`, `NIST_SP_800_190_DOCKER_GOVERNANCE.md`, `SLSA_VERSION_GOVERNANCE.md`.
2. The container build pipeline is wired (Docker, BuildKit, ko, Buildpacks).
3. The container registry is wired (GHCR, ECR, ACR, GAR, Quay, Harbor).
4. The image signing tool is configured (cosign, Notation).
5. The image scanning tool is configured (Trivy, Grype, Clair).

## Procedure

### 1. Base image selection

1. Use a minimal base image:
   - `distroless` (Google): no shell, no package manager.
   - `alpine`: small, musl libc.
   - `scratch`: empty base; for Go binaries.
   - `wolfi` (Chainguard): minimal, hardened.
2. Pin the base image by digest: `FROM gcr.io/distroless/base-debian12@sha256:abc123`.
3. Audit the base image for known CVEs before adopting.

### 2. Multi-stage build

1. Use multi-stage builds:
   ```dockerfile
   # Build stage
   FROM golang:1.23 AS build
   WORKDIR /app
   COPY . .
   RUN go build -o myapp

   # Runtime stage
   FROM gcr.io/distroless/base-debian12
   COPY --from=build /app/myapp /myapp
   ENTRYPOINT ["/myapp"]
   ```
2. The runtime image contains only the compiled binary and minimal dependencies.
3. Build tools, package managers, and shells are excluded from the runtime image.

### 3. Vulnerability scanning

1. Run Trivy / Grype / Clair on every image push.
2. Block promotion on Critical / High CVEs.
3. Document CVEs that cannot be remediated (false positives, accepted risks).
4. Generate SBOM (SPDX or CycloneDX).
5. Store SBOM in the registry alongside the image.

### 4. Image signing

1. Sign with cosign (Sigstore):
   ```bash
   cosign sign --key cosign.key ghcr.io/org/myapp:v1.0.0
   ```
2. Sign with keyless mode using OIDC (preferred for CI):
   ```bash
   cosign sign ghcr.io/org/myapp:v1.0.0
   ```
3. Publish the public key (cosign.pub) or use OIDC trust root.
4. Configure the admission controller to verify the signature:
   - Kyverno: `verifyImages` rule.
   - OPA Gatekeeper: image signature verification.
   - Connaisseur: signature verification admission webhook.

### 5. Image provenance (SLSA)

1. Generate SLSA Build Level provenance.
2. Sign provenance with cosign:
   ```bash
   cosign sign --key cosign.key --predicate <provenance.json> --type slsaprovenance ghcr.io/org/myapp:v1.0.0
   ```
3. Verify provenance in the admission pipeline.

### 6. Runtime hardening

1. Run as non-root:
   ```dockerfile
   USER 65532:65532
   ```
2. Read-only root filesystem:
   ```yaml
   securityContext:
     readOnlyRootFilesystem: true
   ```
3. Drop all capabilities:
   ```yaml
   securityContext:
     capabilities:
       drop:
         - ALL
   ```
4. Add only required capabilities:
   ```yaml
   capabilities:
     drop:
       - ALL
     add:
       - NET_BIND_SERVICE
   ```
5. Disable privilege escalation:
   ```yaml
   securityContext:
     allowPrivilegeEscalation: false
   ```
6. Set resource limits:
   ```yaml
   resources:
     limits:
       cpu: "1"
       memory: 512Mi
     requests:
       cpu: 100m
       memory: 128Mi
   ```
7. Apply seccomp profile:
   ```yaml
   securityContext:
     seccompProfile:
       type: RuntimeDefault
   ```

### 7. Audit

1. Run `docker scout` or `dive` on every image to verify the layers.
2. Run `kube-bench` on the cluster to verify Pod Security Standards conformance.
3. Run `falco` (runtime threat detection) on the cluster.

## Rollback

Rollback of an image promotion:

1. Identify the bad image (e.g., a CVE that was missed).
2. Revert the deployment to the previous image tag.
3. Investigate the scanning / signing failure.
4. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## Mandatory pre-flight (before adopting a new container image)

1. Base image is from a trusted source.
2. Multi-stage build is used.
3. Image is scanned.
4. Image is signed.
5. Runtime hardening is configured.
6. SBOM is published.
7. Provenance is signed.

## References

- `OCI_RUNTIME_VERSION_GOVERNANCE.md`
- `NIST_SP_800_190_DOCKER_GOVERNANCE.md`
- `SLSA_VERSION_GOVERNANCE.md`
- cosign: `https://github.com/sigstore/cosign`
- Trivy: `https://github.com/aquasecurity/trivy`
- Kyverno: `https://kyverno.io/`
- CIS Docker Benchmark: `https://www.cisecurity.org/benchmark/docker`
