---
title: "Agent Memory Poisoning Review Playbook"
standard: "NIST AI 100-2 Adversarial Machine Learning Taxonomy, OWASP Top 10 for LLM Applications (LLM04 Data and Model Poisoning)"
publisher: "NIST / OWASP"
category: "review-playbook"
subcategory: "agent-security"
canonical_url: "https://owasp.org/www-project-top-10-for-large-language-model-applications/"
status: "approved"
classification: "public"
audience: "AI engineering, agent platform, security"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Memory Poisoning Review Playbook

## Trigger

An agent's persistent memory (long-term context store, knowledge base, vector index, scratchpad, or user-level profile) shows signs of being polluted by adversarial or unintended content, or a security review needs to assess the memory's integrity before the agent handles higher-risk tasks.

## Scope

The playbook covers:

- Memory stores that the agent reads on every session or per user.
- Stores that are written from agent outputs, user inputs, retrieved content, or tool calls.
- Cross-tenant or cross-user memory boundaries that could leak or cross-contaminate.

## Inputs

- Memory store inventory with owner, retention, and access policy.
- Recent memory writes and reads trace for a sampled set of sessions.
- Threat model entry for the agent's memory surface.
- Tenant boundary map showing what memory entries are scoped to whom.

## Steps

1. **Inventory memory stores.** List every store the agent reads or writes, with retention and access controls. Identify cross-tenant or shared stores.
2. **Trace memory provenance.** For each store, identify the sources that write into it. Mark sources as trusted (agent output filtered, signed), semi-trusted (retrieval with allow-lists), or untrusted (raw user input).
3. **Sample and inspect.** Pull a random sample of recent entries; look for instructions masquerading as facts, attacker-controlled URLs, prompt-like text, and entries that violate tenant boundaries.
4. **Quarantine poisoned entries.** Mark suspect entries as inactive and route them to review. Preserve the original for forensic analysis.
5. **Tighten write paths.** Filter agent outputs before they enter memory, restrict user-derived memory to safe schemas, and require confirmation for memory writes that affect security-relevant facts.
6. **Refresh embeddings.** When a vector store has been compromised, rebuild the index from a trusted source and rotate embedding keys if necessary.
7. **Schedule re-review.** Add the memory store to the periodic review calendar with a frequency tied to its risk class.

## Escalation

Escalate when:

- Memory poisoning influenced a privileged action or caused a confidentiality breach.
- Tenant boundaries were crossed by poisoned memory entries.
- A vector store was found to contain large-scale adversarial content.

Notify legal, privacy, and the security on-call rotation; pause the agent if cross-tenant leakage is confirmed.

## Evidence

- Memory inventory with risk classification per store.
- Sample trace of recent writes and reads with provenance.
- List of quarantined entries with rationale and disposition.
- Updated write-path policy and the change ticket that introduced it.

## Completion Criteria

The review closes when:

- All suspect entries are quarantined or remediated.
- Write paths are hardened against the observed poisoning vector.
- The store's owner attests to integrity or a rebuild is complete.
- A re-review cadence is documented and entered in the calendar.

## Exceptions

- **Trusted scratchpad.** Ephemeral, session-scoped memory that does not survive across sessions may operate under reduced validation.
- **Customer-managed memory.** The customer owns validation; the platform records the boundary in the agent contract.

## Related Documents

- NIST AI 100-2 Adversarial Machine Learning Taxonomy
- OWASP Top 10 for LLM Applications (LLM04 Data and Model Poisoning)
- Agent Prompt Injection Response
- Agent Audit Events OCSF Normalization
- Vector store hardening guidance
