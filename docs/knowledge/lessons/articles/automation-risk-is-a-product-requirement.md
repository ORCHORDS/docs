# Automation Risk Is a Product Requirement

**Issue:** Abuse controls are added only after implementation, when engineering has no clear definition of which valid user actions become harmful when automated.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API6:2023 separates mitigation planning into business identification of sensitive flows and engineering selection of protections. Engineering cannot infer acceptable purchase rates, reservation behavior, referral creation, posting velocity, or similar product rules from protocol semantics alone.

## Engineering rule

- Put automation-abuse assumptions in the feature requirements for sensitive flows.
- Define what constitutes harmful scale, repetition, timing, or sequencing in business terms.
- Assign an owner for the threshold and exception policy.
- Require abuse tests before launch for flows whose value depends on scarcity, fairness, incentives, or limited capacity.
- Revisit the model when pricing, incentives, inventory, or market behavior changes.

## Verification

- Ask the feature owner to state the allowed automated behavior without referring to implementation details.
- Convert that statement into measurable test cases and telemetry.
- Confirm a change in business rules triggers review of the protection thresholds.

## Official source

- OWASP API6:2023 Unrestricted Access to Sensitive Business Flows: https://owasp.org/API-Security/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/
