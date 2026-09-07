# NIST SP 800-167 — Guide to Application Whitelisting Governance

## 1. Scope

This card governs the application of NIST Special Publication 800-167 (Guide to Application Whitelisting) to endpoints, servers, and container workloads managed by OrchordsAI. The card establishes governance for selecting, authoring, enforcing, and maintaining whitelists that permit only approved executable code to run on in-scope systems. It aligns whitelisting with NIST SP 800-53 control CM-7 (Least Functionality) and SI-7 (Software, Firmware, and Information Integrity), and is informed by NIST SP 800-53 revision 5 baselines where applicable.

## 2. Normative references

- NIST Special Publication 800-167 — Guide to Application Whitelisting (2015).
- NIST SP 800-53 revision 5 — Security and Privacy Controls for Information Systems and Organizations.
- NIST SP 800-53 control CM-7 — Least Functionality.
- NIST SP 800-53 control SI-7 — Software, Firmware, and Information Integrity.
- NIST SP 800-128 — Guide for Security-Focused Configuration Management (supporting reference).

## 3. Terms and definitions

- Application whitelisting: a security approach that permits only approved applications, libraries, scripts, or binaries to execute, denying everything else by default.
- Whitelist (allowlist): the curated set of approved executables identified by publisher, path, hash, or signature.
- Publisher rule: a whitelist entry that authorises any binary signed by a specified code-signing certificate.
- Path rule: a whitelist entry that authorises execution from a specified directory, typically with associated file attributes.
- Hash rule: a whitelist entry that authorises a specific file by cryptographic hash value.

## 4. Application whitelisting objectives

The objective of NIST SP 800-167 is to reduce the attack surface and constrain the execution of unauthorised or malicious code on systems that handle regulated, sensitive, or operationally critical workloads. Whitelisting is positioned as a complement to patching, vulnerability management, and anti-malware controls. The objectives also include support for CM-7 Least Functionality by restricting the set of permitted software to that required for the mission, and support for SI-7 by detecting and blocking execution of unauthorised code, including unsigned or tampered binaries.

The guidance further recognises whitelisting as a defensive layer against fileless malware, living-off-the-land binaries, and supply-chain compromise: by authorising only the binaries required for the workload, the technique reduces the universe of tools available to an attacker who has gained a foothold. The objectives therefore extend beyond traditional executable-file controls to scripts, macros, signed installers, dynamically loaded libraries, and AI/ML model artefacts executed by interpreters and runtimes.

## 5. Policy enforcement modes (audit / block)

NIST SP 800-167 describes two enforcement modes. In audit mode, the whitelisting agent logs execution events for binaries that are not on the whitelist without blocking them; this mode supports baseline collection and policy tuning. In block mode, the whitelisting agent denies execution of any binary not on the whitelist and generates an alert. Orchestration typically begins with audit mode on representative populations, transitions to block mode after the whitelist stabilises, and retains a controlled exception workflow for legitimate but unsigned software. Mode transitions are recorded as configuration changes under CM-7.

Mixed-mode deployments are common: block mode is enforced on production systems that handle regulated or sensitive workloads, while audit mode is retained on developer endpoints and lab systems where the binary churn is high and the data sensitivity is lower. Each mode assignment is justified in the configuration baseline, and reversions from block to audit are approved only as time-bound exceptions with a defined exit criterion.

## 6. Whitelist composition and lifecycle

Whitelist entries are selected using a least-privilege posture. Publisher rules cover signed commercial software; path rules cover approved installation directories under controlled write access; hash rules cover bespoke binaries, internal scripts, and AI/ML model artefacts that lack publisher signatures. Each entry records justification, owner, supported versions, and review cadence. Lifecycle stages include authoring, review, deployment, monitoring, and retirement. Hash rules are recomputed when binaries change; publisher and path rules are revalidated when vendors rotate certificates or change installation paths. Exceptions are time-bound and require an accountable approver.

Lifecycle governance requires staging and roll-back paths: whitelist changes are first applied to a representative cohort, monitored for false positives and unintended block events, then promoted to the wider population. Change records capture the rule, the approver, the target population, and the verification evidence. When a vendor signs a previously unsigned binary, hash rules may be retired in favour of publisher rules to reduce maintenance overhead, with the transition documented in the change record.

## 7. Operational considerations and deviation handling

Operations monitor blocked-execution events, false-positive rates, and unsigned-binary alerts. SI-7 integrity checks compare running binaries against the authorised whitelist and report drift. Deviation handling routes unauthorised execution attempts through incident response, with root-cause analysis distinguishing malicious activity from legitimate gaps in the whitelist. Coverage gaps trigger a whitelist update with expedited review. Periodic recertification verifies that every entry remains necessary and that retired entries are removed, sustaining CM-7 least-functionality posture across the estate.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
