# ITIL 4 Service Request Management Practice Governance

## Purpose

Govern the ITIL 4 service request management practice so that routine, low-risk demand — access, standard changes, information — is fulfilled through predefined, repeatable workflows instead of ad-hoc exception handling.

## Scope

The practice applies to every service request type offered by the studio, including access provisioning, software requests, standard changes, and information requests. It does not cover incident resolution or the design of underlying fulfilment automation.

## Workflow

1. Define a catalogue of request types, each with an owner, required inputs, fulfilment steps, approval requirements, and target times.
2. Classify a request as standard only when risk is low, the fulfilment path is repeatable, and authorization is predictable; everything else routes to change or incident management.
3. Automate fulfilment where volume justifies it; keep a manual runbook for request types automation cannot yet cover.
4. Require pre-authorization for routine requests where policy allows, reserving approvals for genuinely risk-bearing items.
5. Measure fulfilment time and rework per request type; feed outliers into catalogue review.
6. Review the catalogue on a recurring cadence: retire unused types, add recurring ad-hoc demand as new types, and adjust target times to observed reality.
7. Reclassify request types whose risk profile grows; a request type that starts generating incidents is no longer standard.

## Controls and evidence

- Request catalogue with owner, inputs, approvals, fulfilment path, and target time per type.
- Standard classification criteria and the review decision for each type.
- Fulfilment time and rework metrics per request type.
- Catalogue review minutes with additions, retirements, and reclassifications.

## Validation

- Sample 10 fulfilled requests and confirm each followed its catalogue definition without undocumented deviation.
- Confirm no request type exceeded its rework threshold without a catalogue review.
- Confirm the catalogue review ran on cadence and captured recurring ad-hoc demand as new types.

## Failure correction

- **Fulfilment deviates from catalogue** → document the deviation, either automate the missing step or amend the catalogue, and retrain.
- **Request type generating incidents** → remove standard classification, route through change management, and investigate the cause.
- **Target times unrealistic** → rebaseline targets against observed fulfilment data and republish the catalogue.

## Limitations

- The practice handles predictable demand; unpredictable demand belongs in incident management and should not be forced into request templates.
- Automation upfront cost is justified by volume; low-volume types can remain manual runbooks.
- Catalogue hygiene decays; unused types accumulate and slow intake unless retired deliberately.

## Scope note

This article is part of the operations leaf and pairs with the service desk practice and change enablement. Cross-reference: `itil-4-change-enablement-practice.md`, `ITIL_4_SERVICE_DESK_PRACTICE_GOVERNANCE.md`, and `ISO_20000_1_2018_SERVICE_MANAGEMENT_AUDIT_GOVERNANCE.md`.

## Canonical sources

- AXELOS, *ITIL Foundation, ITIL 4 edition* (2019), service request management practice: https://www.axelos.com/certifications/itil-service-management
- ITIL 4 Practices — Service Request Management: https://www.axelos.com/certifications/itil-service-management/itil-4-practices
- ISO/IEC 20000-1:2018 — Service management — Requirements: https://www.iso.org/standard/73686.html
- NIST SP 800-63C — Digital Identity Guidelines — Federation and Assertions: https://pages.nist.gov/800-63-3/sp800-63c.html
- Gartner, Market Guide for IT Service Management Tools (recurring publication): https://www.gartner.com/en/documents/4003000
