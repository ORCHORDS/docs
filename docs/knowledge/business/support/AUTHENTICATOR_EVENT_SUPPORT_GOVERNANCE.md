# Authenticator Event Support Governance

## Purpose

Support processes that help users add, replace, renew, or invalidate authenticators can directly affect account security. NIST SP 800-63B Revision 4 treats authenticator binding, renewal, recovery, and invalidation as lifecycle events with explicit security and notification requirements.

## Support boundary

Support staff should distinguish routine authenticator lifecycle work from full account recovery:

- adding a new authenticator while the subscriber can still authenticate is a binding event;
- replacing an expiring authenticator should follow the additional-authenticator binding pattern;
- losing control of the authenticators needed for the required assurance level is account recovery;
- removing a compromised or obsolete authenticator is invalidation.

A support workflow should not silently downgrade one category into another because the verification and notification expectations can differ.

## Binding and replacement controls

When assisting with an additional or replacement authenticator:

1. Require authentication appropriate to the account and the assurance level at which the new authenticator will be used.
2. Preserve a record of authenticators bound to the subscriber account and the source of material binding events where appropriate.
3. Encourage more than one independent authentication method so a single lost device does not automatically force account recovery.
4. Treat cross-device binding codes as short-lived, one-time secrets and do not send them through insecure channels.
5. Provide a clear way for the subscriber to repudiate or report an unexpected binding.
6. Notify the subscriber through a mechanism independent of the binding transaction when a new authenticator is added.

## Invalidation and compromise

Support should provide a fast path to invalidate an authenticator when the subscriber reports loss, theft, compromise, unauthorized duplication, or another material security problem. Requests to invalidate should be authenticated using a risk-based process, but the workflow should also recognize that delaying revocation of a compromised authenticator can create greater harm than an erroneous temporary denial of service.

Where an authenticator contains personal information, the lifecycle process should include retrieval, erasure, or destruction where applicable.

## Notification governance

NIST requires independent notifications for certain account events, including authenticator binding and account recovery. A reusable support process should:

- maintain multiple reliable notification addresses where the account design permits it;
- avoid relying solely on the same channel used to perform the sensitive event;
- provide clear instructions for reporting an event the subscriber did not initiate; and
- preserve enough event evidence to investigate suspected fraudulent binding or recovery.

## Sources

- NIST SP 800-63B Revision 4 — Authenticator Event Management: https://pages.nist.gov/800-63-4/sp800-63b/events/
- NIST SP 800-63B Revision 4 — Authenticators: https://pages.nist.gov/800-63-4/sp800-63b/authenticators/

## Scope note

This article summarizes reusable support and identity-lifecycle controls. It does not define a specific application's assurance level, identity-proofing policy, or legal notification obligations.