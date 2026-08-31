# Account Suspension, Termination, and Redress

## Purpose

Identity-support processes need a controlled way to suspend or terminate accounts while giving legitimate subscribers enough information to understand the action and use available redress or reactivation paths.

NIST SP 800-63A Revision 4 requires a credential service provider to promptly suspend or terminate a subscriber account under defined conditions and to notify the subscriber of the reason, reactivation or renewal options, and available redress when the subscriber believes the action was made in error.

## Suspension and termination triggers

A reusable process should define evidence and ownership for events such as:

- subscriber-requested account closure;
- confirmed or suspected account compromise;
- violation of participation rules or eligibility requirements;
- inactivity under a documented policy;
- authoritative notice of the subscriber's death;
- a valid legal instrument requiring termination; or
- closure of the identity service itself.

Support staff should not invent new termination reasons or convert a temporary security hold into permanent closure without the decision authority required by policy.

## Subscriber notice

When notice is appropriate and permitted, explain:

1. whether the account is suspended, disabled, or terminated;
2. the reason at a level that is accurate without exposing sensitive detection methods or another person's information;
3. whether reactivation, renewal, or re-enrollment is possible;
4. how the subscriber can seek redress if they believe the decision is incorrect; and
5. any time-sensitive action the subscriber must take.

For inactive accounts scheduled for termination in a federated environment, NIST SP 800-63C requires sufficient advance notice and an opportunity to reactivate before scheduled termination.

## Redress controls

A redress workflow should be independent enough to detect erroneous or stale decisions. Preserve the decision evidence, the account state before and after the action, the subscriber's challenge, and the final disposition. Successful redress should restore only the access or status actually approved rather than automatically reinstating obsolete authenticators or permissions.

## Data lifecycle

Following termination, personal information should be deleted or retained according to the documented records-retention and disposal policy and any applicable legal requirements. Account closure should also trigger review of bound authenticators, federation links, downstream provisioning, and other access that depends on the terminated identity.

## Sources

- NIST SP 800-63A Revision 4 — Subscriber Accounts, suspension and termination: https://pages.nist.gov/800-63-4/sp800-63a/accounts/
- NIST SP 800-63C Revision 4 — RP subscriber account management and inactive-account termination: https://pages.nist.gov/800-63-4/sp800-63c.html

## Scope note

This article describes reusable identity-support controls. Employment, platform moderation, financial-service closure, sanctions, legal process, and other domain-specific account termination rules may impose different or additional requirements.