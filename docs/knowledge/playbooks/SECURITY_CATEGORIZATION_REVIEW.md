# Security Categorization Review

## Trigger

Run on a defined review cadence and when a system’s mission, data types, integrations, users, or operating context materially change.

## Inputs

- Current system/service description
- Information/data types processed
- Architecture and integration inventory
- Existing security category
- Business-impact and regulatory context

## Procedure

1. Identify the system or service and the information types it processes.
2. Assess potential impact from loss of confidentiality, integrity, and availability separately.
3. Document the rationale for each impact level.
4. Determine the resulting security category using the applicable categorization methodology.
5. Compare the result with the current assigned category.
6. Investigate changes caused by new data, business use, integrations, architecture, or legal obligations.
7. If the category changes, trigger review of affected controls, baselines, risk records, and recovery requirements.
8. Record findings, owners, approvals, and the next review date.

## Completion criteria

- Information types in scope are current.
- CIA impacts and rationale are documented.
- The final category is approved.
- Downstream changes are assigned where required.

## Source basis

- NIST FIPS 199 — Standards for Security Categorization of Federal Information and Information Systems
- NIST SP 800-60 Vol. 1 Rev. 1 — Guide for Mapping Types of Information and Information Systems to Security Categories
