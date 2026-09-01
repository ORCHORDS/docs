# Agent Trace PII Minimization

Agent traces are built for debugging: full prompts, tool arguments, model outputs, intermediate reasoning, everything that explains why the agent did what it did. That same completeness makes traces the densest personal-data store in the system, copied to observability backends, retained on log-default schedules, and readable by whoever holds platform access. Minimization means redesigning what enters a trace so debugging value survives while personal data mostly does not. The lever is applied at capture time, not at query time, because data you never wrote cannot leak from retention.

## Scope

Applies to tracing and observability pipelines for agent systems: prompt and completion logging, tool call and result capture, distributed trace spans and their baggage, and evaluation datasets derived from production traffic. Covers classification of trace content, capture-time minimization techniques, retention policy, and access governance. Does not cover consent management, data-subject request tooling, or encryption at rest, which are complementary and required but do not reduce what exists.

## Workflow or implementation guidance

1. Inventory before minimizing. Map every trace field to the personal-data categories it can carry: direct identifiers in prompts, quasi-identifiers in arguments (account numbers, booking references), free-text content in tool results, and derived identifiers in span attributes. An unminimized field you forgot is the one that leaks.
2. Set the design principle in policy: a trace must be sufficient to reconstruct control flow and diagnose failures, not sufficient to reconstruct the user's life. Control flow needs tool names, statuses, latencies, sizes, error categories, and correlation IDs; it rarely needs payloads verbatim.
3. Replace payloads with derivatives by default. Hash identifiers to stable pseudonyms so joins still work across spans, keep sizes instead of bodies, keep record counts instead of rows, and store truncated digests of prompts keyed to a separate, access-controlled raw store with short retention for the cases where verbatim debugging is unavoidable.
4. Redact deterministically at capture. Pattern-based scrubbing for emails, phone numbers, account and card formats, and token-like strings runs in the telemetry SDK, before data crosses a network boundary. Post-ingest scrubbing leaves a window where raw values sit in buffers and agent-side files.
5. Tag what remains. Fields that may still contain residual personal data after redaction carry a classification tag the backend respects for access control and retention, so downstream consumers inherit the classification instead of guessing.
6. Gate the raw store. Where verbatim traces are genuinely needed, they live in a separate store with named-individual access, justification-on-read, and a retention measured in days. Bulk export is an audited, approved action. Debugging convenience never justifies copying raw traces into tickets, chats, or notebooks.
7. Minimize derived datasets twice. Evaluation and fine-tuning sets built from traces inherit every risk of the source; they get their own scrubbing pass, an approved retention, and a review that samples for residual identifiers before use.
8. Sample rather than capture everything. Trace sampling already exists for performance; extend it deliberately, capturing full detail for errored or escalated interactions and sparse detail for routine success, which is the opposite of what naive defaults do and aligns data exposure with debugging need.
9. Run detection as a backstop: periodic scans of the trace store for identifier patterns that slipped through, with a feedback loop into the redaction rules and a root-cause fix for each finding, not a recurring manual cleanup.

## Controls

- Capture-time redaction enforced in the shared telemetry library; direct logging calls that bypass it are lint-blocked in CI.
- Pseudonymization salt management: hashes that must not be reversible across environments use per-environment salts, and salt rotation is documented with its effect on cross-period joins.
- Retention schedules per store: trace backend, raw debug store, and derived datasets each have explicit, enforced TTLs; the raw store's is shortest.
- Access model: role-based access to classified fields, break-glass with justification for the raw store, and quarterly access reviews.
- Trace-field schema review: new span attributes and log fields require a data-classification decision before merge, recorded in the schema.

## Validation evidence

- Seeding exercise: inject synthetic identifiers (fake names, synthetic card and account formats, seeded credentials) into live agent interactions, then scan the trace backend; every seed must arrive redacted, pseudonymized, or absent, and any seed found raw becomes a documented defect with a fix.
- Reconstruction test: hand a minimization-compliant trace to an engineer unfamiliar with the interaction and measure whether they can diagnose a seeded fault; pair with a privacy reviewer confirming the same trace cannot re-identify the synthetic user, demonstrating both properties at once.
- Retention proof: backend configuration excerpts showing TTLs, plus a periodic verification that expired records are actually gone, not merely hidden.
- Access audit: sample of break-glass reads with justifications, and an access review sign-off, included in evidence packs.

## Failure modes and correction

- Free-text fields soak up personal data that structured redaction never sees, especially model outputs summarizing user content. Correction: free-text fields default to digest-or-absent capture, with the raw store as the escape valve.
- Pseudonyms become persistent global identifiers that enable tracking across environments, defeating the purpose. Correction: per-environment salts and documented rotation, accepting broken cross-environment joins as the intended cost.
- A debugging crisis leads to copying raw traces into a ticket system with uncontrolled retention. Correction: incident runbooks point at the raw store's short TTL and forbid copies; ticket hygiene is part of the post-incident review.
- Redaction rules over-match and destroy debugging value, so engineers bypass the telemetry library. Correction: measure false-positive redaction on engineering fixtures, tune rules, and keep the bypass path so narrow that using it is more work than fixing the rule.

## Limitations

Deterministic redaction misses novel identifier formats and semantic personal data ("the user who lives at the corner house"). Pseudonymized traces still support correlation attacks when joins with other datasets exist. Sampling reduces exposure probabilistically, not absolutely. And minimization always trades some debugging fidelity; the residual risk calculus depends on what your traces are connected to, so the configuration that is safe for an internal tool is not automatically safe for a consumer-facing agent.

## Canonical sources

- NIST SP 800-122, Guide to Protecting the Confidentiality of Personally Identifiable Information (PII): https://csrc.nist.gov/pubs/sp/800/122/final
- NIST Privacy Framework v1.0: https://www.nist.gov/privacy-framework
- W3C Trace Context (traceparent and trace-state fields): https://www.w3.org/TR/trace-context/
