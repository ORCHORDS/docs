# A2A File and Structured Data Parts

## Purpose

A2A `Part` objects provide a common container for text, file content, file references, and structured data. Correctly enforcing the one-of content model prevents ambiguous payloads and reduces the risk of treating untrusted bytes, URLs, or JSON as interchangeable data.

## Current part model

A current A2A Part contains exactly one of:

- `text` — string content;
- `raw` — file bytes, represented as base64 in JSON;
- `url` — a URL pointing to file content; or
- `data` — arbitrary structured JSON data.

Optional `filename`, `mediaType`, and metadata fields can describe the selected content.

## Practical controls

1. Reject a Part that supplies more than one primary content member.
2. Treat `mediaType` as descriptive metadata, not proof that content is safe or correctly typed.
3. Apply size limits before decoding large `raw` payloads.
4. Validate remote `url` destinations against SSRF and network-access policy before fetching them.
5. Scan or sandbox untrusted file content before opening or executing it.
6. Validate structured `data` against the application's expected schema before acting on it.
7. Preserve filenames only as labels; do not concatenate untrusted filenames directly into filesystem paths.
8. Avoid logging raw file data or sensitive structured payloads unnecessarily.

## Version note

A2A 1.0 uses member presence as the discriminator for Part variants. Older patterns that used a separate `kind` wrapper should not be assumed to match the current representation.

## Sources

- A2A Protocol — current specification, Part object: https://a2a-protocol.org/dev/specification/
- A2A Protocol — current specification, v1.0 migration examples for Part union types: https://a2a-protocol.org/dev/specification/

## Scope note

A2A defines transport semantics. Malware scanning, URL fetching policy, content retention, privacy, and application-level schema validation remain deployment responsibilities.
