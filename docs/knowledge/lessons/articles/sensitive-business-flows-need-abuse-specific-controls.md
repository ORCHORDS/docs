# Sensitive Business Flows Need Abuse-Specific Controls

**Issue:** A business-critical flow is technically authorized and valid, but automated repetition can still create harmful outcomes such as scalping, reservation exhaustion, spam, or referral abuse.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API6:2023 focuses on legitimate business functions whose excessive automated use creates business harm. This is not necessarily a coding defect: the missing control can be failure to identify the flow as abuse-sensitive during product and security design.

## Engineering rule

- Identify business flows where automation, repetition, speed, or scale can harm customers or the business.
- Document the abuse objective before selecting controls.
- Choose controls that fit the flow: quotas, velocity limits, behavioral signals, human verification, reservation rules, or other business-specific mechanisms.
- Protect machine-to-machine APIs deliberately rather than assuming they are outside abuse risk.
- Measure false positives and bypass attempts so controls can be tuned without silently removing them.

## Verification

- Automate the flow at realistic attacker speed and volume and observe whether the intended business constraint holds.
- Test distributed activity across accounts or network locations where that matters to the threat model.
- Verify legitimate high-volume use cases have an explicit supported path rather than requiring security exceptions.

## Official source

- OWASP API6:2023 Unrestricted Access to Sensitive Business Flows: https://owasp.org/API-Security/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/
