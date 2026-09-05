---
title: ISO/IEC 25010:2011 Systems and Software Quality Requirements and Evaluation Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 25010:2011 (March 2011) — Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — System and software quality models; https://www.iso.org/standard/35733.html
---

# ISO/IEC 25010:2011 Systems and Software Quality Requirements and Evaluation Governance

## Scope

This card governs how `orchords-docs` evaluates systems and software quality against ISO/IEC 25010:2011. It is the reference input for any KB card that touches software quality attributes, quality characteristics, or quality-in-use metrics.

## Why this card exists

ISO/IEC 25010 defines the canonical eight quality characteristics: functional suitability, performance efficiency, compatibility, usability, reliability, security, maintainability, portability. Without an explicit card, the KB cites quality attributes that the auditor cannot reconcile to the standard.

## Document set

- **ISO/IEC 25010:2011** (March 2011) — System and software quality models.
- **ISO/IEC 25040** — Quality evaluation process.
- **ISO/IEC 25045** — Quality evaluation for software products.

References: `https://www.iso.org/standard/35733.html`.

## Quality model

ISO/IEC 25010:2011 defines the eight quality characteristics and 31 sub-characteristics:

### 1. Functional suitability

- Functional completeness
- Functional correctness
- Functional appropriateness

### 2. Performance efficiency

- Time behavior
- Resource utilization
- Capacity

### 3. Compatibility

- Co-existence
- Interoperability

### 4. Usability

- Appropriateness recognizability
- Learnability
- Operability
- User error protection
- User interface aesthetics
- Accessibility

### 5. Reliability

- Maturity
- Availability
- Fault tolerance
- Recoverability

### 6. Security

- Confidentiality
- Integrity
- Non-repudiation
- Authenticity
- Accountability
- Resistance

### 7. Maintainability

- Modularity
- Reusability
- Analyzability
- Modifiability
- Testability

### 8. Portability

- Adaptability
- Installability
- Replaceability

## Quality-in-use model

ISO/IEC 25010:2011 also defines the quality-in-use model with five characteristics:

- Effectiveness
- Efficiency
- Satisfaction
- Freedom from risk
- Context coverage

## Mandatory pre-flight (before adopting a new quality attribute)

1. The characteristic and sub-characteristic are identified.
2. The metric is defined.
3. The target is declared.
4. The measurement is wired.

## Cross-reference

| Domain | Card |
|---|---|
| Security | `NIST_SP_800_53_R5_SECURITY_GOVERNANCE.md`, `ISO_IEC_27001` (deferred) |
| Performance | (deferred) |
| Reliability | `POSTGRES_VERSION_GOVERNANCE.md`, `ETCD_VERSION_GOVERNANCE.md` |
| Maintainability | `NIST_SP_800_218_SSDF_GOVERNANCE.md` |
| Compatibility | `KUBERNETES_VERSION_GOVERNANCE.md` |
| Usability | (deferred) |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card that touches quality.
2. Confirm the ISO/IEC 25010 characteristic is identified.
3. Update the next-review date.

## Sources

- ISO/IEC 25010:2011: `https://www.iso.org/standard/35733.html`
- SQuaRE series overview: `https://www.iso.org/standard/74348.html`
- ISO/IEC 25040: `https://www.iso.org/standard/34974.html`
