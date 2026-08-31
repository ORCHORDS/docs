# Support-Assisted Account Recovery

## Purpose

Support-assisted recovery is a high-risk path for restoring account access when a subscriber has lost control of the authenticators normally used to sign in. Recovery should not become a weaker substitute for authentication or a route by which a support representative can bypass established assurance requirements.

NIST SP 800-63B Revision 4 distinguishes account recovery from ordinary authentication and recognizes saved recovery codes, issued recovery codes, recovery contacts, repeated identity proofing, and documented application-specific recovery methods. It also requires recovery notifications so subscribers can detect fraudulent recovery activity.

## Recovery boundary

Treat support-assisted recovery as a controlled exception path. Before allowing a support representative to participate, define:

- which account states are eligible for assisted recovery;
- the maximum assurance level the recovered account can reach;
- which recovery methods are acceptable for that account;
- which evidence a support representative may view or request;
- which actions require escalation or a second reviewer; and
- what activity is prohibited even if the requester appears credible.

A support representative should not be able to reset or replace authenticators merely because a caller knows profile information, recent transactions, an address, or other information that could be obtained through compromise or social engineering.

## NIST recovery model

NIST SP 800-63B-4 recognizes four general classes of account-recovery method:

1. **Saved recovery codes** maintained by the subscriber for later use.
2. **Issued recovery codes** sent to a verified recovery address.
3. **Recovery contacts** designated by the subscriber.
4. **Repeated identity proofing** when the account was previously identity-proofed.

A CSP may also support an application-specific method, including interaction with a CSP agent, when that method is based on a documented risk analysis.

Support workflows should therefore orchestrate approved recovery mechanisms rather than inventing an informal identity check at the time of the incident.

## Assisted recovery workflow

1. **Classify the request.** Determine whether the request is true account recovery, authenticator replacement while another authenticator remains available, or a different support action.
2. **Assess account risk.** Consider the account assurance level, privileges, recent suspicious activity, recovery-address changes, and evidence of account takeover.
3. **Select an approved recovery path.** Use only recovery methods documented for the account class and assurance level.
4. **Separate guidance from proof.** Support may explain how to complete a recovery method, but should not disclose secrets, recovery codes, or answers that satisfy the method.
5. **Escalate anomalies.** Pause recovery when signals suggest impersonation, coercion, SIM-swap risk, compromised email, forged evidence, or repeated failed attempts.
6. **Bind new authenticators only after recovery succeeds.** Recovery establishes the right to regain control; authenticator binding is a separate controlled action.
7. **Notify the subscriber.** Send the required recovery notification through an appropriate channel so unauthorized recovery can be detected.
8. **Record the event.** Preserve the method used, decision path, significant risk signals, approvals, and outcome without storing unnecessary authentication secrets.

## Assurance-level considerations

NIST sets stronger recovery combinations for higher-assurance accounts. For an account that can authenticate at AAL2, recovery generally requires either two recovery codes obtained through different recovery methods, one recovery code plus an available single-factor authenticator, or repeated identity proofing when the subscriber account was identity-proofed.

Recovery of accounts capable of AAL3 requires additional care, particularly when the underlying account was identity-proofed at IAL3. Do not downgrade a high-assurance account to an informal help-desk verification process simply because normal authenticators are unavailable.

## Recovery-address governance

Recovery addresses are themselves security-sensitive. Where an address was not validated or verified as part of identity proofing, NIST requires verification before it becomes a recovery address. Operational controls should therefore:

- prevent support staff from silently replacing a recovery address during the same interaction that uses it;
- notify subscribers of material recovery-address changes;
- consider waiting periods for high-risk address changes;
- expose recovery-address management to authenticated subscribers where appropriate; and
- treat recent address changes as a risk signal during recovery.

## Recovery codes

Saved and issued recovery codes should be treated as authentication secrets. Support personnel should never ask a subscriber to disclose more secret material than the recovery protocol requires and should not copy codes into tickets or chat transcripts.

NIST requires saved recovery codes to be invalidated after use and replaced. Issued recovery codes have bounded validity periods and are subject to throttling. Implementations should enforce those limits in the recovery system rather than depending on staff memory.

## Fraud and social-engineering controls

Common warning signs include:

- urgency combined with pressure to bypass normal controls;
- a request to change recovery channels before using them;
- inability to use any previously established recovery method;
- repeated failed recovery attempts;
- conflicting identity or account-history information;
- requests involving privileged, financial, or administrative accounts; and
- a recent device, phone-number, email-address, or password change.

Support scripts should make it acceptable to stop and escalate. A representative should not be penalized for refusing a recovery that cannot meet the documented assurance requirements.

## Notifications and review

Every completed account-recovery event should generate a subscriber notification consistent with the service's recovery policy. High-risk systems may also notify on failed or abandoned assisted-recovery attempts when doing so does not create additional abuse risk.

Periodically review assisted recovery for:

- recovery volume and success rate;
- fraud confirmed after recovery;
- methods most frequently used;
- exception and escalation rates;
- repeated recovery by the same accounts;
- recovery-address changes near recovery events; and
- cases where staff departed from documented procedures.

Metrics should be used to improve the recovery design rather than to pressure support staff into approving risky requests.

## Sources

- NIST — SP 800-63B Revision 4, Authentication and Authenticator Management, Account Recovery: https://pages.nist.gov/800-63-4/sp800-63b.html#accountrecovery
- NIST — SP 800-63 Revision 4 overview: https://pages.nist.gov/800-63-4/

## Scope note

This article describes reusable account-recovery governance. It does not claim that a particular service meets a NIST assurance level, and it does not replace a system-specific risk assessment or identity-proofing design.