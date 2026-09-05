---
title: "Agent Delegated Authority Response Playbook"
standard: "NIST AI 100-1 AI Risk Management Framework, OWASP Top 10 for LLM Applications (LLM06 Excessive Agency)"
publisher: "NIST / OWASP"
category: "response-playbook"
subcategory: "agent-security"
canonical_url: "https://www.nist.gov/itl/ai-risk-management-framework"
status: "approved"
classification: "public"
audience: "AI engineering, identity and access management, security"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Delegated Authority Response Playbook

## Trigger

An AI agent operates beyond its intended delegated authority — invoking tools it should not access, acting on behalf of a user it should not impersonate, exceeding scope of consent, or chaining delegated credentials into unintended downstream systems.

## Scope

The playbook applies when:

- An agent inherits user or service credentials and uses them outside the agreed scope.
- An agent's autonomy exceeds the consent captured at session start.
- Token-based delegation (OAuth 2.0, OIDC, SPIFFE, mTLS) is exploited or misused by the agent.
- An agent combines multiple delegated authorities in a way that creates new effective permissions.

## Inputs

- Delegation policy describing what authority the agent is granted and under what conditions.
- Session consent record with explicit scopes and duration.
- Audit log of credentials used, tokens minted, and tools invoked.
- Identity provider and broker configuration.

## Steps

1. **Detect the deviation.** Compare the agent's actions against the consent record and delegation policy. Flag any tool call, network request, or resource access that exceeds the granted scope.
2. **Suspend the session and rotate credentials.** Revoke the session, the delegated tokens, and any short-lived credentials the agent minted. Notify the user and the identity owner.
3. **Quarantine downstream effects.** Roll back changes, invalidate sessions, and notify any peer system that accepted an inflated scope.
4. **Investigate the chain.** Trace the prompt, tool, or policy gap that allowed the agent to exceed its authority. Identify whether the deviation was a prompt injection, a configuration error, or a logic flaw.
5. **Tighten the delegation model.** Reduce default scopes, require step-up authentication for high-risk tools, and add platform-level authorisation checks before any privileged action.
6. **Update consent UX.** Capture explicit consent for each high-risk delegation class; require re-consent on every scope change.
7. **Brief stakeholders.** Inform security, privacy, legal, and the user; refresh the customer-facing explanation of how the agent uses delegated authority.

## Escalation

Escalate when:

- Delegated authority crossed tenant boundaries.
- The agent exfiltrated credentials or minted credentials that escaped revocation.
- A regulator-facing breach resulted from the deviation.

Notify the CISO, legal, and the identity provider's trust and safety team.

## Evidence

- Consent record and delegation policy in effect at the time of the incident.
- Audit trail of credentials, tokens, and tool invocations.
- Revocation confirmation from the identity provider and downstream systems.
- Updated delegation policy and consent UX with change ticket reference.

## Completion Criteria

The incident closes when:

- All delegated credentials minted by the agent are revoked.
- Affected downstream systems confirm rollback or cleanup.
- The delegation policy is tightened and the consent UX is updated.
- A post-incident review is filed with named corrective actions and dates.

## Exceptions

- **Authorized red-team test.** Document the scope and link in the evidence register.
- **Customer-issued credentials.** Where the customer owns the identity provider, document the shared responsibility boundary in the response.

## Related Documents

- NIST AI 100-1 AI Risk Management Framework
- OWASP Top 10 for LLM Applications (LLM06 Excessive Agency)
- IETF RFC 8693 OAuth 2.0 Token Exchange
- IETF RFC 7592 OAuth Client Dynamic Registration
- Agent Authorization Boundaries
- Zero Trust Access Implementation Response
