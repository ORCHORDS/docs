# NIST SP 800-207 Zero Trust Architecture Governance

## Purpose

NIST SP 800-207 defines Zero Trust Architecture (ZTA), an enterprise cybersecurity approach where no implicit trust is granted to assets or users based solely on network location. Governance ensures that an enterprise transitioning to ZTA defines its abstract architecture, selects components that map to the architecture, and applies a defense-in-depth posture across the enterprise.

## Current context and source status

NIST SP 800-207 was published in August 2020. NIST subsequently published SP 800-207A (Zero Trust Architecture Model for Access Control in Cloud-Native Applications in Multi-Location Environments) and a Zero Trust Cybersecurity Framework profile. Verify the current NIST publications before treating any specific control or component as a current requirement.

## Governance workflow and controls

### 1. Apply the abstract architecture

Apply the ZTA abstract architecture components: Policy Engine (PE), Policy Administrator (PA), Policy Enforcement Point (PEP). Map your chosen components (identity provider, device inventory, SIEM, SOAR, NAC, API gateway, microsegmentation) to the abstract components.

### 2. Adopt core principles

Adopt the core principles:

- resources are accessed over open networks;
- communication is secured regardless of network location;
- access is granted per session;
- access is determined by dynamic policy including client identity, application, requested asset, and behavioral attributes;
- the enterprise monitors and measures integrity and security posture;
- all resource authentication and authorization are dynamic and strictly enforced.

### 3. Define trust algorithms

Define trust algorithms that combine subject identity, device posture, requested asset, and behavioral attributes. Document the algorithm.

### 4. Implement per-session access

Implement per-session access. Re-authenticate and re-authorize for high-risk actions. Limit session duration.

### 5. Implement continuous monitoring

Implement continuous monitoring of integrity and security posture. Alert on posture deviations.

### 6. Apply defense in depth

Apply defense in depth. ZTA complements, rather than replaces, layered controls.

### 7. Use the Zero Trust Cybersecurity Framework profile

Use the Zero Trust Cybersecurity Framework profile to map ZTA capabilities to existing security controls.

## Validation and evidence

- ZTA architecture diagram.
- Component-to-abstract mapping.
- Trust algorithm documentation.
- Continuous monitoring reports.

## Failure correction

Common defects include implicit trust based on network location, missing continuous monitoring, and per-session access not implemented. Corrective actions include a network segmentation review, a continuous monitoring deployment, and a session enforcement review.

## Limitations

- ZTA is a journey; full implementation takes years.
- SP 800-207 does not prescribe specific products.
- Some legacy systems cannot meet ZTA requirements without modification.
- ZTA depends on accurate identity, device, and posture data.

## Canonical sources

- NIST SP 800-207, Zero Trust Architecture, 2020.
- NIST SP 800-207A, Zero Trust Architecture Model for Access Control in Cloud-Native Applications in Multi-Location Environments, 2023 (or current edition).
- NIST Cybersecurity Framework Zero Trust profile, current edition.

## Scope note

This article belongs to the reference leaf and cross-references the security leaf for access control, the platforms leaf for identity and access management, and the engineering leaf for application architecture.
