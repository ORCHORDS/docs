# Business Logic Sequence and Step-Order Review

## Purpose

Verify that multi-step business workflows enforce the intended sequence for the same user and cannot be completed by skipping, replaying, reordering, or directly invoking later steps.

## Source basis

OWASP ASVS 5.0.0 requirement v5.0.0-2.3.1 requires applications to process business-logic flows for the same user in the expected sequential order without skipped steps. Related V2 requirements also call for documented business-logic limits and trusted server-side validation.

## Inputs

- documented workflow steps and state transitions;
- representative user roles and authorization states;
- API or route inventory for the workflow;
- test accounts and non-production test data where appropriate;
- expected completion and rollback behavior.

## Procedure

1. **Map the intended flow.** List every required step, prerequisite state, authorization decision, and completion state for the workflow.
2. **Identify server-side state.** Determine which state transitions the trusted service records and which client-supplied values could attempt to influence progression.
3. **Attempt step skipping.** Invoke later endpoints or actions without completing required earlier steps and confirm the server rejects or safely redirects the request.
4. **Attempt reordering.** Execute valid steps in an unexpected order and verify that the workflow remains in a correct state.
5. **Attempt replay.** Resubmit previously accepted requests, stale tokens, or completed-step actions and confirm duplicates cannot create a second unauthorized effect.
6. **Test cross-session behavior.** Confirm that state from one authenticated session, user, or transaction cannot satisfy prerequisites for another unless explicitly designed.
7. **Test direct API access.** Bypass the user interface and call the underlying route or API directly to ensure client-side navigation is not being relied upon as a security control.
8. **Check failure recovery.** Interrupt the flow at each material step and verify restart, retry, or rollback behavior cannot be abused to reach an invalid state.
9. **Review concurrency.** Where multiple requests can race, confirm concurrent progression cannot satisfy incompatible steps or duplicate a one-time transition.
10. **Record deviations.** Capture any sequence bypass, ambiguous state, or replay weakness with an owner and remediation target.

## Evidence

Record the workflow version, tested roles, tested step permutations, endpoint or action identifiers, observed server decisions, relevant logs, and remediation status.

## Completion criteria

The review is complete when all required steps are enforced by trusted server-side state, skipped or reordered requests fail safely, replay does not create duplicate unauthorized effects, and unresolved defects have accountable owners.

## Sources

- OWASP ASVS 5.0.0, V2 Validation and Business Logic: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x11-V2-Validation-and-Business-Logic.md
- OWASP Web Security Testing Guide, Business Logic Testing: https://owasp.org/www-project-web-security-testing-guide/

## Scope note

This playbook addresses workflow integrity. It does not replace authorization testing, transaction-integrity review, anti-automation controls, or domain-specific fraud analysis.
