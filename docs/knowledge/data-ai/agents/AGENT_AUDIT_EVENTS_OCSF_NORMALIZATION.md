# Normalizing Agent Audit Events with OCSF

## Purpose

Agent audit records are most useful when investigators can correlate model requests, tool calls, identity changes, policy decisions, and resulting resource activity. The Open Cybersecurity Schema Framework (OCSF) provides a vendor-neutral schema organized into categories, event classes, objects, attributes, and a taxonomy. Mapping agent security events into OCSF can improve interoperability with security analytics systems without forcing every producer to use identical internal logs.

OCSF normalization is not the same as protocol tracing. Traces explain execution flow and performance; audit events preserve security-relevant facts for accountability and investigation. A deployment may export both, linked through stable identifiers. OCSF also does not prescribe storage retention, access policy, or the truthfulness of producer data. Those remain local controls.

## Implementation workflow

1. Define an agent audit-event inventory before choosing classes. Include authentication, authorization decisions, credential use, tool invocation, configuration change, data access, process activity, and administrative approval where they occur.
2. For each internal event, select the OCSF event class whose semantics match the observed activity. Do not choose a class merely because its fields are convenient. Record the schema version used by the mapping.
3. Map producer fields to standard attributes and objects. Preserve actor, authenticated identity, service, device or workload, action, target resource, outcome, time, severity, and correlation identifiers when known.
4. Use extension attributes only for agent-specific facts that have no standard representation, such as an internal run identifier or tool registry identifier. Namespace and document extensions, and do not redefine a standard attribute with conflicting meaning.
5. Validate normalized events against the selected OCSF schema and local semantic rules before export. Route invalid records to a controlled dead-letter path rather than silently dropping them.
6. Send events through an integrity-protected channel to append-oriented storage. Apply retention, access, and deletion policy based on data classification and legal requirements.

## Controls

Generate authoritative fields at trusted boundaries. A model may name a desired tool, but the tool gateway should record the resolved tool identity, authenticated caller, canonical target, authorization outcome, and actual result. Distinguish requested action from executed action. Preserve both when an adapter rewrites or narrows a request.

Use UTC timestamps with declared precision and record ingestion time separately from event time. Maintain a monotonic sequence or producer-local event identifier where possible to detect loss and duplication. Correlation IDs must not contain credentials or personal data. Never log access tokens, private keys, full session cookies, or unrestricted prompt and response bodies by default. When content capture is justified, classify, minimize, redact, encrypt, and restrict it separately.

Protect schema mappings through code review and version control. A mapping change can create a detection blind spot even when event delivery remains healthy. Apply access controls to both raw and normalized records, and log administrative searches and exports of sensitive audit data.

## Validation and evidence

Construct representative fixtures for every mapped event type and validate required attributes, enumerations, data types, time fields, and class selection. Add semantic assertions: a successful tool execution must identify the executed target; a denial must not be recorded as successful activity; and tenant identity must agree with authenticated routing context.

Run end-to-end tests that trigger a known agent operation and locate its policy event, tool event, and resource-side event using correlation data. Measure delivery lag, parse failures, dead-letter volume, duplicate rate, and sequence gaps. Periodically sample normalized records against raw producer records to detect lossy or misleading mappings.

Evidence should include the event inventory, mapping specification, schema version, validation results, transport configuration, retention policy, access-review records, and reconciliation samples. Do not claim OCSF conformance solely because field names resemble the schema; validation must cover the selected version and class semantics.

## Failure handling

If normalization fails, retain the raw event in a protected queue with an error code and mapping version. Alert on sustained failure or volume thresholds. Replay only after fixing the mapper, preserving the original event time and assigning ingestion metadata that makes the delay visible. Deduplicate using stable producer identifiers.

If the pipeline is unavailable, security-sensitive operations should follow a documented audit-availability policy. Particularly high-impact administrative actions may need to fail closed; lower-risk operations may buffer locally within strict capacity and encryption limits. On buffer exhaustion, never silently overwrite recent events. If a mapping error mislabeled outcomes or identities, issue corrected records or rebuild the affected partition while preserving evidence of the correction.

## Canonical sources

- Open Cybersecurity Schema Framework, official schema repository: https://github.com/ocsf/ocsf-schema
- OCSF, *Understanding OCSF*: https://ocsf.io/understanding-ocsf/
- OCSF schema browser: https://schema.ocsf.io/
- NIST, *Guide to Computer Security Log Management* (SP 800-92): https://csrc.nist.gov/pubs/sp/800/92/final
