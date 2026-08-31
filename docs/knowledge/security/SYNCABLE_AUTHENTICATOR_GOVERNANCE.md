# Syncable Authenticator Governance

## Purpose

NIST SP 800-63B-4 treats syncable authenticators as a distinct class of cryptographic authenticator because their authentication keys can be copied through a sync fabric to additional devices. This can improve usability and recovery, but it changes the security model: a key that can be synchronized is inherently exportable and therefore cannot satisfy the non-exportability requirement for AAL3.

This guidance provides a reusable governance pattern for deciding where syncable authenticators are appropriate and how to manage the additional risks introduced by synchronization.

## Current NIST boundary

SP 800-63B-4 Appendix B is normative. NIST allows syncable authenticators to support AAL2 when the applicable requirements are met. NIST also states that syncable authenticators SHALL NOT be used at AAL3 because synchronization requires the authentication key to be exportable.

Do not describe a synchronized passkey or other syncable authenticator as AAL3 merely because the underlying protocol is phishing-resistant. Assurance level depends on the complete authenticator and key-protection model, not only on the user experience or protocol name.

## Governance questions

Before allowing a syncable authenticator for a service, document:

1. **Target assurance level.** Confirm that the service does not require AAL3 for the authentication event.
2. **Sync-fabric operator.** Identify the service that stores, transmits, or manages synchronized authentication keys.
3. **Key protection.** Confirm that synchronized keys are protected in encrypted form and that the implementation meets applicable cryptographic requirements.
4. **Access to the sync fabric.** Confirm that access to synchronized keys is protected by controls equivalent to AAL2 multi-factor authentication as required by NIST.
5. **Local private-key use.** Confirm that authentication transactions perform private-key operations on the local device using keys generated locally or recovered through the sync fabric.
6. **Recovery implications.** Understand how account recovery or device restoration can restore synchronized authenticators and what controls govern that path.
7. **Device visibility.** Prefer implementations that let subscribers see where authentication keys have been synchronized and for which services they are used.
8. **Policy communication.** Document organization-specific restrictions and communicate them to affected users where appropriate.

## Risk model

Synchronization expands the trust boundary beyond one authenticator device. Risks can include:

- compromise of the account protecting the sync fabric;
- unauthorized device enrollment or restoration;
- weak recovery paths that bypass the intended authenticator strength;
- uncertainty about where synchronized credentials exist;
- stale credentials remaining on retired or lost devices; and
- incorrect assumptions that every WebAuthn or passkey deployment has the same assurance properties.

The presence of these risks does not make syncable authenticators unsuitable by default. It means the service owner should evaluate the complete lifecycle rather than treating the authenticator as an isolated login mechanism.

## Deployment pattern

A practical deployment review can use the following sequence:

1. Identify the transaction risk and required assurance level.
2. Determine whether synchronization is permitted for that assurance target.
3. Evaluate the sync fabric and its account-protection controls.
4. Verify that the relying-party implementation requests and validates the authenticator properties required by policy.
5. Define enrollment, device addition, recovery, revocation, and offboarding behavior.
6. Test what happens after a device is lost, replaced, or removed from the sync ecosystem.
7. Record any environment-specific restrictions for privileged or high-impact accounts.
8. Reassess the decision when the authenticator platform, sync provider, recovery process, or assurance requirement materially changes.

## WebAuthn and passkeys

NIST notes that many syncable authenticators are built on WebAuthn, but the flexibility of WebAuthn means that not every deployment automatically satisfies the requirements that apply to a particular assurance level.

Avoid using product labels such as "passkey" as a substitute for checking the relevant authenticator properties. The relying party should make its access decision from the actual security characteristics exposed by the authentication ceremony and the organization's assurance policy.

## Privileged and high-impact access

Where AAL3 is required, use an authenticator model with a non-exportable private key that satisfies the applicable NIST requirements. Syncable authenticators are not a substitute for that requirement.

For high-impact accounts that remain at AAL2, organizations may still choose stricter local policy, such as limiting acceptable sync fabrics, requiring separately managed recovery factors, or preferring non-syncable hardware authenticators. Such restrictions should be described as local risk decisions rather than as universal NIST requirements.

## Lifecycle evidence

Retain evidence appropriate to the service, such as:

- the required authentication assurance level;
- permitted authenticator classes;
- sync-fabric assumptions;
- recovery and device-addition controls;
- relying-party configuration and validation requirements;
- exception approvals;
- security-test results; and
- the date the policy was last reviewed against the current NIST publication.

## Sources

- NIST SP 800-63B-4 — Authentication and Authenticator Management: https://pages.nist.gov/800-63-4/sp800-63b.html
- NIST SP 800-63B-4 Appendix B — Syncable Authenticators: https://pages.nist.gov/800-63-4/sp800-63b/syncable/
- NIST SP 800-63 Revision 4 publication hub: https://pages.nist.gov/800-63-4/

## Scope note

This article summarizes reusable governance considerations from NIST SP 800-63B-4. It does not claim that any particular product, passkey provider, WebAuthn deployment, or ORCHORDS system satisfies a NIST assurance level.