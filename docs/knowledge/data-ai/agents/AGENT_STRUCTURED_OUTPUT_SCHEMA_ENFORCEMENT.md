# Agent Structured Output Schema Enforcement

When an agent's output feeds a parser, an API, or a downstream agent, "mostly JSON" is a failure. Enforcing a JSON Schema on agent output means deciding, before generation, what shapes are acceptable, and after generation, running a validation tier that repairs what it safely can and rejects what it cannot. The design questions are where validation lives, how strict each tier is, how repair is bounded so it cannot invent facts, and what the rejection path does. This article lays out an enforcement pipeline with those tiers explicit.

## Scope

Applies to agent deployments that require machine-consumable output: JSON documents conforming to a JSON Schema, emitted either directly by the model or by a post-processing step. Covers schema authoring for agent outputs, tiered validation, bounded repair, rejection semantics, and monitoring. Does not cover tool argument validation on inbound calls, prompt-injection filtering of content embedded inside valid structures, or schema evolution governance for long-lived APIs, which are separate concerns.

## Workflow or implementation guidance

1. Author the schema for validation value, not documentation value. Every field the downstream consumer actually reads gets an explicit type; enums are closed where the domain is closed; required lists are honest; `additionalProperties: false` on objects you fully control, so stray fields fail loudly during development instead of migrating silently into contracts.
2. Prefer the strictest supported dialect your tooling handles, and pin it. A schema is an executable contract; an ambiguous keyword set is a latent outage. Record the dialect with the schema and validate with a conformant validator, not ad hoc field checks scattered in consumers.
3. Tier the validation. Tier 0, lexical: the output parses as JSON at all, within size and depth ceilings. Tier 1, structural: types, required fields, enum membership, array bounds. Tier 2, semantic: formats (dates that are real dates, URIs that parse), cross-field constraints (end after start, totals that sum), and business rules that only your domain knows. Each tier produces distinct error codes.
4. Decide response per tier before deployment. Tier 0 failures are rarely repairable; they usually mean truncation or prose contamination, and go to repair only for trivial cases like surrounding code fences. Tier 1 failures are the sweet spot for bounded repair. Tier 2 failures are semantic lies, and repairing structure cannot fix them; they reject or re-generate.
5. Bound repair mechanically. Repair may: strip wrapper fences, fix well-known syntax slips (trailing commas, single quotes) via a deterministic fixer, or re-request generation once with the validation errors quoted back. Repair may never: fill missing required fields with guessed values, coerce values across incompatible types to force validity, or silently drop failing array elements to satisfy bounds. A repair that changes meaning is a rejection.
6. Count repair attempts and log them separately from clean passes. One re-request ceiling per output; a second failure rejects. Unbounded "try until valid" loops turn schema enforcement into a cost leak and, worse, select for confidently invalid output.
7. Reject with structure. A rejected output produces a typed error carrying the tier, the validator's JSON path to the failure, and a redacted excerpt for logs. Downstream consumers receive the error, never the invalid document, and never a best-effort parse of it.
8. Where the model supports constrained decoding or structured output modes, use them as generation-time assistance, but keep the validator. Provider-side guarantees vary by version and mode, and only your validator enforces the semantics of your schema, especially at Tier 2.
9. Monitor the whole pipeline: parse-failure rate, per-tier failure rates, repair rate, re-request rate, and rejection rate, sliced by schema version and model version. A rising Tier 1 rate after a model change is your earliest signal.

## Controls

- Schema registry with versioning: every schema has an identifier and version referenced in prompts and validation logs, so a validation result is always attributable to an exact contract.
- Validator conformance tests: the validator itself is tested against the schema dialect's test suite subset for the keywords you use, plus fixtures for each schema you run.
- Repair allowlist: the deterministic fixers are enumerated and unit-tested; anything outside the list is not repair, it is rewriting, and is prohibited.
- Size and depth ceilings on inputs to the validator to prevent pathological documents from becoming a denial-of-service vector.
- Change control: relaxing a schema (opening an enum, dropping required) is a reviewed decision with downstream-consumer sign-off, because relaxations silently become load-bearing.

## Validation evidence

- Fixture matrix per schema: valid documents across the representable range; each Tier 1 and Tier 2 violation isolated one at a time; combined violations; truncated JSON; JSON wrapped in prose and code fences; documents exceeding depth and size ceilings. Every fixture produces its documented tier code and disposition.
- Repair boundary tests: a fence-wrapped valid document repairs clean; a document with a missing required field does not gain an invented value; a failing enum does not get coerced; each demonstrated in the logs.
- End-to-end test: a consumer receives either a valid document or the typed rejection, never an invalid document, under a chaos run where the model is deliberately prompted to emit broken output.
- Trend evidence: failure and repair rates by tier across model and prompt versions, attached to release records.

## Failure modes and correction

- Schemas accrete optional fields until everything validates and nothing means anything. Correction: quarterly schema review measuring optionality ratio; every optional field justifies itself or becomes required or removed.
- Repair fixers grow "one more" convenience rule until they rewrite content. Correction: the repair allowlist boundary is enforced in review, with any new fixer requiring a demonstration that it cannot change parsed meaning.
- Error messages quote the whole invalid document into logs, leaking personal data that would never have passed Tier 2. Correction: redaction applies to validation logs identically to transport logs; excerpts are hash-identified, with full documents only in a sealed debug store.
- Provider structured-output mode changes semantics between versions and Tier 2 silently stops firing. Correction: canary fixtures run against every model version bump, and the validator remains authoritative regardless of mode.

## Limitations

Schema validation constrains shape and, weakly, semantics; it cannot judge truth, relevance, or safety of field values, so it composes with, rather than replaces, content-level controls. Very loose domains resist closed enums, shifting enforcement weight onto downstream consumers. Constrained decoding reduces but does not eliminate invalid output, particularly around semantics. And aggressive strictness on the wrong contract front-loads failures onto users in exchange for internal cleanliness, so the tiering must be tuned to where failures are cheapest to absorb.

## Canonical sources

- JSON Schema Specification, draft 2020-12: https://json-schema.org/draft/2020-12/json-schema-core
- JSON Schema Validation Specification, draft 2020-12: https://json-schema.org/draft/2020-12/json-schema-validation
- RFC 8259, The JavaScript Object Notation (JSON) Data Interchange Format: https://www.rfc-editor.org/rfc/rfc8259
