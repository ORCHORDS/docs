# container-security-2026

**Issue:** Container security — image, registry, runtime, K8s
**Date:** 2026-08-09
**Status:** documented

## Symptom
Log4Shell is in your base image. Containers run as
root. The registry is unauthenticated. A pod has
docker.sock mounted. The auditor is paged. You wish
you had layered security.

## Root cause
**Containers are attack targets.** Use 6 layers.

**Source:** Orca Security 2026 + OX Security 2026.

## The "6 pillars" pattern

For container security:
1. **Image security** — Scan + minimal + sign
2. **Registry security** — Private + signed
3. **Build-time / IaC** — Dockerfile + K8s manifest
4. **Kubernetes hardening** — CIS + PSS + RBAC
5. **Runtime security** — Falco + eBPF
6. **Response & forensics** — Audit + runbook

The 6 pillars are comprehensive.

## The "minimal base image" pattern

For base images:
- **Distroless:** No shell, no package manager
- **Alpine:** Small (5 MB), musl libc
- **Scratch:** Empty (Go binaries)
- **Chainguard:** Distroless + auto-rebuild
- **Avoid:** ubuntu:latest, debian:latest

The image is minimal.

**CVE count:** Distroless ~40 vs Debian 400+.

## The "multi-stage build" pattern

For Dockerfile:
```dockerfile
# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Runtime stage
FROM gcr.io/distroless/nodejs20-debian12
COPY --from=builder /app/dist /app
USER 10001
EXPOSE 3000
CMD ["/app/server.js"]
```

The build is multi-stage.

## The "non-root" pattern

For non-root:
```dockerfile
RUN addgroup --system app && \
    adduser --system --ingroup app app
USER app
```

Or K8s:
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
```

The root is dropped.

## The "read-only rootfs" pattern

For filesystem:
```yaml
securityContext:
  readOnlyRootFilesystem: true
volumes:
  - name: tmp
    emptyDir: {}
volumeMounts:
  - name: tmp
    mountPath: /tmp
```

The rootfs is read-only.

## The "drop capabilities" pattern

For capabilities:
```yaml
securityContext:
  capabilities:
    drop:
      - ALL
    add:
      - NET_BIND_SERVICE  # Only if needed
```

The caps are dropped.

## The "pin by digest" pattern

For image pinning:
```dockerfile
# ❌ Bad: mutable tag
FROM node:20

# ✅ Good: immutable digest
FROM node@sha256:abc123...
```

The digest is pinned.

## The "image scanning" pattern

For scanning:
- **Trivy:** OSS, fast, default
- **Grype:** Anchore, fast
- **Snyk:** SaaS, reachability
- **OX Security:** ASPM, exploit-aware

The scanner is per choice.

## The "Trivy in CI" pattern

For CI:
```yaml
- name: Trivy scan
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: 'myregistry/app:${{ github.sha }}'
    format: 'sarif'
    output: 'trivy.sarif'
    severity: 'CRITICAL,HIGH'
    exit-code: '1'
    ignore-unfixed: true
```

The CI scans on build.

## The "Cosign signing" pattern

For signing:
```bash
# Sign
cosign sign --key cosign.key myregistry/app:tag

# Verify
cosign verify --key cosign.pub myregistry/app:tag
```

The image is signed.

## The "Cosign at admission" pattern

For K8s:
- **Kyverno:** Policy to require signature
- **OPA Gatekeeper:** Rego policy
- **Connaisseur:** Cosign-native
- **Kubewarden:** Webhook

The admission verifies.

## The "SBOM" pattern

For SBOM:
- **Format:** CycloneDX or SPDX
- **Generate:** Syft, Trivy, Docker SBOM
- **Attach:** To image
- **Required for:** FedRAMP, EU CRA

The SBOM is generated.

## The "rebuild on update" pattern

For base image updates:
- **Webhook:** Registry → CI
- **Trigger:** On base image push
- **Re-test:** All dependent images
- **Period:** Weekly

The rebuild is automated.

## The "Pod Security Standards" pattern

For K8s PSS:
- **Privileged:** Unrestricted
- **Baseline:** Minimal restrictions
- **Restricted:** Hardened (default)

Apply at namespace:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: my-ns
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

The standard is enforced.

## The "NetworkPolicy default deny" pattern

For network:
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  # No rules = deny all
```

Then explicit allows per service.

The default is deny.

## The "RBAC least-privilege" pattern

For RBAC:
- **No cluster-admin:** On app ServiceAccounts
- **Per namespace:** Bound
- **Audit:** With rbac-tool, krane
- **Workload identity:** EKS Pod ID, IRSA, GKE WIF

The RBAC is minimal.

## The "workload identity" pattern

