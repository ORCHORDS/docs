# NIST AAL2 Phishing-Resistant Option Review

## Trigger
Run when a service claims or targets NIST SP 800-63B-4 AAL2, before major authenticator changes, and during periodic authentication-assurance review.

## Inputs
- Current authenticator inventory.
- User populations in scope.
- Authentication protocol documentation.
- Enrollment, recovery, and fallback paths.

## Procedure
1. List every authenticator option actually offered to the in-scope population.
2. Classify each option as single-factor or multi-factor and note whether the user manually transfers an authenticator output such as an OTP or out-of-band code.
3. Evaluate phishing resistance using the current NIST definition: the protocol must prevent disclosure of authentication secrets or valid authenticator outputs to an impostor verifier without relying on user vigilance.
4. Identify at least one deployed option that satisfies the NIST phishing-resistance requirement for AAL2 availability.
5. Exercise that option end-to-end with a representative user and confirm it is genuinely available rather than only planned or documented.
6. Review enrollment, recovery, fallback, and exception paths for unintended downgrade of the assurance claim.
7. Check product, policy, and security documentation so that MFA and phishing resistance are described as separate properties.
8. Record findings, owners, and retest evidence.

## Escalation
Escalate if an AAL2 claim is made while no phishing-resistant option is available, or if OTP/out-of-band authentication is being represented as phishing-resistant.

## Evidence
- Authenticator classification matrix.
- End-to-end test of the phishing-resistant option.
- Protocol/verifier-binding evidence.
- Recovery/fallback review.
- Documentation claim review.

## Completion criteria
At least one phishing-resistant authentication option is deployed and available for the assessed AAL2 population, and the assurance claim accurately reflects the deployed authentication paths.

## Source basis
- NIST SP 800-63B-4, final July 2025: https://pages.nist.gov/800-63-4/sp800-63b.html
- NIST phishing-resistance guidance: https://pages.nist.gov/800-63-4/sp800-63b/authenticators/
