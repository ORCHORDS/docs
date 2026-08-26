# crlf-injection-response-splitting

**Issue:** CRLF injection arises when attacker-controlled data containing carriage return (CR, %0d) and line feed (LF, %0a) characters is written into HTTP response headers, log records, or mail headers without stripping the control characters first. In HTTP/1.1, headers are delimited by CRLF, so injected line breaks let the attacker terminate the intended header and start new ones of their own, a condition classically known as HTTP response splitting: the payload can inject a full second response, set cookies, fake redirects, or write response body content. Downstream consequences include reflected XSS via injected headers, web cache poisoning when a caching proxy stores the poisoned response under a shared cache key, session cookie overwriting, and log forgery that plants fake audit entries. The bug persists because header values are still assembled by string concatenation in many code paths, and because URL-encoded CR/LF sequences survive naive decoding into header-writing sinks.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Attack surfaces

1. **Reflected parameters in response headers.** Redirect endpoints that copy a url or next parameter into a Location header, and pages that mirror user agent, referrer, or filename data into custom headers, are the classic sinks; a %0d%0a in the parameter splits the header block.
2. **Set-Cookie construction from user input.** Cookies built by concatenating user-chosen names, values, or tracking attributes can be split to overwrite the session cookie or inject HttpOnly-removing attributes.
3. **Log injection escalation.** The same CR/LF bytes written into log files forge or erase log lines, hide attack evidence, and poison log-based monitoring and alerting pipelines that parse line-oriented records.
4. **Email header injection in transactional mail.** Contact and invite flows that place user input into SMTP headers allow extra headers, BCC exfiltration, and full message-body injection, the mail sibling of response splitting.
5. **Proxy and cache interactions.** When an injected header influences what a shared cache stores, a single poisoned entry can serve malicious content to other users, converting a reflected flaw into a persistent one.

## Prevention

1. **Never assemble headers by string concatenation.** Use framework APIs that set headers as discrete name/value pairs and rely on the runtime to reject invalid characters, instead of building raw header blocks or template-rendered header sections.
2. **Reject CR and LF in every header-bound value.** Validate that any user input destined for a header, cookie, or log line contains no CR, LF, or NUL characters, applying the check after URL decoding so encoded sequences are caught; reject rather than silently strip when the field has an expected format.
3. **Allowlist redirect and header destinations.** For Location and Location-adjacent fields, validate against a list of permitted destinations or a strict pattern (origin match, relative path), which removes header injection as well as open-redirect risk.
4. **Encode for the sink, not the source.** Where logging must preserve attacker input verbatim, encode CR and LF as visible escapes such as percent-encoding or a literal marker so records cannot forge new lines while remaining analyzable.
5. **Sanitize at the mail library boundary.** Pass addresses and names through a mail library's structured address APIs, which validate and encode, rather than interpolating strings into message templates.

## Framework and protocol considerations

1. **Modern runtimes reject, but do not rely on it.** Current versions of major frameworks and servers reject header values containing CR/LF, yet older servers, custom proxies, and bespoke HTTP handling still accept them, so application-level validation remains mandatory.
2. **HTTP/2 and HTTP/3 change the mechanics, not the risk.** Binary framing eliminates literal CRLF delimiters, but intermediaries and origin servers that translate to HTTP/1.1 for upstreams can reintroduce the flaw, and header value injection still works wherever translation or logging happens.
3. **Watch generated-file and CDN pipelines.** Server-generated manifests, Sitemaps, and CDN edge logic that interpolate query parameters into response metadata inherit the same splitting surface and must validate identically.
4. **Normalize before validation order matters.** Decode once, then validate; validating before decoding passes %0d%0a through untouched and lets the sink do the decoding into a vulnerable position.

## Testing and detection

1. **Header-focused fuzzing.** Automated tests should inject raw and single- and double-encoded CR/LF, plus isolated CR and LF, into every parameter that reaches a header, cookie, log write, or mail header, asserting the response contains no attacker-named headers and logs show no forged lines.
2. **Scanner coverage plus manual sink review.** Configure DAST checks for CRLF specifically, and manually review redirect, download, export, and contact endpoints, which are the sinks scanners most often miss due to authentication or multi-step flows.
3. **Log integrity monitoring.** Alert on log lines with impossible structure, such as headers appearing mid-record or line counts mismatching between producer and consumer, which indicate active log forgery attempts.
4. **Cache canary checks.** Periodically request known cache-poisoning-prone endpoints with benign marker payloads and verify cached variants do not differ by unkeyed inputs, catching poisoning before attackers do.

## References informing this article

1. **OWASP CRLF Injection vulnerability page.** Canonical description of the injection class and header-splitting mechanics.
2. **Acunetix, Imperva, and Invicti explainers.** Mapping of CRLF injection to XSS, cache poisoning, and session cookie overwrite consequences.
3. **OneUptime fix guide (January 2026).** Current practical remediation patterns for response splitting in production stacks.
4. **HTTP/2 CRLF discussion (Security StackExchange).** Basis for the protocol-translation caveat that binary framing does not eliminate the flaw end to end.