For cloud access:
- **AWS:** IRSA, EKS Pod Identity
- **GCP:** Workload Identity Federation
- **Azure:** Entra Workload ID
- **Replace:** Long-lived keys

The identity is federated.

## The "Falco runtime" pattern

For runtime:
- **Falco:** Behavioral detection
- **Tetragon:** eBPF-based
- **Sysdig:** SaaS
- **Aqua:** Enterprise
- **Detects:** Process spawn, network, FS

The runtime is monitored.

## The "Falco example" pattern

For rule:
```yaml
- rule: Unexpected process in container
  desc: Detect unexpected process spawned in container
  condition: >
    spawned_process and
    container and
    not proc.name in (allowed_processes)
  output: >
    Unexpected process in container
    (user=%user.name command=%proc.cmdline container=%container.name)
  priority: WARNING
```

The rule detects.

## The "Kubernetes hardening" pattern

For hardening:
- [ ] Pod Security Standards (restricted)
- [ ] Anonymous auth disabled
- [ ] RBAC least-privilege
- [ ] Default-deny NetworkPolicies
- [ ] Encrypted etcd
- [ ] Short-lived certs
- [ ] Admission control (OPA/Kyverno)
- [ ] Audit logging
- [ ] Kubelet restricted
- [ ] Dedicated node pools
- [ ] External secrets (Vault, ASM)
- [ ] kube-bench quarterly

The cluster is hardened.

## The "registry security" pattern

For registry:
- **Auth required:** For all ops
- **Vuln scan at push:** Block on critical
- **Signature verify at pull:** Cosign
- **Audit log:** All operations
- **Private:** No public

The registry is locked.

## The "incident response" pattern

For K8s IR:
1. **Preserve:** Snapshot FS + process list
2. **Capture:** Audit logs (pre-incident)
3. **Identify:** Image digest → CI run
4. **Roll back:** Image
5. **Forensic:** Before terminating

The IR is documented.

## The "secrets in layers" anti-pattern

For secrets:
- **Issue:** .env in COPY
- **Fix:** BuildKit secret mounts
- **Or:** Runtime injection

The secrets are not baked.

## The "root user" anti-pattern

For root:
- **Issue:** Container root = host root
- **Fix:** USER 10001

The user is non-root.

## The "privileged" anti-pattern

For privileged:
- **Issue:** Container escape
- **Fix:** allowPrivilegeEscalation: false

The escalation is blocked.

## The "docker.sock" anti-pattern

For docker.sock:
- **Issue:** Container control of host
- **Fix:** Never mount

The socket is never mounted.

## The "public registry" anti-pattern

For public:
- **Issue:** Supply chain attack
- **Fix:** Private + signed

The registry is private.

## The "30-day plan" pattern

For starting:
- **Week 1:** Visibility (Trivy + SBOM)
- **Week 2:** Image hardening (distroless + USER)
- **Week 3:** K8s hardening (PSS + NetPol)
- **Week 4:** Runtime + supply chain (Falco + Cosign)

The plan is staged.

## The "reachability" pattern

For scanning:
- **Default:** All CVEs
- **Reachability:** Only called code
- **Cuts noise:** 60-80%
- **Tools:** Snyk, OX, Mend

The scan is reachable.

## The "container security checklist" pattern

For checklist:
- [ ] Distroless / minimal base
- [ ] Multi-stage build
- [ ] Non-root USER
- [ ] readOnlyRootFilesystem
- [ ] Drop ALL capabilities
- [ ] Pin by digest
- [ ] Trivy in CI (fail on critical)
- [ ] Cosign signed
- [ ] SBOM generated
- [ ] PSS restricted
- [ ] Default-deny NetworkPolicy
- [ ] RBAC least-privilege
- [ ] Workload identity (no static keys)
- [ ] Falco runtime
- [ ] IR runbook

The checklist is 15.

## Verification
- **Test:** Trivy passes
- **Test:** Cosign verifies
- **Test:** PSS restricted
- **Test:** NetworkPolicy default-deny
- **Test:** Falco detects anomaly
- **Audit:** Quarterly

## Gotchas
- **The "root user" anti-pattern.** USER 10001.
- **The "docker.sock" anti-pattern.** Never mount.
- **The "public registry" anti-pattern.** Private.

## Related
- `cloudflare/containers-best-practices.md`
- `security/owasp-top-10-2025.md`
- `security/slsa-supply-chain.md`
- `security/sql-injection-deep-dive.md`
- `infra/iac-best-practices.md`
- `infra/iac-testing-2026.md`
- OX Security: https://www.ox.security/blog/container-security-best-practices/
- Orca Security: https://orca.security/resources/blog/container-security-best-practices/
- SaaS Security: https://www.saassecurity.io/blog/container-security
