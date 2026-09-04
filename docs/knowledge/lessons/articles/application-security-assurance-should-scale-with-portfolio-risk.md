# Application Security Assurance Should Scale With Portfolio Risk

**Issue:** Every application receives the same lightweight security checklist regardless of business criticality, data sensitivity, exposure, or impact, leaving high-risk systems under-assured and low-risk systems burdened with poorly targeted work.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP Top 10:2025 application-security program guidance recommends a risk-based portfolio approach: inventory applications and APIs, use a common risk model, prioritize them, and define assurance coverage and rigor accordingly. A security baseline should be consistent, but the depth of evidence should follow risk.

## Engineering rule

- Maintain an owned inventory of applications and APIs with business/data context.
- Use a common likelihood/impact model aligned to organizational risk tolerance.
- Assign risk tiers that drive expected design review, testing frequency, testing depth, and management visibility.
- Provide shared baseline policies and reusable security controls so teams do not rebuild common controls independently.
- Integrate security activities across requirements, design, development, testing, rollout, operations/change management, and retirement.
- Track portfolio coverage and exceptions so management can see where required assurance is missing.

## Verification

- Select applications from different risk tiers and confirm the required security-assurance depth differs according to documented policy.
- Compare the application/API inventory with active deployment/exposure sources to find missing systems.
- Verify high-risk exceptions and overdue testing are visible at the portfolio-management level.

## Official sources

- OWASP Top 10:2025 — Establishing a Modern Application Security Program: https://owasp.org/Top10/2025/0x03_2025-Establishing_a_Modern_Application_Security_Program/
- OWASP Top 10 project page: https://owasp.org/www-project-top-ten/
