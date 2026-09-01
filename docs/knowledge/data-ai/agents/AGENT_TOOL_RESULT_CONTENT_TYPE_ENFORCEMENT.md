# Content-Type Enforcement for Agent Tool Results

## Scope

Tool results frequently cross several interpreters: an HTTP client decodes bytes, an adapter builds structured content, a model reads text, and a renderer displays output. A mismatch between declared and actual media type can turn inert data into instructions, markup, executable content, or malformed objects. This article defines a deterministic content-type boundary for inbound tool results. It does not cover file uploads, outbound schema design, or transport authentication.

HTTP semantics make `Content-Type` a representation metadata field and prohibit recipients from casually overriding an authoritative type through content sniffing. OWASP similarly recommends explicit response types and safe handling of untrusted data. MCP defines typed content blocks, but a protocol label alone does not establish that bytes are well formed or safe for every downstream sink.

## Workflow

1. Before invocation, register the result types the tool contract permits, maximum encoded and decoded sizes, character encoding rules, and intended sinks.
2. Receive status, headers, and bytes without rendering or inserting them into a prompt. Apply transfer decoding with strict size ceilings.
3. Parse `Content-Type` according to HTTP field syntax. Reject missing, duplicate-conflicting, unsupported, wildcard, or malformed values unless the contract explicitly defines a safe default.
4. Match the normalized media type to the allowlist. Do not infer HTML, JSON, or images from filename extensions or leading bytes to rescue a mismatch.
5. Decode using the declared charset where applicable. Reject invalid sequences rather than silently replacing security-relevant characters. For JSON, require the encoding rules from the JSON specification and parse with bounded depth and member count.
6. Validate the decoded representation against its contract. Typed protocol blocks must agree with transport metadata and with the actual parser result.
7. Convert accepted data into an internal tagged value such as `TrustedJsonShape`, `UntrustedPlainText`, or `ValidatedImage`. Preserve the original type and source alongside the value.
8. Route only compatible tagged values to each sink. Plain text must be escaped before HTML display; untrusted markup must not become active UI; structured values must not be serialized into instructions without explicit delimiters and policy.

## Controls, data, and evidence

Centralize parsing in the tool gateway. Disable browser-style MIME sniffing and automatic content execution. Maintain a small media-type registry per tool and version it with the tool contract. Separate parsing from semantic trust: valid JSON may still contain hostile strings. Apply Content Security Policy and sandboxing where a UI intentionally displays active content, but prefer inert rendering.

Record tool identity, contract revision, HTTP status, declared media type, decoded size, parser selected, validation result, internal tag, rejection code, and a digest of the raw representation. Payload retention is unnecessary for routine evidence and may create data risk. Evidence should include registry approvals, parser dependency reviews, negative-test results, and samples proving that sink selection uses the internal tag rather than a filename or model judgment.

## Validation tests

Return HTML with `text/plain` and confirm it is displayed only as escaped text. Return JSON labeled `text/html`, two conflicting Content-Type fields, an unknown charset, invalid UTF-8, a JSON body exceeding nesting limits, and a compressed body that expands beyond the ceiling; each must fail predictably. Test `application/json` with duplicate keys under the chosen policy, top-level scalar values, and trailing bytes.

Provide an MCP text block whose adapter claims it is an image and verify the cross-layer mismatch is rejected. Attempt to pass validated text into an HTML-only renderer and verify the type system or runtime gate blocks it. Fuzz header parameters and quoted strings. Confirm errors do not include raw secrets or attacker-controlled markup. Regression-test every supported media type with canonical valid fixtures.

## Failure handling

On a type or parse failure, return a stable `invalid_tool_representation` error and stop dependent actions. Do not ask the model to reinterpret raw bytes. If a server recently changed its response type, quarantine that tool version and require a reviewed contract update rather than broadening the allowlist during an incident.

If decoding partially succeeds before a limit is exceeded, discard the partial object and prevent caching. If active content reaches a renderer, disable that rendering path, preserve metadata and digests, assess affected sessions, and rotate any exposed credentials according to incident procedures. A fallback may expose a download only when policy allows, with an inert attachment type and no inline execution.

## Limitations

Correct media typing does not establish truth, authorization, or absence of prompt injection. Parsers can contain vulnerabilities and need patching and isolation. Some legacy services omit metadata; supporting them requires a narrow contract-specific default and increases ambiguity. Polyglot formats and downstream transformations remain hazardous, so each transformation must produce a new validated tag. This control also cannot make inherently active content safe merely by labeling it correctly.

## Canonical sources

- **IETF, HTTP Semantics (RFC 9110):** https://www.rfc-editor.org/rfc/rfc9110.html
- **IETF, The JavaScript Object Notation Data Interchange Format (RFC 8259):** https://www.rfc-editor.org/rfc/rfc8259.html
- **OWASP, Cross Site Scripting Prevention Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- **Model Context Protocol, Server Tools:** https://modelcontextprotocol.io/specification/2025-06-18/server/tools
