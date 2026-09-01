# Contract Test Schema Evolution Backwards Compatibility

Contracts describe what the system does today and what consumers depend on; the gap between
those two descriptions widens every time a schema changes. A contract test that passes against
today's provider and today consumers still passes when the provider evolves the schema — and
that is exactly the moment when breakage occurs, because the schema that consumers received
yesterday is no longer the schema they receive today. Backwards compatibility is the discipline
that keeps a schema change from breaking a contract: each change is classified as
*additive*, *removal*, *tightening*, or *loosening*, and the contract test suite is the gate
that decides which categories are allowed without coordinated consumer change.

## Scope

Covers the design and verification of backwards-compatible schema evolution between
contract-tested producers and consumers, with Pact contracts as the running example but the
principles applying to any consumer-driven contract layer that operates against a JSON Schema,
Protocol Buffer, OpenAPI, or GraphQL schema. Includes change classification, schema versioning
strategies, request and response compatibility rules, and the test design that enforces them.
Does not cover the broader topic of API versioning strategy or deprecation policy beyond the
schema-evolution surface.

## Workflow or implementation guidance

1. **Classify every schema change into one of four buckets.** This classification is the gate
   between safe and unsafe evolution:
   - **Additive**: new optional field, new response variant behind a discriminator, new enum
     value that consumers treat as *unknown*. Consumers that ignore unknown fields stay
     working.
   - **Removal**: dropping a field, removing an enum value, tightening a type (for example,
     `string` to `integer`). Removal is breaking unless every consumer is confirmed to have
     migrated.
   - **Tightening**: making a field required that was previously optional, narrowing a
     numeric range, switching from `any` to a stricter type, adding a stricter regex.
     Tightening is breaking because consumers that omit the field now fail validation.
   - **Loosening**: making a field optional that was required, widening a numeric range,
     broadening a regex, removing a constraint. Loosening is technically backwards-compatible
     for existing consumers but can hide provider-side bugs if a now-accepted value was
     previously rejected for a reason.
2. **Encode the classification into the schema and the contract.** Pact's matchers are the
   practical tool here: a field declared `MatchersV3.string("any")` or
   `MatchersV3.like(...)` communicates to consumers that the provider is loose in the field.
   The schema should carry the same intent — for example, marking the field `additionalProperties:
   true` or using a `oneOf` discriminator — so the contract and the schema agree.
3. **Treat removal and tightening as breaking.** A breaking change requires either:
   - coordinated consumer migration, evidenced by every consumer's contract test against the
     new schema, *and* a deprecation window during which the previous shape still works;
   - a versioned schema surface, where consumers opt into the new version at their own pace
     while the previous version is maintained.
   In both cases the contract suite is the gate that lets the breaking change land: the suite
   either shows every consumer updated, or the breaking change is rejected.
4. **Prefer additive changes.** When a feature requires new data, add a new optional field
   rather than repurposing an existing one. Additive changes are backwards-compatible for
   consumers that ignore unknowns, which is the default for most JSON consumers. Repurposing
   a field is a breaking change even if the type is the same.
5. **Version the schema in lockstep with the contract.** A schema version `v1` and a
   contract that references `v1` should resolve to the same shape. Where multiple schema
   versions are supported, the broker matrix or schema registry should record which consumer
   versions are pinned to which schema versions, and `can-i-deploy`-style gates should treat a
   schema bump as a breaking event unless the consumer version is recorded against the new
   schema.
6. **Write regression tests that prove the classification.** A test that adds the new field
   and removes it should fail without the change set, pass with it, and prove the consumer
   behaviour under both. For Protocol Buffers and similar systems with explicit field numbers
   or tags, the regression test should reserve the removed identifier and confirm the parser
   still tolerates it.
7. **Adopt a `freeze` rule for fields that consumers depend on.** A field marked frozen in
   the schema registry cannot be removed or have its type changed without an explicit review
   and a deprecation timeline. Freezing does not prevent evolution; it forces the evolution
   to be deliberate and visible.

A representative schema evolution for a `User` resource:

- Today: `{ id: integer, email: string, name: string }`.
- Add `phoneNumber: string | null` (optional). Additive, backwards-compatible.
- Make `email` non-null. Tightening, breaking. Requires consumer migration.
- Rename `name` to `displayName`. Removal + additive; breaking unless every consumer has
  migrated.

The contract test suite for the consumer is the artefact that proves consumers are ready to
absorb each step.

## Controls

- A schema changelog where each entry is tagged with one of the four classifications and
  references the contract version(s) that absorbed it.
- A schema registry or equivalent that records which schema versions are supported and which
  consumer versions are pinned to which schema versions.
- A contract test suite that fails when a breaking change lands without all consumers having
  updated; the gate is wired to the provider's deploy pipeline.
- A pre-merge review that requires the schema classification to be declared; merges without
  classification are rejected.
- A deprecation clock for removed fields; the clock must be honoured.

## Validation evidence

- The contract test suite, replayed against the previous consumer version, passes against the
  new provider — proving the change is backwards-compatible.
- A consumer known to ignore unknown fields continues to pass after an additive change; the
  consumer's recorded behaviour is the test.
- A breaking change is observed to be rejected by the contract suite until every consumer
  version is recorded against the new schema.
- The schema changelog accounts for every field in the current schema; fields without a
  history are flagged.

## Failure modes and correction

- *Additive change breaks a consumer that does not ignore unknowns.* Document the consumer
  expectation explicitly; if the consumer cannot be changed, the additive change becomes
  effectively tightening and must be reclassified.
- *Loosening change hides a real bug.* A provider that previously rejected a malformed value
  now accepts it; downstream systems break on the malformed value. Tighten the contract
  instead of loosening.
- *Removal not communicated.* A field disappears and consumers break silently. The
  changelog and the freeze rule are the only mechanism that prevents this; ensure the field's
  consumers are tracked.
- *Tightening not coordinated.* A field becomes required and consumers that omitted it now
  fail. The fix is a coordinated rollout with consumer migration; the prevention is the
  classification step.
- *Schema and contract out of sync.* The schema says one thing, the contract says another.
  Both must be updated in the same change, reviewed together.
- *Freeze rule ignored.* A frozen field is changed anyway. The review must reject the change
  before it lands.

## Limitations

- The classification depends on knowing the consumer's behaviour. Consumers that are not
  exercised by the contract suite are invisible; their breakage will surface only at
  integration time.
- Backwards compatibility is about the schema surface; semantic changes inside a field
  (different units, different rounding, different ordering) are not detectable from the
  schema alone.
- Pact matchers and similar tools express compatibility intent, but they do not enforce it.
  The contract test only proves that a consumer built today still passes against a provider
  built today; long-term compatibility needs deliberate maintenance.
- Schema registries are operational systems; outages and misconfiguration are themselves a
  source of risk.
- Backwards compatibility does not solve data migration. A schema that adds a required field
  needs every stored record updated, which is a separate engineering problem.

## Canonical sources

- Pact Foundation, *Pact documentation* (matchers, provider verification, and contract
  evolution patterns): https://docs.pact.io/
- JSON Schema, *JSON Schema Core specification* (vocabulary for additive, removal,
  tightening, and loosening changes): https://json-schema.org/draft/2020-12/json-schema-core.html
- Pact Foundation, *Pact JS implementation* (matcher API reference and worked examples):
  https://github.com/pact-foundation/pact-js
