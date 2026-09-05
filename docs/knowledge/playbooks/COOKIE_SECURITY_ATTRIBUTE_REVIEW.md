# Cookie Security Attribute Review

## Purpose

Review application cookies for secure naming, transport, script-access, cross-site, and size behavior using the stable OWASP ASVS 5.0.0 browser-security requirements as the baseline.

## Source basis

OWASP ASVS 5.0.0 V3.3 defines cookie requirements covering the `Secure` attribute, `__Secure-` and `__Host-` name prefixes, `SameSite`, `HttpOnly`, and a combined cookie name/value size limit. This playbook translates those requirements into a repeatable review procedure without claiming ASVS certification.

## Inputs

- representative authenticated and unauthenticated browser sessions;
- application cookie inventory or observed Set-Cookie responses;
- documented cross-site and multi-host requirements;
- session and authentication design documentation.

## Procedure

1. **Inventory cookies.** Capture cookies created during sign-in, sign-out, account changes, normal navigation, sensitive workflows, and error or recovery paths.
2. **Classify each cookie.** Identify whether it contains or references authentication state, session state, preferences, routing state, anti-forgery state, analytics, or another purpose.
3. **Validate secure transport.** Confirm security-relevant cookies use the `Secure` attribute and are never intentionally issued over plaintext transport.
4. **Validate cookie prefixes.** Prefer `__Host-` for host-bound cookies. Where sharing across hosts is explicitly required, verify the naming and scope decision is documented and that `__Secure-` is used where appropriate.
5. **Validate SameSite.** Confirm the SameSite value matches the real cross-site behavior needed by the application and does not broaden exposure without a documented reason.
6. **Validate script access.** For cookie values that should not be readable by client-side script, confirm `HttpOnly` is set and that the same sensitive value is not duplicated into script-readable storage or page content.
7. **Validate host and path scope.** Review Domain and Path behavior so cookies are not sent to unrelated hosts or paths without an explicit requirement.
8. **Check size.** Confirm the combined cookie name and value length remains within the ASVS 5.0.0 limit and that application behavior does not silently depend on oversized cookies that browsers may reject.
9. **Test lifecycle behavior.** Verify creation, rotation, expiry, logout invalidation, and replacement behavior for authentication or session cookies.
10. **Review exceptions.** Any cookie that cannot meet the preferred host, SameSite, or script-access restrictions must have a documented technical reason and compensating controls where appropriate.

## Evidence

Record the cookie name, purpose, observed attributes, expected attributes, host/path scope, tested workflow, application version, and any exception or remediation owner.

## Completion criteria

The review is complete when all security-relevant cookies have an identified purpose, observed attributes match the intended trust boundary, size and lifecycle behavior have been tested, and unresolved deviations have accountable owners.

## Sources

- OWASP ASVS 5.0.0, V3.3 Cookie Setup: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x12-V3-Web-Frontend-Security.md
- OWASP ASVS project, latest stable version information: https://owasp.org/www-project-application-security-verification-standard/
- MDN, Set-Cookie header reference: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie

## Scope note

Cookie behavior varies by browser and application architecture. Validate the deployed behavior in supported clients rather than relying only on configuration files.
