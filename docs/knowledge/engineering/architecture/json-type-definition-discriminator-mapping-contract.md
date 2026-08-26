# JSON Type Definition discriminator mapping contract

**Issue:** A JSON Type Definition discriminator is a tagged-union contract, not a generic JSON Schema discriminator. Redefining the tag inside a variant or allowing variant-local nullability makes the schema ambiguous and invalid under RFC 8927.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Validate the JTD schema itself before generating code or accepting instance data.
- Require the discriminator property in every non-null instance and require its value to be a string key present in `mapping`.
- Allow only the JTD properties form as each mapping value.
- Prohibit the discriminator name inside a variant’s `properties` or `optionalProperties`.
- Put `nullable: true` on the outer discriminator form when null is allowed; do not set it on an individual mapping schema.
- Version tag values as durable wire identifiers and define an explicit unknown-tag rollout policy.

## Implementation and tests

Generate positive fixtures for every mapping key and negative fixtures for a missing tag, non-string tag, unknown tag, duplicate tag definition, variant-local nullability, missing required fields, and unexpected properties. Validate the fixtures with the same implementation used in production and cross-check critical schemas with an independent RFC 8927 implementation.

For rolling deployments, introduce readers that understand a new tag before writers emit it. Record schema identity and tag in event telemetry without logging the full payload.

## Gotchas and applicability

JTD rejects additional properties by default unless the applicable properties form enables them. The discriminator tag receives a specific exemption while its selected mapping is evaluated; that does not make other unspecified members valid.

RFC 8927 is Experimental, not an Internet Standards Track specification, and intentionally supports a narrower model than JSON Schema. Confirm ecosystem and code-generator support before adopting it. This contract applies to JTD; similarly named OpenAPI or JSON Schema features have different rules.

## Official sources

- [RFC 8927: JSON Type Definition](https://www.rfc-editor.org/rfc/rfc8927.html)
- [RFC 8927 status](https://www.rfc-editor.org/info/rfc8927/)
