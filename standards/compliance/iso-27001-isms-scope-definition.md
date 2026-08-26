# iso-27001-isms-scope-definition

**Issue:** Defining the ISO 27001 ISMS scope boundary (Clause 4.3) correctly
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An incorrectly defined scope leads to either under-coverage (certification gaps) or over-coverage (excessive cost and complexity). Auditors scrutinize scope carefully to ensure it is not cherry-picked to exclude high-risk areas.

## Pattern / Solution
Scope statement elements:
- Organizational boundaries: which legal entities, departments, and teams are in scope
- Physical boundaries: which offices, data centers, cloud regions are in scope
- Technology boundaries: which systems, platforms, and services are in scope
- Excluded elements: what is explicitly out and why (must be justified)

Scope statement template:
```
The ISMS applies to the design, development, delivery, and support of [Product Name],
operated by [Entity Name], including all employees and contractors with access to
production systems hosted on AWS [us-east-1, eu-west-1], the corporate office at
[Address], and remote workers globally. Excluded: [subsidiary X] (separate ISMS pending).
```

Common scope choices:
- Full organization: maximum coverage, most credible to customers
- Product/service scope: limited to a specific product's infrastructure and team
- Cloud/hosted services scope: infrastructure and operations only, excludes physical offices

Context analysis required (Clauses 4.1 and 4.2):
- Internal and external issues (PESTLE, SWOT)
- Interested parties (customers, regulators, suppliers) and their requirements
- How these affect the ISMS scope

## Gotchas
- Scope that excludes development environments but developers have production access is inconsistent
- Customer-facing SaaS with SOC 2 and ISO 27001: scopes must be reconcilable
- Scope must be documented and reviewed annually — changes require stage 1 audit re-evaluation
- Auditors will question any exclusion that seems designed to avoid scrutiny

## Related
- `iso-27001-risk-assessment-methodology.md`
- `iso-27001-internal-audit-process.md`
