# Security Decision Traceability Review

## Trigger
Run before release of material security-sensitive changes, after significant architecture/threat/dependency changes, during risk/exception reviews, and on a periodic secure-development governance cadence.

## Inputs
- Security requirements and sources.
- Threat/risk records.
- Security-relevant design decisions.
- Approved exceptions/accepted risks.
- Implementation/mitigation and verification evidence.

## Procedure
1. Select representative security requirements and material risks for the product/component in scope.
2. Trace each selected requirement to its source, owner, current status, and relevant design/implementation decision.
3. For each selected risk, verify an explicit disposition such as mitigate, accept, transfer, avoid, or another approved response is recorded.
4. Trace mitigated requirements/risks to implementation or control evidence and then to verification/test evidence where required by the SDLC.
5. Sample security-relevant design decisions and confirm rationale remains available to maintainers rather than only the final outcome.
6. Sample approved exceptions or accepted risks and verify owner, rationale, compensating controls where applicable, and review/expiry state.
7. Introduce or identify a material change in architecture, threat model, dependency, exposure, or business context and verify affected prior decisions can be found for re-evaluation.
8. Identify requirements, risks, or exceptions that exist only in informal notes or individual memory and move them into the maintained system of record.
9. Verify records remain accessible to maintenance, incident-response, audit, and future design roles according to retention policy.
10. Record traceability gaps, assign owners/dates, and retest after remediation.

## Escalation
Escalate material security requirements with no accountable owner, risks with no disposition, accepted risks/exceptions with no current review state, or decisions whose rationale and verification evidence cannot be reconstructed.

## Evidence
- Requirement-to-decision trace samples.
- Risk-to-disposition/mitigation traces.
- Implementation and verification evidence.
- Exception/accepted-risk review evidence.
- Material-change re-evaluation test.
- Findings and retest results.

## Completion criteria
Representative security requirements, risks, design decisions, mitigations, verification evidence, and exceptions are traceable through the software lifecycle and can be re-evaluated when assumptions change.

## Source basis
- NIST SP 800-218, Secure Software Development Framework (SSDF) Version 1.1: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SSDF project page — PW.1.2: https://csrc.nist.gov/projects/ssdf
