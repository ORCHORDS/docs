# MITRE D3FEND Detection Countermeasure Governance

## Purpose
Establish the governance pattern for selecting, mapping, and validating detection countermeasures using the MITRE D3FEND ontology so that defensive coverage is traceable from adversary techniques to deployed controls.

## Scope
Applies to every detection rule, sensor configuration, and security control operation whose purpose is to detect, deny, disrupt, degrade, deceive, or contain adversary behaviour.

## Workflow
1. Maintain a coverage matrix that maps MITRE ATT&CK techniques relevant to the studio's threat model to D3FEND defensive techniques.
3. For each defensive technique, document the implemented countermeasure, owner, telemetry source, and tuning owner.
5. Validate each countermeasure quarterly using synthetic test cases derived from publicly-available adversary emulation plans.
7. Track coverage gaps and prioritise countermeasures based on the threat model and the adversary emulation results.
9. Refresh the coverage matrix when the studio's threat model changes, when MITRE ATT&CK receives a significant update, or when D3FEND publishes a new version.

## Controls and evidence
- Coverage matrix keyed to ATT&CK technique and D3FEND defensive technique.
- Countermeasure catalogue with telemetry source, owner, last test date, and result.
- Quarterly test results archive with pass/fail outcome and root cause for failures.
- Coverage gap report with prioritised remediation backlog.

## Validation
- Execute a defined set of synthetic adversary emulation scenarios against the deployed countermeasures; record pass/fail and timing metrics.
- Confirm coverage of the top 20 ATT&CK techniques per the studio's threat model; produce a remediation plan for any gap.
- Verify that the coverage matrix is in sync with the latest D3FEND ontology version.

## Failure correction
- **Countermeasure fails synthetic test** → investigate the failure, document the root cause, and either retune the control or document compensating measures.
- **Coverage gap not remediated within target date** → escalate to the security engineering lead and document the risk acceptance.
- **Coverage matrix out of sync with D3FEND version** → update within 30 days, document the lag, and re-test countermeasures whose D3FEND definition changed.

## Limitations
- D3FEND is a structured ontology of countermeasures; it does not provide implementations.
- Detection coverage of an ATT&CK technique is a function of telemetry availability; some techniques may be inherently undetectable.
- Synthetic test cases cannot replicate all production adversary behaviours; expect drift between test coverage and real incident outcomes.

## Scope note
This article is part of the security leaf. Cross-reference: OWASP_API_SECURITY_TOP_10_2023_GOVERNANCE.md, NIST_IR_8441_CYBERSUPPLY_CHAIN_RISK_GOVERNANCE.md, NIST_SP_800_61_R3_INCIDENT_LEGAL_COORDINATION_GOVERNANCE.md.

## Canonical sources
- MITRE D3FEND Project: https://d3fend.mitre.org/
- MITRE D3FEND Ontology: https://d3fend.mitre.org/resources/ontology/
- MITRE ATT&CK Enterprise Matrix: https://attack.mitre.org/matrices/enterprise/
- MITRE ATT&CK Adversary Emulation Plans: https://attack.mitre.org/resources/adversary-emulation-plans/
- NIST SP 800-53 Rev. 5 — SI family controls: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final