# Partner Tier Privilege Review Cadence

## Scope

This article governs how the privileges granted to partner identities and partner-operated workloads are reviewed against the tier of the relationship. A partner may hold several tiers of access at once — read access to a shared portal, write access to a co-managed integration, administrative access to a jointly operated service, or break-glass access for an emergency. The privileges exist because of the relationship, but the relationship tier sets the upper bound and the cadence of review sets the lower bound on how often those privileges are re-examined.

The article applies the access-control posture of ISO/IEC 27001:2022 — Information security, cybersecurity and privacy protection — Information security management systems — Requirements, with particular reference to the access-control outcomes the standard requires an organization to implement. The standard's Annex A.9 (Access control) is addressed through the controls an organization itself operates; the partner access handled by those controls is the subject of this article.

The scope is the cadence and evidence of the privilege review. It does not replace the partner's own access-control program on its side of the boundary, and it does not substitute for either party's identity and access-management controls.

## Workflow or implementation guidance

1. Classify the partner relationship by tier. The tier captures the maximum privilege the relationship can hold, the review cadence that maximum privilege requires, the evidence required for continued access, and the approval chain. Tier definitions should be versioned and applied consistently across the partner portfolio.
2. Maintain an authoritative inventory of partner identities, service accounts, API credentials, certificates, group memberships, role assignments, and federated entitlements. The inventory is the basis for the review; a review without an inventory is a sample of unknown scope.
3. Define the review cadence by tier. Higher tiers require more frequent review. A plausible baseline is monthly or quarterly for tier-one administrative access, semi-annual for tier-two privileged access, and annual for tier-three standard access, with additional ad-hoc reviews on defined triggers.
4. Define the triggers for review outside the cycle: personnel change on the partner side (departure, role change, internal transfer), contract change, scope change, security incident on either side, governance finding, expired evidence, or an extended period of inactivity. The trigger should be visible to the people responsible for the review.
5. Conduct the review as a documented decision, not a passive notification. For each identity, the review must answer: is the identity still required, is the privilege still appropriate to the role, is the assignment still within the tier cap, is the evidence current, and what is the next review date.
6. Capture the decision per identity with the reviewer, the approver, the date, and the evidence consulted. Decisions should be reproducible from the record; a "no change" decision without evidence is not a defensible review.
7. Act on the review outcome within an agreed window. Removal of access should be timed to the change in role, departure, or contract change that triggered it, not to the next cycle. A privilege that was unnecessary at review and was not removed is a control failure.
8. Reconcile the review against the authoritative inventory. Identities that exist in active systems but not in the review record — and identities in the review record but not in active systems — should be investigated.
9. Audit the review itself. Periodic independent review should ask whether the cadence is being honoured, whether the approvals are genuine, and whether the actions arising from the review were completed.
10. Reconsider the cadence and the tier definitions at a defined interval. A cadence that always produces the same answer, or one that always produces a long list of changes, signals that the underlying tier or access design needs adjustment.

## Controls

Privilege review relies on access-control fundamentals. Identity lifecycle controls ensure that departures on the partner side produce timely removal on this side. Least-privilege controls ensure that the privilege granted is the minimum needed for the partner's role in the relationship. Segregation-of-duties controls prevent a partner identity from holding a combination of privileges that would allow unilateral sensitive action. Time-bound controls ensure that elevated access is granted for a defined window and not left in place. Logging controls ensure that the use of privileged access is recorded in a form that can be reviewed. Evidence controls ensure that the basis for continued access (current contract, current role, current personnel) is recorded and not assumed.

## Validation evidence

Validation evidence includes the partner tier definitions, the authoritative identity inventory, the periodic review records with reviewer and approver identification, the action logs arising from the review (provisioning and deprovisioning), the reconciliation between the review record and the operational identity store, independent audit findings, and any escalation records where the review surfaced a concern. Evidence should be sufficient to reconstruct who had access, why, and when the access was reviewed.

## Failure modes and correction

Common failure modes include access surviving the partner relationship that justified it, identities in active systems that are not in the review inventory, reviewers who do not have authority to remove access, removal actions that are queued but not executed, and the cadence slipping without acknowledgement. A serious failure is shared or generic accounts being granted tier-one access because no one took ownership of the identity lifecycle. Another is federated trust that grants more on the partner side than the tier allows because the trust relationship was not modelled at the entitlement level.

Correction begins with restoring the inventory, working through the backlog of stale identities, and re-establishing the cadence. Where the failures are systemic, the access design should be revisited: tighter tier definitions, just-in-time access, shorter review cycles, or stronger identity proofing. Repeated failure of the review to identify obvious stale identities indicates that the review has become a checkbox rather than a control, and the issue should be escalated to the security-governance function.

## Limitations

This article covers the privilege review on one side of the partner relationship — the side that grants access. The partner's own controls over its identities are governed by its own information-security management system and are not addressed here. The article does not address every access-control outcome that ISO/IEC 27001:2022 requires; it focuses on the review cadence and the tier-driven variation in that cadence.

## Canonical sources

- ISO/IEC 27001:2022 — Information security, cybersecurity and privacy protection — Information security management systems — Requirements: https://www.iso.org/standard/27001
- ISO/IEC 27002:2022 — Information security, cybersecurity and privacy protection — Information security controls (companion implementation guidance): https://www.iso.org/standard/75652.html
