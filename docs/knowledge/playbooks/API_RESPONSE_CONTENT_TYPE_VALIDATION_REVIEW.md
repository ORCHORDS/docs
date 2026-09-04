# API Response Content-Type Validation Review

## Purpose

Verify that API and web-service responses declare a Content-Type that matches the actual message body and includes an appropriate character encoding where the media type requires it.

## Source basis

OWASP ASVS 5.0.0 requirement v5.0.0-4.1.1 requires every HTTP response with a message body to contain a Content-Type header that matches the real content, including a safe charset parameter where applicable.

## Inputs

- representative API endpoint inventory;
- sample success, validation-error, authorization-error, and server-error responses;
- documented response media types and API schemas;
- gateway, proxy, framework, and serialization configuration.

## Procedure

1. **Inventory response types.** Identify JSON, XML, text, HTML, file, stream, and other response bodies the service emits.
2. **Sample success and error paths.** Capture headers and bodies for normal responses and for validation, authorization, not-found, rate-limit, and internal-error paths.
3. **Compare declaration to content.** Confirm the Content-Type accurately identifies the actual payload rather than a framework default or stale route configuration.
4. **Check charset handling.** For text-based media types where a charset is relevant, confirm the declared encoding matches the bytes actually returned.
5. **Check empty responses.** Verify status codes and endpoints intentionally returning no body do not accidentally attach misleading content metadata.
6. **Review generated downloads.** Confirm downloadable files use the intended media type and do not fall back to a dangerous or misleading generic type when a specific type is known.
7. **Review proxy transformations.** Ensure gateways or intermediary services do not rewrite the body without also preserving correct response metadata.
8. **Test content negotiation.** Where Accept or similar negotiation is supported, verify unsupported media types fail safely and supported variants return the correct declaration.
9. **Check security-sensitive errors.** Error pages or fallback HTML should not be mislabeled as JSON or another API format in ways that could trigger unintended client interpretation.
10. **Record deviations.** Document mismatches, affected endpoints, client/security impact, and remediation owner.

## Evidence

Record endpoint, request variant, status, Content-Type value, observed payload format, charset behavior, application revision, and remediation status.

## Completion criteria

The review is complete when representative response bodies and declared media types agree across success and failure paths, character encoding is unambiguous where required, and unresolved mismatches have accountable owners.

## Sources

- OWASP ASVS 5.0.0, V4 API and Web Service: https://github.com/OWASP/ASVS/blob/v5.0.0_release/5.0/en/0x13-V4-API-and-Web-Service.md
- IANA Media Types registry: https://www.iana.org/assignments/media-types/media-types.xhtml

## Scope note

This playbook validates response metadata correctness. It does not replace output encoding, schema validation, or browser content-sniffing protections.
