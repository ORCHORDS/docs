# JSON Schema Unevaluated Properties Composition

**Issue:** Putting `additionalProperties: false` in a base schema often rejects properties introduced by `allOf`, `$ref`, or conditional branches because it only sees properties declared in the same schema object.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Pin the document to JSON Schema Draft 2020-12 with `$schema` and confirm every validator supports its applicator and unevaluated vocabularies.
- Use `unevaluatedProperties: false` at the composition boundary when properties may be evaluated by successful referenced, combined, or conditional subschemas.
- Keep `additionalProperties` for local object rules where same-schema visibility is intentional; do not mechanically replace one keyword with the other.
- Test annotations from `$ref`, `allOf`, `anyOf`, `oneOf`, `if`/`then`/`else`, and `dependentSchemas`. Only successfully applied subschemas contribute evaluated properties.
- Fail deployment if a validator ignores unknown vocabularies or silently downgrades the dialect.
- Keep property-name allowlists and business authorization outside schema evaluation when the decision depends on caller or runtime state.

## Verification
- Add a property allowed only by a composed branch and confirm it passes while a truly unknown property fails.
- Exercise both sides of each conditional and all alternatives, including failing alternatives that must not mark a property evaluated.
- Run the same corpus through every production validator and code generator and compare outcomes.

## Gotchas
`unevaluatedProperties` depends on evaluation annotations. Reordering or replacing a subschema can change which properties are considered evaluated even when local property declarations look unchanged.

## Official sources
- https://json-schema.org/draft/2020-12/json-schema-core
- https://json-schema.org/draft/2020-12/release-notes
