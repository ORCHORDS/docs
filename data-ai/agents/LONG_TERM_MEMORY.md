---
title: "Agent Long-Term Memory"
owner: "Documentation Maintainer"
status: "review"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Agent Long-Term Memory

## Purpose

Long-term memory persists selected information across tasks or sessions when that persistence provides a defined benefit and is permitted by the application's privacy, retention, and access rules.

## Memory model

Persisted memory MAY use structured records, searchable text, embeddings, or a combination of storage methods. The storage mechanism should follow the data's actual retrieval and governance needs rather than defaulting to a single technique.

A memory record can include:

- the information to retain;
- subject or scope identifier where needed;
- source or provenance;
- creation and review timestamps;
- confidence or validation state where relevant;
- retention or expiration metadata;
- access-control metadata.

## Write controls

Before storing a candidate memory, the system SHOULD determine whether it is useful, allowed to persist, sufficiently trustworthy, and scoped to the correct subject or tenant. Sensitive data MUST follow applicable minimization, access, and retention requirements.

Generated inferences SHOULD NOT be stored as confirmed facts without an appropriate validation rule.

## Retrieval controls

Retrieved memories SHOULD be treated as contextual evidence rather than automatically authoritative instructions. Retrieval SHOULD respect subject and tenant boundaries and SHOULD provide enough provenance to identify stale, conflicting, or low-confidence material.

Applications SHOULD define behavior for:

- stale memories;
- conflicting memories;
- corrected information;
- deletion or revocation;
- retention expiry;
- access changes;
- unavailable storage.

## Security and privacy

Memory storage SHOULD use least-privilege access and SHOULD avoid exposing raw personal or sensitive information to components that do not need it. Where deletion or correction rights apply, memory indexes and derived representations SHOULD be included in the lifecycle design.
