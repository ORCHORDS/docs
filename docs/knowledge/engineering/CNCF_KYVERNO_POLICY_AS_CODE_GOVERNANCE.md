# CNCF Kyverno Policy-as-Code Governance

## Purpose

CNCF Kyverno is a policy engine designed for Kubernetes. It allows policies to be expressed as Kubernetes resources, validated against resources, and used to mutate or generate resources. Governance ensures that policies are version-controlled, tested, and applied consistently across clusters.

## Current context and source status

Kyverno is a CNCF Incubating project. Versions and policy types (validate, mutate, generate, verifyImages, imageVerification) evolve; verify the current Kyverno documentation before treating any specific policy type or field as a current requirement.

## Governance workflow and controls

### 1. Adopt Kyverno as the policy engine

Adopt Kyverno as the policy engine for Kubernetes clusters. Apply Kyverno at cluster install time.

### 2. Define policies as code

Define policies as Kubernetes manifests. Store them in version control. Apply a code review process for policy changes.

### 3. Test policies

Test policies with the Kyverno CLI (Kyverno apply, Kyverno test) and with the test command. Maintain a test suite for each policy.

### 4. Apply mutation policies

Apply mutation policies for security defaults (e.g., adding resource limits, restricting capabilities, adding labels). Document the mutations.

### 5. Apply generation policies

Apply generation policies to bootstrap resources (e.g., default NetworkPolicies, default PodDisruptionBudgets).

### 6. Apply validation policies

Apply validation policies for security and compliance (e.g., disallow privileged containers, require image digests, enforce resource limits). Use audit and enforce modes.

### 7. Apply image verification

Apply image verification with cosign signatures. Configure trust roots. Reject unsigned images in enforce mode.

### 8. Apply policy exceptions

Apply policy exceptions (Kyverno PolicyException) where a violation is justified. Require owner and expiry.

### 9. Monitor policy compliance

Monitor policy compliance with the Kyverno policy reports. Report violations.

## Validation and evidence

- Policy repository.
- Test suite.
- Policy exception register.
- Compliance reports.

## Failure correction

Common defects include untested policies, missing exception governance, and policy reports that are not reviewed. Corrective actions include a CI gate on policy tests, an exception governance process, and a compliance review cadence.

## Limitations

- Kyverno is specific to Kubernetes.
- Some mutations may not be expressible; design limitations.
- Image verification requires signature infrastructure (cosign, Rekor).
- Policy performance depends on policy count and cluster size.

## Canonical sources

- CNCF, Kyverno documentation, current edition.
- CNCF, Kyverno CLI documentation, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the platforms leaf for Kubernetes platforms, the security leaf for pod security, and the operations leaf for compliance reporting.
