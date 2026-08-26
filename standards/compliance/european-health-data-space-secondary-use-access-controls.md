# european-health-data-space-secondary-use-access-controls

**Issue:** A health-data secondary-use program treats GDPR consent or a generic data-export process as sufficient, without the specific governance and secure-processing controls required by the European Health Data Space framework.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Secondary use of health data is a controlled governance workflow. It requires scope analysis, permitted-purpose assessment, data-holder responsibilities, access-body processes, minimum-necessary handling, and secure processing safeguards. Applicable obligations and dates depend on the entity, data, purpose, and implementing measures.

**Source:** [European Health Data Space](https://health.ec.europa.eu/ehealth-digital-health-and-care/european-health-data-space-regulation-ehds_en).

## Fix

- obtain qualified legal and sector-specific scope analysis;
- inventory health-data holders, data categories, lawful purpose, access authority, and recipients;
- enforce minimum-necessary data, role separation, and controlled processing environments;
- document anonymisation/pseudonymisation assumptions and re-identification risk controls;
- preserve application, approval, access, output-check, and retention/deletion evidence;
- track implementation milestones and national/sector guidance separately from product delivery.

## Verification

- A secondary-use request has a documented purpose, authority, and data-minimization decision.
- Access is limited to approved users and controlled environment.
- Outputs follow an approved disclosure process.
- Evidence can be traced from request through access expiry and closure.

## Related

- `compliance/gdpr-data-subject-rights-api.md`
- `compliance/eu-data-act-implementation.md`
