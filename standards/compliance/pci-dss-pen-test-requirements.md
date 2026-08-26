# pci-dss-pen-test-requirements

**Issue:** Meeting PCI DSS v4.0 penetration testing requirements (Req 11.3 and 11.4)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PCI DSS v4.0 strengthened penetration testing requirements including annual external and internal tests, targeted segmentation tests, and application-layer testing.

## Pattern / Solution
Required tests:

External penetration test (Req 11.3.1):
- At least annually and after any significant infrastructure change
- Covers all external-facing CDE components
- Must include network-layer and application-layer testing

Internal penetration test (Req 11.3.1):
- At least annually
- Tests from within the CDE boundary
- Internal network segmentation validation

Segmentation penetration test (Req 11.3.2):
- Validates that out-of-scope systems cannot access CDE
- At least every 6 months for service providers; annually for merchants
- Tests from all out-of-scope network segments toward CDE

Application-layer testing (Req 11.3.1.1):
- Web application testing against OWASP Top 10 at minimum
- All CDE-connected APIs and web apps in scope

Tester requirements:
- Qualified internal resource or qualified external third party
- Organizational independence from systems being tested
- No requirement for specific certification, but OSCP, CREST, CEH widely accepted

Deliverables:
- Penetration test methodology document (before test)
- Full report with findings, risk ratings, and proof-of-concept screenshots
- Remediation plan for all high/critical findings
- Retest results after remediation
- Retain reports for at least 12 months

## Gotchas
- QSAs can reject pen tests that do not cover application layer — scope must be documented
- Vulnerability scans (ASV scans) are NOT penetration tests — both are required
- Segmentation test must be specifically designed to verify segmentation, not just general pen test
- Findings must be remediated before AOC is issued for the period

## Related
- `pci-dss-network-segmentation.md`
- `pci-dss-v4.md`
- `penetration-testing-scope.md`
