# Privileged MFA Default Validation

## Trigger
Run before release, after privileged-authentication or account-setup changes, after entitlement/tier changes, and during periodic secure-default review.

## Inputs
- Baseline commercial/product tier.
- Privileged roles and administrative entry points.
- Fresh privileged test accounts.
- Supported MFA and phishing-resistant authentication methods.
- Bootstrap, recovery, break-glass, API, CLI, and support-admin flows.

## Procedure
1. Enumerate every path through which a privileged user can authenticate or recover administrative access.
2. Create a new privileged account using the normal baseline setup path and record whether MFA is available and whether setup defaults or strongly directs the administrator toward MFA enrollment.
3. Verify privileged MFA is not available only through an optional premium security tier when it is part of the product's baseline secure-operation model.
4. Test at least one phishing-resistant option where the product supports it and document any platform or deployment constraints.
5. Exercise API, CLI, recovery, bootstrap, break-glass, and support-admin paths and verify they do not silently bypass the intended privileged MFA posture.
6. Test account/tier migration and configuration changes for accidental removal or weakening of MFA enforcement.
7. Record adoption/default-state evidence separately from the claim that the product merely supports MFA.
8. Retest all failed paths after remediation.

## Escalation
Escalate privileged paths that unexpectedly fall back to password-only access, bypass the intended MFA decision, or require an undisclosed higher-priced tier to obtain a security capability treated as baseline.

## Evidence
- Privileged-entry-point inventory.
- Fresh-account setup result.
- Baseline-tier entitlement result.
- Phishing-resistant method test where applicable.
- Recovery/bootstrap/API/CLI test evidence.
- Findings and retest evidence.

## Completion criteria
Privileged authentication behavior matches the documented secure-default policy across normal, recovery, programmatic, and exceptional access paths, and the product accurately distinguishes MFA support from default enforcement.

## Source basis
- NSA/CISA, Top Ten Cybersecurity Misconfigurations — Secure by Design recommendations: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-278a
- CISA Secure by Design Pledge — MFA goal and example approaches: https://www.cisa.gov/sites/default/files/2024-05/CISA%20Secure%20by%20Design%20Pledge_508c.pdf
