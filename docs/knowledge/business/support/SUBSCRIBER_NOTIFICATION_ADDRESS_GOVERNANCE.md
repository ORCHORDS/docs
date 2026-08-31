# Subscriber Notification Address Governance

## Purpose

Notification addresses are a security control because they are used to alert subscribers about sensitive account events such as authenticator binding and account recovery. NIST SP 800-63 Revision 4 requires identity systems to maintain reliable notification paths and to notify subscribers when account information is updated.

## Governance principles

A support or account-management process should treat notification-address changes as security-sensitive profile changes rather than ordinary contact-preference edits.

1. Require authentication appropriate to the account before allowing a subscriber to change notification addresses.
2. Validate changed core attributes when required by the identity policy.
3. Notify the subscriber when information in the subscriber account is updated.
4. Maintain more than one reliable notification address where the account design supports it.
5. Keep at least one validated address for identity-proofed accounts when required by the assurance model.
6. Avoid routing all security notifications only to a newly changed address before the change has had a reasonable opportunity to be detected and challenged.

## Event notifications

NIST SP 800-63B requires certain account events to trigger independent notifications. A reusable process should send the notification to the stored notification addresses required by policy and include clear instructions for repudiating an event the subscriber did not initiate.

Examples of security-relevant events include:

- binding a new authenticator;
- completing account recovery;
- invalidating an authenticator; and
- changing account information used for security notifications.

## Abuse indicators

Escalate changes that coincide with suspicious recovery, device changes, repeated failed authentication, unusual support contacts, or requests to remove all previously trusted notification paths. The support process should preserve evidence of the old and new routing state without unnecessarily exposing personal information.

## Sources

- NIST SP 800-63A Revision 4 — Subscriber Accounts: https://pages.nist.gov/800-63-4/sp800-63a/accounts/
- NIST SP 800-63B Revision 4 — Authenticator Event Management and Account Notifications: https://pages.nist.gov/800-63-4/sp800-63b/events/

## Scope note

This article describes reusable identity-support controls. It does not prescribe a particular assurance level, messaging provider, retention period, or jurisdiction-specific breach-notification rule.