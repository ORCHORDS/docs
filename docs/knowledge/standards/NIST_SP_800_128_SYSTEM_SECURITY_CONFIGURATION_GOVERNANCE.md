# NIST SP 800-128 — System Security Configuration Management Governance

## 1. Scope

This card governs the adoption of NIST Special Publication 800-128, *Guide for Security-Focused Configuration Management of Information Systems*, as the governance framework for security-focused configuration management (SecCM) across all systems, applications, and cloud workloads operated by the organization. It applies to every component in the system inventory: on-premises servers, endpoints, network devices, container platforms, serverless workloads, and managed cloud services. The card establishes the policy and procedure minimum that downstream engineering, operations, and assurance teams must implement.

## 2. Normative references

- NIST SP 800-128 — *Guide for Security-Focused Configuration Management of Information Systems*.
- NIST SP 800-53 Rev. 5 — Configuration Management (CM) control family.
- NIST SP 800-53A Rev. 5 — assessment procedures for CM controls.
- NIST SP 800-70 Rev. 4 — *National Checklist Program for IT Products*.
- CIS Benchmarks — platform-specific technical baselines.
- CIS Critical Security Controls v8 — Safeguard 4 (Secure Configuration) and Safeguard 11 (Data Recovery).
- NIST SP 800-37 Rev. 3 — Risk Management Framework (configuration as a system-state artifact).

## 3. Terms and definitions

- **Configuration Management (CM)** — the collection of activities used to establish and maintain the integrity of a system through control of the processes for initializing, changing, and monitoring the configuration of that system.
- **Security-focused Configuration Management (SecCM)** — the subset of CM activities that focus on establishing and maintaining the secure configuration of information systems, as defined by NIST SP 800-128.
- **Configuration Item (CI)** — an identifiable part of a system (hardware, software, firmware, document) that has a defined set of security-relevant properties.
- **Baseline Configuration** — a documented set of attributes used as a basis for future builds, releases, or changes.
- **Configuration Change Control** — the process of managing changes to configuration items to preserve system integrity.
- **Common Secure Configuration** — a recognized, consensus-based configuration such as a CIS Benchmark or a DISA STIG.

## 4. Configuration management baseline

The Security Configuration Baseline is the codified set of approved settings for every system component.

- Each system has a named owner, a documented baseline version, and a revision history stored in the change-control system.
- Baseline sources are tiered: CIS Benchmarks are the default; DISA STIGs are mandatory for federal-bound workloads; vendor hardening guides fill documented gaps.
- Baselines are expressed as machine-readable code (Ansible, Terraform, Chef InSpec) so that drift can be detected automatically.
- A baseline must include account and credential settings, service and daemon configuration, network exposure rules, logging and audit settings, patch level, and cryptographic module posture.
- Every baseline release is reviewed by Security Engineering and signed by the system owner before promotion.
- Baselines for new systems must be declared within 30 days of system onboarding and integrated with the Configuration Management Database (CMDB).

## 5. Configuration change control

All changes to a security-relevant configuration item must follow the documented change-control flow.

- Change requests reference the affected CI, the baseline delta, the security impact category (low, moderate, high), and the rollback plan.
- Standard changes (pre-approved, low risk) are auto-approved through the change-management platform; normal and emergency changes require Security Engineering sign-off.
- Emergency changes follow the NIST SP 800-128 emergency-change procedure, with a mandatory post-implementation review within five business days.
- Configuration changes are tested in a non-production environment that mirrors the production baseline before promotion.
- All approved changes are recorded in an immutable audit log retained for at least the duration required by the organization's records-retention policy.
- Aligns with NIST SP 800-53 CM-3 (Configuration Change Control), CM-4 (Impact Analyses), CM-5 (Access Restrictions for Change), and CM-6 (Configuration Settings).

## 6. Monitoring and assessment

Continuous monitoring verifies that the running configuration matches the approved baseline and that deviations are detected and resolved.

- Automated configuration-scanning tools (CIS-CAT, OpenSCAP, Nessus, native cloud posture-management) execute daily against every in-scope asset.
- Drift alerts are routed to the system owner and the Security Operations Center; the maximum detection-to-alert latency target is fifteen minutes.
- Findings are classified as PASS, FAIL, or ERROR and remediated within the NIST SP 800-128 severity schedule: critical in 7 days, high in 30 days, moderate in 90 days, low in 180 days.
- Independent assessment of SecCM effectiveness is performed at least annually against NIST SP 800-53A assessment procedures for the CM family.
- Assessment results, scan output, and remediation evidence are retained in the compliance evidence store for the record retention period.

## 7. Compliance and deviation handling

Compliance with the SecCM program is mandatory; deviations must be formally justified and tracked to closure.

- Each system must demonstrate at least 95 percent pass rate against its baseline at the time of assessment.
- Deviations from a baseline require a documented exception request, compensating controls, an expiry date not exceeding 180 days, and approval by the system owner and Security Engineering.
- Repeated or unexcused drift triggers an assurance finding, escalation to the Security Council, and a remediation plan with owner and due date.
- Compliance evidence is reported quarterly to the Security Steering Committee and annually to the Audit Committee.
- This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
