# Agent Compaction Loss Awareness

## Scope

This article covers detection and compensation for information loss that occurs when an agent runtime compacts its context window. As a long-running agent accumulates messages, tool outputs, scratch reasoning, and intermediate state, the runtime will at some point either truncate the oldest entries, summarize them, or offload them to external storage. Each of these operations is lossy in the sense that the original text is no longer available verbatim inside the context window. The article covers what critical-detail signals to preserve, how to detect silent loss, and how to structure work so that loss is bounded and reversible.

Out of scope: full-memory archival of agent transcripts, choice of compaction algorithm, and prompt-engineering strategies for fitting within a fixed context budget. This article assumes the compaction operation is a black box from the perspective of the agent code, and focuses on the contract between the agent and the runtime that performs compaction.

## Implementation workflow

Mark every item placed into the context window with a `criticality` tag at insertion time. The tag is one of `durable-decision`, `constraint`, `identity`, `pending-action`, `evidence-citation`, `tool-state`, or `transient-reasoning`. `durable-decision` covers any commitment the agent has made that other agents or downstream consumers will rely on. `constraint` covers requirements the agent must respect (tool scopes, policy limits, user preferences). `identity` covers the user identity, account identifiers, and authentication state in use. `pending-action` covers side effects the agent has scheduled but not yet confirmed. `evidence-citation` covers factual claims the agent has made, with their sources. `tool-state` covers the state of long-running tool calls and streaming connections. `transient-reasoning` covers intermediate scratch reasoning.

On compaction, the runtime preserves everything tagged `durable-decision`, `constraint`, `identity`, `pending-action`, and `evidence-citation` verbatim. It is permitted to summarize `tool-state` only with explicit acknowledgment that summarization is in effect and a reference to the offloaded canonical record. It is permitted to drop `transient-reasoning` entirely, but it must record the count and approximate size of dropped reasoning for audit purposes. These rules must be declared in the runtime's documented contract, not inferred from observed behavior.

Verify loss detection by reconstructing the context window from the post-compaction state and comparing it to a known inventory. The agent emits a `compaction-manifest` event that lists, per tag, how many entries were preserved, summarized, or dropped, and the byte budget consumed by each class. The manifest is part of the audit trail and must be signed under the task identity.

When the agent's next action depends on information that may have been summarized or dropped, the agent first queries the offload store for the canonical record. If the offload store cannot supply the record — for example, because it was evicted or because the compaction policy was misconfigured — the agent treats the situation as a fault and refuses to act on a presumed fact. The agent should not silently reconstruct the missing information from a summary it has not verified.

For long-horizon tasks, periodically force a checkpoint that explicitly captures the agent's current commitments and pending actions in durable storage, independently of any compaction event. The checkpoint is an authoritative recovery point that survives any compaction that might happen afterward. This is distinct from CDC, which captures incremental mutations; the checkpoint captures the agent's self-understood state at a logical moment.

## Controls

The compaction manifest is a controlled artifact. It must be emitted for every compaction event, must be signed by the runtime, and must be retained alongside the task's audit trail. A runtime that cannot produce a manifest is not safe to use for tasks that involve critical decisions.

Define and enforce a maximum loss budget. For tasks with a regulatory or contractual requirement, the loss budget may be zero for certain tag classes: for example, a healthcare-related task may require that `evidence-citation` entries are never dropped. The task policy must be expressible in the same criticality-tag vocabulary and must be checked against the manifest after every compaction.

Detect silent loss. Maintain an independent counter of items added to the context window per criticality class, and compare it to the manifest's reported totals. Any discrepancy is an alertable anomaly. Detection cannot rely on the runtime's self-report alone; the agent's own accounting is the second source of truth.

The offload store must be access-controlled and durable. Critical-detail records in the offload store carry the same confidentiality classification as the original context entries. The offload store is the agent's working memory; it is not a debug log and must not be exposed to operators without an explicit purpose and the appropriate authorization.

## Validation evidence

Conformance tests must cover: compaction with all critical classes preserved, compaction that summarizes `tool-state` with explicit acknowledgment, compaction that drops `transient-reasoning` with manifest emitted, attempted use of summarized state triggers an offload-store query, refusal to act when the offload store is unavailable, and detection of silent loss when the runtime under-reports drop counts. Inject a simulated runtime that drops `evidence-citation` entries without manifest updates and verify the agent detects the discrepancy.

Operational evidence includes: distribution of compaction manifest sizes, ratio of preserved-to-dropped entries by tag class, count of detected anomalies, frequency of offload-store queries, and count of refusals to act on summarized information. Reviewers should be able to reconstruct any post-compaction decision from the manifest plus the offload store.

## Failure handling

When the offload store is unavailable, the agent stops adding new critical-detail items to the context window and refuses to begin any new sub-tasks that would depend on them. In-flight tasks complete only if they can complete without further queries to the offload store. This is a fail-closed mode; the alternative — proceeding with possibly stale or reconstructed information — risks silent corruption.

When the manifest is missing or unsigned, treat the compaction as unverified. The agent pauses, emits a `compaction-unverified` event, and either restarts from a known checkpoint or escalates to a human reviewer. Never proceed on the assumption that compaction was lossless in the absence of evidence.

When a downstream consumer reports that information it relied on was missing or altered after compaction, the audit trail must allow reconstruction of which compaction event caused the change. Each compaction manifest references the pre- and post-compaction sequence numbers of the items it touched, so a post-mortem can identify the responsible event.

## Canonical sources

- NIST AI 600-1, Generative AI Profile (background reference for context integrity in long-running AI tasks): https://www.nist.gov/itl/ai-risk-management-framework
- OWASP Top 10 for LLM Applications, LLM04 Model Denial of Service (background reference for context-window resource controls): https://owasp.org/www-project-top-10-for-large-language-model-applications/
- W3C Trace Context, Level 2 (background reference for span-context continuity across compaction): https://www.w3.org/TR/trace-context/
- ISO/IEC 42001:2023, Information technology — Artificial intelligence — Management system (background reference for AI lifecycle controls): https://www.iso.org/standard/81230.html
