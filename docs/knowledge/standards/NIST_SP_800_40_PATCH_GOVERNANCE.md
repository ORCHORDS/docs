# NIST SP 800-40 Rev. 4 (2022) Guide to Enterprise Patch Management Governance

## 1. Scope
This document establishes a governance framework for enterprise patch management derived from NIST Special Publication 800-40 Revision 4. It applies to all information systems, applications, and infrastructure components within the organization that receive security updates from vendors or open source maintainers. The scope covers operating systems, applications, firmware, container images, and infrastructure-as-code modules. Out of scope are physical security controls and personnel policies unrelated to vulnerability remediation.

## 2. Normative references
The following documents are referenced and inform the controls defined herein:
- NIST SP 800-40 Rev. 4, Guide to Enterprise Patch Management Planning (2022)
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations
- NIST SP 800-30 Rev. 1, Guide for Conducting Risk Assessments
- CISA Known Exploited Vulnerabilities (KEV) Catalog
- FIRST.org Exploit Prediction Scoring System (EPSS) specification

## 3. Terms and definitions
CVE — Common Vulnerabilities and Exposures: a unique identifier assigned to a publicly disclosed vulnerability.
NVD — National Vulnerability Database: the U.S. government repository of vulnerability data synchronized with CVE records.
CVSS — Common Vulnerability Scoring System: a standardized method for rating vulnerability severity on a 0.0 to 10.0 scale.
KEV — Known Exploited Vulnerabilities: the CISA-maintained list of vulnerabilities for which active exploitation has been observed in the wild.

## 4. Background
Enterprise environments accumulate vulnerabilities faster than operational teams can remediate them. NIST SP 800-40 Rev. 4 promotes a risk-based approach that replaces calendar-driven patch cycles with prioritized, evidence-driven remediation. Organizations must integrate authoritative threat intelligence, asset context, and compensating controls to allocate remediation effort where risk reduction is greatest. The framework treats patching as a continuous risk management activity rather than a periodic maintenance task.

## 5. Risk-based patching framework
The framework ingests three primary signals to score remediation priority. CVSS provides a static severity baseline ranging from 0.0 to 10.0 and reflects intrinsic technical impact. EPSS supplies a probabilistic estimate, expressed as a percentage, that a vulnerability will be exploited in the wild within the next 30 days. CISA KEV confirms active exploitation in the environment's threat landscape and imposes binding remediation deadlines for federal agencies. Prioritization logic multiplies CVSS impact weight by EPSS likelihood and applies an override multiplier when a vulnerability appears on the KEV catalog. Assets with elevated exposure such as internet-facing systems, domain controllers, and payment-processing hosts receive additional weighting through an asset criticality tier recorded in [risk-register.md:1](risk-register.md:1).

## 6. Patch identification and prioritization
Vulnerability data is collected from vendor advisories, NVD feeds, and authenticated scanners operating on a continuous basis. Each advisory is correlated with the configuration management database to identify affected assets and their owners. Tickets are generated automatically with a priority derived from Section 5 scoring. Critical internet-facing KEV vulnerabilities receive a 14-day service-level objective. High-severity internal vulnerabilities receive 30 days. Medium and low severities follow a quarterly batch cycle unless EPSS probability exceeds 0.5, which escalates the timeline to 30 days.

## 7. Patch testing and staging
Patches are deployed first to a laboratory environment that mirrors production configuration including installed roles, network exposure, and integrated third-party components. Regression suites covering authentication, cryptography, and business-critical workflows must pass before promotion. Staging environments receive patches under representative load conditions. Change advisory board review is required for patches affecting more than 100 endpoints or any system regulated under Section 11. Rollback procedures are validated in staging prior to production deployment.

## 8. Deployment mechanisms
Operating system patches are delivered through native vendors such as Windows Update for Business, Red Hat Satellite, and Ubuntu Landscape. Application patches are distributed via managed package repositories and enterprise application control tooling. Firmware updates are scheduled during maintenance windows with redundant power verification and out-of-band recovery procedures. Container base images are rebuilt through automated pipelines that scan upstream registries for disclosed vulnerabilities. Infrastructure as code modules are re-evaluated against policy-as-code gates that block deployment when unpatched critical components are detected.

## 9. Exception handling and compensating controls
When a patch cannot be deployed within its service-level objective, a formal exception is recorded in the risk register. The exception must document the affected assets, the blocking condition, the proposed remediation date, and the compensating controls in place. Compensating controls include network segmentation, virtual patching via intrusion prevention signatures, enhanced monitoring, and access restrictions enforced through administrative policy. Exceptions are approved by the system owner and the information security officer and expire automatically after 90 days.

## 10. Verification, validation, and SOAR integration
Post-deployment verification reconfirms package versions and scanner cleanliness on every affected endpoint. Validation compares the deployed state against the original ticket's remediation criteria and produces a signed attestation. SOAR (Security Orchestration Automation and Response) integration automates ticket creation upon KEV publication, orchestrates scanner re-runs after deployment, and confirms patch presence by correlating endpoint telemetry with the expected version recorded in the change record. Failed confirmations reopen tickets and notify the on-call security engineer. Workflow definitions are maintained in [section-10-procedures.md:1](section-10-procedures.md:1).

## 11. Compliance evidence
The framework satisfies control requirements across multiple regimes. FedRAMP continuous monitoring obligations under RA-5 and SI-2 are met through documented scanning cadence and remediation timelines. FISMA reporting incorporates the same artifacts as quarterly metrics submitted to the authorizing official. PCI DSS Requirement 6.3 is satisfied by prioritized remediation of security vulnerabilities within defined timelines. HIPAA Security Rule 164.308(a)(1)(ii)(B) risk management requirements are addressed through documented patch governance. ISO 27001 Annex A control 8.8 is fulfilled via formal change management of technical vulnerabilities.

## 12. Risk register
Residual risk from unpatched assets, expired exceptions, and delayed remediations is recorded in [risk-register.md:1](risk-register.md:1). Each entry tracks asset identifier, CVE, CVSS score, EPSS probability, KEV status, compensating control, exception expiry, and review date. The register is reconciled weekly and audited quarterly by internal compliance.

## 13. Review cadence
This document is reviewed every 180 days or upon material change to NIST SP 800-40, KEV catalog publication rate, or applicable regulatory guidance. The review owner is the information security officer.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.