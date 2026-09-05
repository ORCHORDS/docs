# Supply Chain Incident Response Playbook

## Purpose

Respond to a software supply chain incident: malicious dependency, compromised upstream artifact, account takeover of an upstream maintainer, or build-system compromise. Aligns with SLSA v1.0, NIST SSDF v1.1, NIST SP 800-161, and the CISA Software Supply Chain Attestation guidance.

## Audience

Security incident commander, SRE on-call, security engineer, application owners, vendor risk manager.

## Pre-conditions

1. The reference cards are current: `SLSA_VERSION_GOVERNANCE.md`, `NIST_SP_800_218_SSDF_GOVERNANCE.md`, `NIST_CSWP_23_2024_SSB_GOVERNANCE.md`.
2. The project publishes SBOM (SPDX or CycloneDX).
3. The project signs build provenance.
4. The project maintains a vendor inventory.
5. The incident response channel is reachable.

## Procedure

### 1. Detect

A supply chain incident is detected through one of:

- **Vulnerability disclosure**: CVE in an upstream dependency (e.g., `log4shell`).
- **Upstream advisory**: vendor-published security advisory (e.g., `GHSA-xxxx`).
- **Threat intel**: STIX 2.1 indicator pointing to a malicious package.
- **Runtime detection**: anomaly in build / dependency update.
- **Account takeover**: maintainer account compromise disclosed.
- **Build-system compromise**: CI / CD account compromise.

### 2. Classify

| Vector | Severity |
|---|---|
| Direct dependency CVE (in active use) | depends on CVSS + exploitability |
| Transitive dependency CVE (in active use) | depends on reachability |
| Account takeover of upstream maintainer | critical |
| Build-system compromise | critical |
| Malicious package published (typosquatting) | critical |
| Compromised upstream artifact signature | critical |
| Dependency-confusion attack | critical |

### 3. Contain

Within 1 hour:

1. Pin the affected dependency to a known-good version.
2. Block the malicious version in the dependency manager (npm `audit`, cargo `audit`, pip-audit, etc.).
3. Block the malicious registry URL at the egress firewall.
4. Suspend automated updates for the affected ecosystem (npm, PyPI, RubyGems, Maven).
5. Rotate any secret that may have been exposed via the compromised dependency.

### 4. Eradicate

Within 4 hours:

1. Identify every artifact built with the compromised version (via SBOM + build provenance).
2. Identify every deployment using those artifacts.
3. Replace the artifacts with the pinned-good version.
4. Re-deploy.
5. Audit the build pipeline for any artifact that was produced during the compromise window.

### 5. Recover

1. Re-deploy from clean source.
2. Validate the SBOM matches the deployed artifact.
3. Re-verify signatures.
4. Confirm dependencies are pinned to good versions.

### 6. Communicate

| Audience | Channel | SLA |
|---|---|---|
| Internal | incident channel | ≤ 1 hour |
| Customer-facing | status page | ≤ 4 hours |
| CISA | `cisa.gov/report` | ≤ 24 hours |
| Vendor / upstream | vendor's security contact | ≤ 4 hours |

For critical incidents affecting customer data, follow `PRIVACY_INCIDENT_RESPONSE_PLAYBOOK.md`.

### 7. Document

Within 5 business days:

1. Incident dossier with timeline.
2. SBOM diff before / after the incident.
3. Build-provenance verification log.
4. Vendor coordination log.

### 8. Post-incident review

Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`. Output:

- Updated SBOM publication cadence.
- Updated signing / verification policy.
- Updated vendor risk assessment.
- New reference card for the affected ecosystem (if applicable).

## Rollback

Rollback decisions:

- Pinned version has its own CVE → revert to the prior version that has no known CVE.
- Pinning causes runtime regression → identify the regression and document as an exception.

## Mandatory pre-flight (before adopting a new external dependency)

1. The dependency is in the SBOM.
2. The dependency is signed (per `SLSA_VERSION_GOVERNANCE.md`).
3. The upstream maintainer is documented.
4. The license is documented.
5. The transitive dependency tree is reviewed.

## References

- `SLSA_VERSION_GOVERNANCE.md`
- `NIST_SP_800_218_SSDF_GOVERNANCE.md`
- `NIST_CSWP_23_2024_SSB_GOVERNANCE.md`
- `PRIVACY_INCIDENT_RESPONSE_PLAYBOOK.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- CISA Software Supply Chain: `https://www.cisa.gov/supply-chain`
- NIST SP 800-161 Rev. 2 (C-SCRM): `https://csrc.nist.gov/publications/detail/sp/800-161/rev-2/final`
- OpenSSF Scorecard: `https://github.com/ossf/scorecard`
