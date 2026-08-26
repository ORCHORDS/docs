---
title: "SOP: Dependency Update"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# SOP: Dependency Update

## Trigger

Use for routine dependency maintenance, security remediation, end-of-support
risk, or supplier/package health concerns.

## Procedure

1. Identify the dependency and reason for change.
2. Review release notes, security advisories, and compatibility impact.
3. Verify expected package source or provenance.
4. Update the smallest appropriate dependency set.
5. Run relevant automated and targeted tests.
6. Review transitive dependency changes where material.
7. Confirm license or policy changes if applicable.
8. Roll out according to change risk.
9. Monitor for regression.
10. Record deferred high-risk updates with an owner and rationale.

Routine automation may propose the change but does not replace risk review.
