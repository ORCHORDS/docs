# eu-dora-ict-third-party-register-and-incident-evidence

**Issue:** An in-scope financial entity cannot demonstrate its ICT third-party dependencies, contractual controls, or incident evidence under DORA.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

DORA compliance is not a generic security checklist. In-scope financial entities need operational evidence linking ICT services, providers, criticality, contracts, ownership, incident handling, testing, and change management. A vendor list without service-level dependency and evidence records cannot support oversight or reporting.

**Source:** [Regulation (EU) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj) and [EBA DORA resources](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/digital-operational-resilience-act-dora).

## Fix

- confirm scope with qualified counsel;
- maintain a register of ICT services, providers, subcontractor dependencies, data/service criticality, contract owners, and exit assumptions;
- preserve evidence for incident classification, escalation, communication, remediation, testing, and material changes;
- connect each critical service to business owner, technical owner, resilience controls, and review cadence;
- test provider failure and exit assumptions, then retain the resulting evidence;
- reconcile the register after procurement, architecture, security, or supplier changes.

## Verification

- A critical business service can be traced to ICT providers and contractual/resilience evidence.
- A simulated provider incident produces a complete, time-ordered evidence set.
- A contract or provider change updates the register through an owned process.
- Gaps are risk-accepted with an owner and review date, not silently omitted.

## Gotchas

- DORA obligations and reporting detail depend on the entity and service; do not generalize scope without counsel.
- A security questionnaire is not an operational-resilience evidence trail.
- Third-party concentration and subcontractor dependencies can matter even when the direct provider is well known.

## Related

- `compliance/dora-regulation.md`
- `patterns/incident-response.md`
- `infra/vendor-risk-management.md`
