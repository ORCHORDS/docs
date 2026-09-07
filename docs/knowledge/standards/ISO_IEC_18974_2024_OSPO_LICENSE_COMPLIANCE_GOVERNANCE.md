# ISO/IEC 18974:2024 Open Source License Compliance Governance

## Purpose

ISO/IEC 18974:2024 ("Open chain of custody for open source software used in the development, deployment and support of products and services") defines an open chain of custody (OCC) for open source software consumed and produced by organizations. Governance ensures ORCHORDS platforms apply OCC as a first-class compliance domain with documented identification, attribution, license-obligation tracking, and audit trail, distinct from — but coordinated with — the SCRM controls in `NIST_SP_800_161_R2_CYBER_SCRM_GOVERNANCE.md` and the SDLC controls in `NIST_SP_800_218_SSDF_GOVERNANCE.md`.

## Current context and source status

ISO/IEC 18974:2024 was published by ISO/IEC JTC 1/SC 7 in October 2024. It is the first internationally standardized framework for open-source chain of custody and aligns with SPDX 2.3 and CycloneDX 1.5 metadata formats, with the Linux Foundation's OpenChain specification, and with the European Cyber Resilience Act (CRA) SBOM-related obligations. Treat the ISO/IEC document as the authoritative source for the OCC vocabulary and lifecycle stages; cross-reference SPDX, CycloneDX, and OpenChain for implementation formats.

## Governance workflow and controls

### 1. OCC-1: Scope and component identification

- Maintain an organization-wide register of open-source components consumed in production builds (third-party) and produced as deliverables (first-party).
- Each component MUST carry: name, version, source, license SPDX identifier, upstream maintainer, SHA digest, and the build that first introduced it.
- Use SPDX or CycloneDX as the canonical format; declare a single format as the system-of-record (one or the other, not both, per system).

### 2. OCC-2: Chain of custody inputs

- Provenance evidence MUST identify the source commit, the build runner identity, and the input parameter set (see `NIST_SP_800_53_R5_SCRM_OVERLAY_GOVERNANCE.md` and SLSA Build Level 2).
- Signed SBOMs (cosign or Notary v2) MUST accompany each production artifact; verification MUST be enforced at the admission boundary.

### 3. OCC-3: License-obligation tracking

- For every consumed component, the compliance officer MUST record the license, the obligations (attribution, copyleft, patent grant, source-disclosure), and the verification evidence (license file, SPDX expression).
- Copyleft components in distributed products MUST be flagged; review the distribution boundary (which artifacts are distributed to whom) at every release.
- License changes in upstream MUST trigger a re-review of the obligation set.

### 4. OCC-4: Distribution and redistribution

- Maintain a redistribution register that records which components ship with which products, the destination (customer, partner, internal), and the destination's rights under the component's license.
- Copyleft components MUST NOT be redistributed under a license that conflicts with the upstream license; if redistribution is required, obtain written guidance from legal counsel.
- Re-distribution events MUST be logged for the retention period declared by the records-retention policy.

### 5. OCC-5: Vulnerability and patch management

- Vulnerability signals (CVE, GHSA, vendor advisories) MUST be cross-referenced against the component inventory.
- Patch events MUST update the component inventory with the new version, the new SHA digest, and the new provenance evidence.
- End-of-life components MUST be removed from production builds within the migration lead time agreed with the system owner.

### 6. OCC-6: Records and audit trail

- OCC records MUST be retained for the lifetime of the deliverable plus the retention period declared by the records-retention policy.
- Records MUST be tamper-evident (write-once storage or signed manifests) and MUST be queryable for audit.
- A breach of the OCC record MUST trigger an incident response under the SCRM/IR plan.

### 7. OCC-7: Roles, responsibilities, and training

- Designate an OSPO lead (or equivalent role) accountable for OCC outcomes.
- Engineers MUST complete open-source license training before contributing a new dependency to a production build.
- Annual refresh training covers OCC updates, license-change trends, and incidents observed in the prior year.

### 8. OCC-8: Continuous improvement

- Track KPI: time to register a new component, time to re-review after a license change, percentage of components with provenance evidence, percentage of components with current vulnerability status.
- Quarterly: review the KPI dashboard and produce an improvement plan.
- Annually: re-baseline the OCC program against ISO/IEC 18974 updates, CRA regulatory updates, and the OpenChain conformance checklist.

## Mapping to other ORCHORDS standards

- `NIST_SP_800_53_R5_SCRM_OVERLAY_GOVERNANCE.md`: SR-3, SR-4, CM-8 align with OCC-1, OCC-2, and the component inventory.
- `NIST_SP_800_218_SSDF_GOVERNANCE.md`: PS-3 (open-source participation) and SR-3 (third-party components) align with OCC-1 and OCC-3.
- `OWASP_CICD_TOP_10_2024_GOVERNANCE.md`: CICD-SEC-3 (dependency chain abuse) and CICD-SEC-9 (artifact integrity) align with OCC-2 and OCC-5.

## Review cadence

- Re-baseline the OCC program at every ISO/IEC 18974 revision.
- Quarterly: validate the component inventory and the redistribution register.
- Annually: independent audit of OCC records and KPI performance.

References: `https://www.iso.org/standard/86360.html` (ISO/IEC 18974:2024), `https://spdx.dev/`, `https://cyclonedx.org/`, `https://www.openchainproject.org/`, `https://www.linuxfoundation.org/tools/openchain/open-source-program-office/`, `https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act`.
