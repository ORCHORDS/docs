# Tool Registry Schema Evolution Under JSON Schema 2020-12

## Scope

A tool registry lists every callable capability an agent can invoke. Each entry carries a name, a description, a schema for the arguments the model emits, and metadata the runtime uses for confirmation, rate limiting, and audit. Tool schemas change for many reasons - new required parameters, removed fields, stricter types, stricter value constraints - and most of those changes are uneventful. The events that matter are the ones where a model trained on the old schema continues to produce arguments that the new schema rejects, or worse, where the new schema silently accepts inputs the old schema would have refused.

This article covers schema evolution discipline grounded in JSON Schema 2020-12. The standard provides explicit annotation keywords for backward and forward compatibility (`deprecated`, `readOnly`, `writeOnly`) and a vocabulary for format assertions, but it provides no guidance on lifecycle governance. The lifecycle guidance is the agent-side contribution.

## Workflow or implementation guidance

1. Version the schema for every tool. Treat the schema as an API surface, with an explicit version recorded alongside the tool definition and a mapping from schema version to deployed runtime version. Tools without a version number cannot be evolved safely.
2. Distinguish additive from breaking changes under a written rule. Adding an optional field with a sensible default, adding a new enum value the runtime does not interpret as security-relevant, or relaxing a minimum cardinality are additive. Removing a field, narrowing a type, or adding a required field are breaking. The classification belongs to a registered authority, not to whoever happens to be editing.
3. For additive changes, support dual emission. Continue shipping the old schema to model contexts that have not been migrated while shipping the new schema to contexts that have, and track which schema was used per run so observed behavior can be explained. Many schema failures blamed on models are actually untriaged dual-emission gaps.
4. For breaking changes, ship a transition window in which both schemas are accepted and old arguments are coerced or mapped. The window must have a defined end and a published timeline. Windows that never end are how migration debt accumulates.
5. Use `deprecated` for fields the model should stop emitting and `x-deprecation-reason` or an equivalent vocabulary to carry the migration guidance the model can read. `readOnly` and `writeOnly` should be applied wherever the asymmetric access exists, because they prevent the model from emitting arguments the tool would only ignore.
6. Co-evolve the runtime validator. A schema accepted at registration but unenforced at runtime is decoration. Validate arguments before the tool executes, log validation outcomes with the schema version active, and reject the call on failure with a reason the model can act on.
7. When a tool accepts structured arguments that cross a trust boundary, validate against the strictest variant available rather than the lenient one. JSON Schema 2020-12 supports `oneOf` discrimination; use it to reject ambiguous or polymorphic inputs that the model could otherwise slide past.
8. Maintain a registry audit: every tool, current schema digest, deployed runtime versions accepting that schema, deprecation dates, and end-of-support dates. The audit is what makes evolutionary decisions reviewable and rollback-able.

## Controls

Registration authority should sit with the team that owns the tool's effect, not with the model consumer. The agent runtime should not self-register tools from unverified sources; every entry needs an explicit owner, purpose statement, and approval record. A schema without an owner is a schema that cannot be safely changed.

Validation logs are evidence. Capture each call's schema digest, the validation outcome, the specific rule that failed, and the version of the validator that ran. Retention should be long enough to support both incident analysis and post-deployment learning. Care is required because validation logs can include argument values that may themselves be sensitive; redact where needed but retain the structural facts needed to debug.

Keep a stable mapping from human-readable tool names to registry identifiers, and forbid registration of two tools that differ only in casing or whitespace. The model treats these as the same; the runtime must not allow ambiguity. Refuse schema definitions whose `description` text is misleading relative to observed behavior, because agents rely on those descriptions to decide whether to call a tool at all.

## Validation evidence

Evidence must show that an old schema continues to validate historical arguments after a schema revision, and that a new schema rejects the old arguments it should reject. It must show deprecation in action: a deprecated field still parsed but flagged, and the model side prompted toward the replacement via the description or `x-deprecation-reason`. It must show breaking change handling: the old schema deprecated, the new schema accepted, the transition window honored, and the old schema removed on schedule.

Show that the runtime rejected a malformed argument from a misbehaving model with an actionable error rather than silent acceptance. Show that a tool whose schema declares a write-only argument accepted the value but did not echo it back, and that a read-only argument was rejected as an input even when the model emitted one. Show the registry audit: an inventory at a point in time, with diffs against the previous inventory explaining each change.

## Failure modes and correction

A common failure is treating the schema as a developer convenience rather than a security boundary, so validation is added late, after a tool has been in production long enough to accumulate untested argument shapes. Correct by moving validation upstream of any side effect and by gatekeeping deployment of new tool versions behind validation evidence.

Another failure is schema drift in the model's mental model. The registry schema is up to date, but the model still emits old argument names because that is what it learned during training. Correct by feeding structured reminders into the prompt using the schema's own `description` and `deprecated` annotations, and by surfacing validation errors back to the model in a form it can correct against.

The most dangerous failure is dual-emission where one path coerces aggressively, masking schema violations. Aggressive coercion is appropriate for known compatibility shims and inappropriate as a default. Correct by making coercion explicit and bounded, logging the coercion event, and removing shims on the published schedule.

## Limitations

JSON Schema 2020-12 cannot express every constraint the runtime actually needs, particularly semantic constraints like "argument value must correspond to a row the caller has access to." Runtime checks must supplement schema validation. The standard's vocabulary for deprecation is descriptive, not executable; coordinating deprecation across multiple model versions and providers is operational, not standards work. Schema evolution discipline also assumes a stable registry and does not help when tools are registered dynamically at runtime from untrusted sources.

## Canonical sources

- **JSON Schema 2020-12, draft specification and release notes:** https://json-schema.org/draft/2020-12/schema
- **JSON Schema 2020-12, Release notes (annotation keywords):** https://json-schema.org/draft/2020-12/release-notes
- **IETF, JSON Schema Validation vocabulary reference (RFC 9535 - draft at citation time):** https://www.rfc-editor.org/rfc/rfc9535
