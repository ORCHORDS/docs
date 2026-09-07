# LLM Provider Onboarding Playbook

## Purpose
Provide a repeatable procedure for onboarding a new large language
model (LLM) provider so teams can integrate the provider into the
platform with consistent security, evaluation, and operational
controls.

## Audience
AI platform engineers integrating LLM providers, security
reviewers performing provider assessments, and procurement
reviewers evaluating vendor contracts.

## Pre-conditions
- Business sponsor identified for the use case.
- AI risk tier assigned per the AI Risk Tiering Practice Governance
  standard.
- Provider security and privacy documentation available for review.
- Platform identity and network egress policies documented for the
  target environment.
- Evaluation harness available per the Prompt Engineering Discipline
  Governance standard.

## Procedure
1. Confirm the proposed use case is not on the prohibited-uses list
   and the risk tier is documented in the model card.
2. Review the provider's security, privacy, and data retention
   posture against the platform's AI risk tiering and data
   classification standards.
3. Negotiate contract terms covering data ownership, retention,
   deletion, training opt-out, and incident notification timelines.
4. Provision provider credentials through the platform secret
   manager; restrict access to authorised applications only.
5. Configure network egress so provider endpoints are reachable
   from approved egress paths with allow-listed domains and TLS
   pinning where supported.
6. Author system prompts and tool definitions using the prompt
   engineering discipline standard; commit to the prompt registry.
7. Run the agreed evaluation suite against the provider and record
   pass/fail results in the AI governance archive.
8. Document the rollout, including routing, fallback behaviour,
   cost controls, and rate limits, in the service runbook.
9. Submit the integration for AI governance review and capture the
   approval record before production enablement.

## Rollback
- Disable the provider credential in the secret manager so the
  application can no longer reach the endpoint.
- Remove provider-specific routing rules from the LLM gateway and
  fall back to the previously approved provider.
- Purge any cached provider responses that may contain stale
  content and audit logs for the affected window.
- Capture the failure mode in the post-incident review and update
  this playbook with any newly identified guardrails.

## References
- [AI Risk Tiering Practice Governance](../standards/AI_RISK_TIERING_PRACTICE_GOVERNANCE.md)
- [Prompt Engineering Discipline Governance](../standards/PROMPT_ENGINEERING_DISCIPLINE_GOVERNANCE.md)
- [AI Content Provenance Governance](../standards/AI_CONTENT_PROVENANCE_GOVERNANCE.md)
- [AI Model Lifecycle Playbook](AI_MODEL_LIFECYCLE_PLAYBOOK.md)
- [AI Provider Outage Response Playbook](AI_PROVIDER_OUTAGE_RESPONSE.md)
