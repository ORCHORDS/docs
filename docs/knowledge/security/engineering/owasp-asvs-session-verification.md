---
title: "OWASP ASVS 5.0.0 Session Management Verification"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# OWASP ASVS 5.0.0 Session Management Verification

## Pinned source and scope
ASVS **5.0.0**, chapter **V7 Session Management**. This article uses the named version and identifiers; do not combine evidence from another edition without a migration record.

## Control interpretation
Verify session token generation, binding, disclosure resistance, renewal, timeout, termination, and federated-session consequences against each applicable V7 identifier. Cookies need Secure, HttpOnly, appropriate SameSite, narrow Domain/Path, and transport-only issuance. Rotate the session identifier after authentication and privilege elevation. Logout and administrative revocation must invalidate server-side authority, not merely remove client storage.

## Domain-specific procedure
Attempt fixation by supplying a pre-login token, replay old tokens after login rotation, test idle and absolute expiry, replay after logout/password reset/account disable, and enumerate concurrent sessions. Inspect refresh-token rotation and reuse detection. Test cross-subdomain cookie leakage and cached authenticated pages. Retain raw Set-Cookie attributes with token values redacted and server revocation evidence.

## Evidence and decision
Preserve redacted cookie headers, rotation pairs, server-side session records, timeout timestamps, and replay responses. A revoked token producing any authenticated effect is a failure.

## Failure modes
Client-only logout, unchanged identifiers after elevation, permissive parent-domain cookies, and refresh-token reuse without detection are recurring defects.

## Sources
- [Pinned canonical source](https://github.com/OWASP/ASVS/tree/v5.0.0_release/5.0/en/0x16-V7-Session-Management.md)
