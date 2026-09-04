# Browser Security Header Validation

## Purpose

Validate that a web application deliberately configures browser-facing security headers and that the deployed responses match the application's documented security expectations.

## Source basis

This playbook is based on OWASP ASVS 5.0.0 Web Frontend Security requirements, especially v5.0.0-3.1.1 and v5.0.0-3.4.1 through v5.0.0-3.4.8. OWASP lists ASVS 5.0.0 as the latest stable release; bleeding-edge builds should not be treated as the production baseline.

## Inputs

- application hostname and representative routes;
- documented browser-security expectations;
- response-header samples from production or a production-equivalent environment;
- approved exceptions and compatibility requirements.

## Procedure

1. **Confirm documented expectations.** Identify which browser security features the application requires and what it should do when a client does not support them.
2. **Check HSTS.** Confirm HTTPS responses include a Strict-Transport-Security policy with an appropriate lifetime and subdomain coverage for the application's assurance target.
3. **Check CORS.** Verify allowed origins are fixed or validated against an explicit trusted-origin set. Do not allow wildcard origins on responses containing sensitive information.
4. **Check CSP.** Confirm a Content-Security-Policy header is present where required and that the policy restricts resource execution and object/base behavior. Review nonce, hash, or allowlist use according to the application's target level.
5. **Check MIME-sniffing protection.** Confirm X-Content-Type-Options is set to `nosniff` on applicable responses.
6. **Check referrer handling.** Confirm the referrer policy does not leak sensitive URL or host information beyond the intended boundary.
7. **Check framing policy.** Confirm CSP `frame-ancestors` prevents embedding by default unless a specific embedding requirement exists.
8. **Check cross-window isolation.** For document-rendering responses, verify the intended Cross-Origin-Opener-Policy value is present.
9. **Check policy reporting.** Where the assurance target requires it, confirm CSP violation reporting is configured to an approved endpoint or reporting mechanism.
10. **Test representative routes.** Sample authentication, account, upload/download, API-adjacent, error, redirect, and static-content responses so the review does not pass based on a single route.

## Evidence

Record:

- tested URLs and response types;
- observed header values;
- expected policy values;
- deviations and approved exceptions;
- remediation owner and due date for each unresolved gap.

## Completion criteria

The review is complete when representative responses match documented browser-security requirements, deviations are either remediated or formally accepted, and the evidence is retained with the exact application version or deployment identifier tested.

## Sources

- OWASP ASVS 5.0.0, V3 Web Frontend Security: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x12-V3-Web-Frontend-Security.md
- OWASP ASVS project, latest stable version information: https://owasp.org/www-project-application-security-verification-standard/
- OWASP Secure Headers Project: https://owasp.org/www-project-secure-headers/

## Scope note

Header requirements depend on application architecture and compatibility constraints. This playbook does not claim conformance with ASVS or any certification level.
