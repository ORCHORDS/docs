# Agent Explainability Summaries

## Scope

This article covers the generation of calibrated, evidence-anchored explanations of agent decisions for human reviewers. The explanations are summaries in the sense that they condense a long chain of model calls, tool invocations, and intermediate reasoning into a narrative a reviewer can follow. They are calibrated in the sense that every claim in the summary is bound to a citation in the underlying trace, and the reviewer's confidence in a claim can be traced back to the evidence that supports it.

Out of scope: full replay of every model call and tool response (which is impractical for human review), training-time interpretability techniques such as probing or attention visualization, and counterfactual reasoning ("what would have happened if the agent had chosen differently"). This article addresses the runtime production of summaries that accompany decisions, not the research literature on interpretability.

## Implementation workflow

Define a structured `Explanation` type with at least the following fields: `decision` (a short statement of what the agent did or decided), `intent` (the goal or task that motivated the decision), `inputs` (the data the agent relied on at decision time), `evidence_chain` (an ordered list of trace span references that constitute the path from intent to decision), `alternatives_considered` (the choices the agent evaluated and rejected), `uncertainty` (the agent's own confidence expressed as a structured measure, not as a single probability), `policies_applied` (the policy rules that were relevant), and `human_review_hints` (what the reviewer should focus on).

Generate the summary at decision time, not on demand. Producing the summary later (when the reviewer requests it) risks referencing trace spans that have been compacted, summarized, or evicted from the trace store. The summary is a durable artifact that survives the same lifecycle as the decision itself, including compaction, archival, and audit retention.

Bind every claim in the summary to a specific evidence anchor. An evidence anchor is a (trace_id, span_id, attribute_path) tuple that resolves to a concrete datum in the trace. The reviewer can click through to the anchor and see exactly what the agent saw at decision time. This pattern is consistent with the W3C Trace Context model and the OpenTelemetry GenAI semantic conventions.

The `uncertainty` field is structured. It includes, at minimum, the model's own self-reported confidence (if available), the number of independent reasoning paths that converged on the decision (for majority-vote patterns), the entropy or variance across those paths, and any explicit caveats the agent emitted about its confidence in this decision. Calibrated uncertainty communicates when a reviewer should weigh the agent's conclusion heavily and when they should treat it as one input among several.

The `alternatives_considered` field is mandatory. An explanation that only describes the chosen path gives the reviewer no basis for evaluating whether the agent considered the right alternatives. The agent records, for each rejected alternative, a brief reason for rejection and the evidence that supported the rejection. If the agent did not consider meaningful alternatives, the explanation says so explicitly — that absence is itself information for the reviewer.

The summary is reviewed by the agent itself before release. The agent checks that every evidence anchor resolves, that the alternatives list is non-empty unless the decision was deterministic, that the policy references match the policy version in effect at decision time, and that no personally identifying information appears outside the explicit `inputs` field. The summary is then signed under the task identity and appended to the task's audit trail.

## Controls

Summaries are access-controlled at the same level as the underlying trace data. A reviewer authorized to see the agent's decisions for a task is authorized to see the summary; a reviewer authorized to see only the decision outcome is not. The summary itself contains pointers to the trace, but the trace is fetched under the reviewer's own credentials at click-through time, not bundled into the summary.

Treat the explanation as a liability surface. A summary that inaccurately describes the agent's reasoning is worse than no summary, because the reviewer may act on the explanation rather than on the underlying evidence. The agent must never assert a fact about its own reasoning that is not anchored in the trace. If the trace has gaps (for example, because a span was evicted before the summary was generated), the summary says so explicitly rather than papering over the gap.

Suppress personal information in the summary by default. Names, email addresses, identifiers, and free-form text from users should be replaced with opaque references unless the reviewer has a documented purpose and an authorization to see them. The W3C Trace Context security guidance and the OpenTelemetry data minimization guidance both support this practice.

The explanation format is versioned. A summary produced under explanation schema version N must remain valid under version N even when the underlying trace evolves. When the schema changes, summaries continue to be readable using the version they were produced under, and a migration path handles the transition.

## Validation evidence

Conformance tests must cover: summary generation with all required fields, evidence anchor resolution for every claim, refusal to release a summary with unresolved anchors, behavior under trace compaction (the summary is generated before compaction), structured uncertainty with at least one quantitative measure, alternatives list that is non-empty for non-deterministic decisions, missing-alternatives flag when no alternatives were considered, and PII suppression by default. Inject a simulated trace with a deliberately broken anchor and verify the summary is rejected for release.

Operational evidence includes: summary completeness rate (what fraction of decisions have all required fields), evidence anchor resolution rate at click-through time, count of summaries suppressed for unresolved anchors, distribution of `uncertainty` values across decision types, and reviewer feedback scores on summary quality. Reviewer feedback is itself an input to explanation quality monitoring.

## Failure handling

When a summary cannot be generated because of trace gaps or policy mismatches, the agent does not release the decision to downstream consumers until the explanation problem is resolved. The decision is held in a pending-explanation queue, and an operator is notified. The default is to delay rather than to release an unexplained decision; the agent does not silently drop the explanation requirement.

When a reviewer reports that a summary is inaccurate or misleading, the discrepancy is itself an audit event. The agent (or its post-incident process) reconstructs the trace and compares the summary against it; the discrepancy and the corrective action are added to the audit trail. Recurring discrepancies trigger a review of the summary generation logic.

When the summary schema version is retired, existing summaries remain accessible under their original version. New summaries are produced under the current version; a transition period allows both formats to coexist. Migration tooling, if used, must be auditable and reversible.

## Canonical sources

- NIST AI RMF, AI 600-1 Generative AI Profile (background reference for explainability and interpretability in AI systems): https://www.nist.gov/itl/ai-risk-management-framework
- W3C Trace Context, Level 2 (canonical model for trace span anchoring): https://www.w3.org/TR/trace-context/
- OpenTelemetry GenAI Semantic Conventions (canonical reference for trace attributes for generative AI workloads): https://opentelemetry.io/docs/specs/semconv/gen-ai/
- ISO/IEC 42001:2023 (background reference for AI management system controls including transparency): https://www.iso.org/standard/81230.html
