# EU Data Act smart-contract essential requirements

**Issue:** Article 36 of Regulation (EU) 2023/2854 sets essential requirements for smart contracts used to execute data-sharing agreements. This entry applies only where that statutory role and use are established; it is not a general blockchain checklist.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Record the role analysis, agreement, deployment owner, access-control model, and applicable date.
- Design robustness, safe termination/interruption, archival and audit continuity, access control, and consistency with the data-sharing agreement.
- Preserve conformity evidence and the EU declaration where the Regulation requires it; obtain legal review for applicability and standards.

## Verification

1. Exercise unauthorized calls, replay, partial execution, interruption, upgrade or termination, and recovery.
2. Demonstrate that termination does not erase evidence required by the agreement or law.
3. Trace each applicable Article 36 requirement to a control and test.

## Gotchas

An immutable deployment does not remove the legal requirement for safe termination. Do not claim conformity merely because a contract passed a code audit; harmonised-standard and implementation status can change.

## Official sources

- https://eur-lex.europa.eu/eli/reg/2023/2854/oj
