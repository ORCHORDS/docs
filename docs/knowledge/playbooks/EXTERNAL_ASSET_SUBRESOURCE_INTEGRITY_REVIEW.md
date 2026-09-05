# External Asset Subresource Integrity Review

## Purpose

Review externally hosted browser assets so that third-party JavaScript, stylesheets, and similar static resources are versioned, integrity-checked, and justified when they cannot meet the preferred integrity model.

## Source basis

OWASP ASVS 5.0.0 requirement v5.0.0-3.6.1 requires externally hosted client-side assets to be static and versioned and to use Subresource Integrity (SRI), or to have a documented security decision when that is not possible. This playbook turns that requirement into a repeatable operational review.

## Inputs

- inventory of scripts, stylesheets, fonts, and other browser-loaded assets;
- deployed HTML or generated page templates;
- Content Security Policy and asset-host configuration;
- dependency or release records for externally hosted resources.

## Procedure

1. **Inventory external assets.** Identify browser resources loaded from origins that are not controlled by the application operator.
2. **Confirm necessity.** For each external resource, record why external hosting is used and whether a locally hosted or first-party alternative is practical.
3. **Confirm immutability.** Prefer resource URLs that are explicitly versioned or otherwise immutable. Reject moving targets where content can change without an application release unless a documented exception exists.
4. **Validate SRI.** For applicable script and stylesheet resources, confirm an `integrity` attribute is present and contains a cryptographic digest that matches the exact deployed resource.
5. **Validate CORS compatibility.** Where cross-origin SRI requires it, confirm the resource host provides the necessary cross-origin behavior and that the application does not weaken origin policy solely to make the resource load.
6. **Check failure behavior.** Test what happens when the resource content no longer matches the configured integrity value. The application should fail safely rather than silently executing changed content.
7. **Review CSP alignment.** Confirm the Content Security Policy permits only the intended external origins and does not broadly authorize unrelated script or style sources.
8. **Review update process.** Confirm asset updates require an intentional application change that refreshes the version reference and integrity digest together.
9. **Document exceptions.** If SRI cannot be used, record the technical reason, risk owner, compensating controls, review date, and conditions that would allow the exception to be removed.
10. **Retest representative pages.** Cover pages and workflows that load different asset bundles so the review does not miss route-specific dependencies.

## Evidence

Record the external origin, resource URL, version or immutability mechanism, observed integrity digest, CSP allowance, exception status, tested application revision, and remediation owner where applicable.

## Completion criteria

The review is complete when externally hosted client-side assets are inventoried, static/versioned resources use SRI where applicable, exceptions are documented, and the deployed resource set matches the approved evidence.

## Sources

- OWASP ASVS 5.0.0, V3.6 External Resource Integrity: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x12-V3-Web-Frontend-Security.md
- OWASP ASVS project, latest stable version information: https://owasp.org/www-project-application-security-verification-standard/
- MDN, Subresource Integrity: https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity

## Scope note

SRI primarily applies to browser-fetched resources whose bytes can be integrity-checked by the browser. It does not replace dependency governance, CSP, vendor review, or secure release controls.
