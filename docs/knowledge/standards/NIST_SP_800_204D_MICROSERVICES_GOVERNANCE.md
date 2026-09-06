# NIST SP 800-204D Microservices Security Strategies Governance

## Purpose

NIST SP 800-204D (February 2024, "Implementation of DevSecOps for a Microservices-based Application with Service Mesh") documents security strategies for microservices applications and the service mesh that fronts them. Governance ensures ORCHORDS microservices applications apply the documented strategies across the build, deploy, runtime, and observability stages, with the service mesh as the primary trust boundary.

## Current context and source status

SP 800-204D is part of the NIST 800-204 series that began with SP 800-204 (Security Strategies for Microservices-based Application Systems) and continues with SP 800-204A, B, C, D, and the under-development E. SP 800-204D focuses on DevSecOps practice and service mesh security integration. Treat the publication as normative guidance for any ORCHORDS microservices deployment that uses a service mesh; verify the current revision status before adopting.

## Governance workflow and controls

### 1. Service mesh as the trust boundary

- Treat the service mesh sidecar (or equivalent sidecar-free mesh data plane) as the primary trust boundary for inter-service traffic.
- Apply mTLS to every service-to-service call by default; require an explicit policy exception to opt out.
- Centralize policy authoring in the mesh control plane; treat policy as code.

### 2. Identity and authentication

- Issue a strong workload identity to every service via SPIFFE/SPIRE or a managed equivalent.
- Bind workload identity to the running binary and to the deployment metadata; rotate identity on schedule and on compromise.
- Do not rely on network location (IP, subnet, namespace alone) for authentication.

### 3. Authorization and policy

- Author service-to-service authorization policies as code in the mesh control plane.
- Default deny; allow only documented and reviewed flows.
- Apply namespace, label, and identity-based authorization in addition to path-based rules.

### 4. Secure build and supply chain

- Pin base images; rebuild and re-sign on every base-image update.
- Generate and verify SLSA provenance for every image.
- Sign every image with a documented signing identity; verify on admission.

### 5. Secure deployment

- Apply network policies alongside mesh policies; mesh authorization is necessary but not sufficient.
- Restrict egress from every service to documented destinations; alert on egress outside the policy.
- Use progressive delivery (canary, blue/green) with automated rollback on policy violation.

### 6. Runtime detection and observability

- Deploy runtime detection (eBPF, syscall, or mesh telemetry) per `FALCO_VERSION_GOVERNANCE.md` and per `OPENTELEMETRY_VERSION_GOVERNANCE.md`.
- Forward mesh audit logs and policy decisions to the SIEM with structured fields.
- Track mesh control-plane health as a first-class SLO.

### 7. Incident response and recovery

- Pre-stage isolation actions (namespace quarantine, identity revocation, mesh policy deny) for known compromise scenarios.
- Maintain a runbook that maps detection signal to mesh action.
- Rehearse isolation and recovery at least annually.

## Validation and evidence

- Capture a current service-mesh policy inventory and the most recent mesh-policy review.
- Capture mTLS coverage reports and any opt-out exceptions.
- Capture supply-chain verification evidence for the deployed image set.
- Capture the most recent incident-after-action report and the rehearsal schedule.

References: NIST SP 800-204D (February 2024); NIST SP 800-204 series; NIST SP 800-204C; SPIFFE/SPIRE specifications; SLSA framework.
