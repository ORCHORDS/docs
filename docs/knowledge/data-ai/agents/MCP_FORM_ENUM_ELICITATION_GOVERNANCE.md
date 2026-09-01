# MCP Form Enum Elicitation Governance

## Purpose

MCP form-mode elicitation lets a server ask the user for structured input through the client. The 2025-11-25 specification supports single-select and multi-select enum fields while deliberately restricting form schemas to simple, flat structures that clients can render and validate consistently.

## Schema boundary

Form elicitation uses `requestedSchema`, a restricted subset of JSON Schema. The top level is an object with primitive properties. Nested objects and general complex arrays are intentionally excluded.

Supported field classes include strings, numbers/integers, booleans, and enum schemas. All primitive types can include defaults.

## Single-select enums

For a simple single-select value, servers can use a string `enum`:

```json
{
  "type": "string",
  "enum": ["red", "green", "blue"],
  "default": "red"
}
```

When machine values need separate human-readable labels, use `oneOf` entries containing `const` and `title`. The older `enumNames` representation is legacy and the MCP schema says to use the titled single-select representation instead.

## Multi-select enums

Multi-select fields use an array whose items are restricted to enum values. For titled choices, MCP uses `anyOf` entries with `const` and `title` under `items`.

Servers can also specify `minItems`, `maxItems`, and a default array. Defaults should satisfy the same allowed values and cardinality limits the client will validate for user input.

## Governance pattern

1. Keep form schemas flat and limited to MCP-supported primitive definitions.
2. Use stable machine values in `const` and user-facing wording in `title` when labels may change independently.
3. Prefer the current `oneOf`/`anyOf` titled-enum forms rather than legacy `enumNames`.
4. Validate defaults against the enum choices and item-count limits before sending the request.
5. Allow users to review and modify form responses before submission.
6. Preserve explicit `accept`, `decline`, and `cancel` outcomes rather than treating all non-accept responses as equivalent.
7. Do not request secrets, API keys, passwords, access tokens, or payment credentials through form mode; the MCP specification requires URL mode for those sensitive interactions.

## Client rendering

Clients can render dropdowns, radio controls, checklists, or other suitable widgets, but the submitted values must match the schema's machine values. Display titles must not be substituted for `const` values unless they are intentionally identical.

## Failure modes

- Using nested objects or arbitrary arrays can exceed MCP's supported form schema.
- Persisting display titles instead of machine values can break compatibility after copy changes.
- Legacy `enumNames` use creates forward-compatibility debt.
- Supplying defaults outside the allowed enum can produce invalid pre-filled forms.
- Using form mode for credentials violates the current MCP elicitation security boundary.

## Sources

- Model Context Protocol — Elicitation, revision 2025-11-25: https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation
- Model Context Protocol — Schema Reference: https://modelcontextprotocol.io/specification/2025-11-25/schema

## Scope note

MCP defines the schema and response semantics, not a mandatory visual UI. Accessibility, localization, and interaction design remain client responsibilities.