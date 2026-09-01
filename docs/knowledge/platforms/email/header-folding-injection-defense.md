# Header Folding Injection Defense

Header injection is what happens when data crosses into the header section carrying its own structure. The email header format allows long fields to fold across lines: a CRLF followed by whitespace continues the previous logical line, and unfolding - removing the CRLF immediately preceding whitespace - reconstitutes the original. That folding rule is also the injection primitive. A recipient-supplied display name containing a CR or LF can, on naive composition, terminate the current header early and start fresh headers chosen by the attacker: additional recipients, a rewritten Subject, injected List-Unsubscribe, or BCC copies of password-reset mail. The defense is boundary discipline - treat every value entering a header as untrusted structured input, and normalize or reject control characters before they reach the composer - because once a bare CRLF sits inside a header value, whether it becomes a fold, a break, or a smuggled header is decided by whatever parses it next.

## Scope

This article covers defense against header injection via folding and raw line-terminator injection in email composition: where untrusted values enter headers, how folding turns controlled characters into structure, sanitization and encoding strategy, and verification that downstream parsers cannot be coerced. It applies to mail-generation code - application builders, template renderers, list managers - and to gateways composing headers from external data. It does not cover SMTP command smuggling (a distinct CRLF problem at the protocol layer), MIME boundary injection, or HTML content sanitization.

## Workflow or implementation guidance

**Map the entry points.** Enumerate every header field whose value derives from user input or external systems: display names, recipient addresses from forms, Subject lines, Reply-To, List-Unsubscribe URIs built from tokens, custom headers carrying IDs, and template variables interpolated into headers. The map is the threat model - injection only happens where untrusted data meets header syntax.

**Reject or encode at the boundary.** For each entry point, choose one policy and apply it consistently. Strict rejection: any value containing CR or LF, bare or paired, is refused at validation - simplest to reason about, and correct for address fields where such content is never legitimate. Structural encoding: for free-text fields like display names and Subjects, use RFC 2047 encoded-words or RFC 2231 continuations, which represent non-ASCII without admitting raw control characters. Never pass the raw value through and trust the composer to cope.

**Normalize before validation.** Attackers deliver bare CR, bare LF, CRLF, and occasionally Unicode line separators that later libraries convert to CRLF. Normalize all of these to a canonical form first, then validate, so the check cannot be bypassed by an alternative byte sequence that downstream code canonicalizes differently. Validation must run on the normalized value, and the normalized value is what flows onward.

**Never construct folds from untrusted data.** Legitimate long headers are folded by the composer, which inserts CRLF-plus-WSP at safe points under its control. Application code that manually concatenates CRLF and whitespace into user values to prettify long subjects is writing the attacker's payload. Folding is a serialization decision; make it exclusively in the serialization layer.

**Encode at the MIME layer.** Subjects and display names containing non-ASCII must be encoded-words; unstructured headers stay within line-length bounds by composer-driven folding. This keeps the entire header grammar under one implementation's control rather than split between application logic and library heuristics.

**Verify downstream tolerance.** Confirm the receiving MTA's parser treats a bare CR or LF in a header value as data or an error - never as a line boundary creating new structure. Test against your actual MTA and intermediate gateways, because the blast radius of a missed injection is set by the most permissive parser in the chain.

## Controls

- Central header-value validation library used by every composer path; no email-sending code constructs headers by string concatenation outside it.
- Normalization-then-validation ordering enforced in the library API, so bypass via alternate line terminators is structurally impossible.
- CR/LF rejection for address fields and URI-valued headers; encoded-word handling for display text.
- Template constraint: header templates rendered through the same library, interpolation points typed as header-safe or rejected.
- Length limits per header field applied at composition, folding performed only by the serializer.
- Fuzzing harness feeding line-terminator variants - CR, LF, CRLF, Unicode separators, mixed - into every entry point, asserting no attacker-controlled headers emerge.
- Round-trip parse test: composed messages re-parsed by an independent MIME parser, header sets compared to intent.
- Gateway ingress lint flagging inbound messages with bare CR/LF inside header values, revealing other senders' broken composers.

## Validation evidence

- Fuzz corpus results showing zero injected-header cases across all entry points, including CRLF, bare CR, bare LF, and canonicalized Unicode separators.
- A deliberate attack fixture - a display name containing CRLF plus `Bcc: attacker@evil.example` - emitted as a rejection or safely encoded value, with the raw wire bytes captured.
- Independent re-parse of production-bound message samples confirming header sets match composer intent exactly.
- Gateway lint statistics over inbound traffic quantifying malformed folded headers in the wild.
- Regression suite executed in CI on every composer library change.
- Coverage report mapping each enumerated entry point to its validation test.

## Failure modes and correction

Injected headers observed at the receiving side mean some composer path bypassed the central library - usually a template rendered by a different engine or a quick custom notification sender; route it through the library and add the path to the entry-point map. Validation passing bare CR through as "just data" holds only until a downstream library canonicalizes CR to CRLF during transport, converting data back into structure; the normalization control exists to close exactly this, so verify it runs first everywhere. Encoded-word fields breaking past line limits indicate the composer folds at safe points but the application pre-wraps; remove application-level wrapping. Subjects rendering with stray equals signs point at double encoding - encode once, at the boundary. Template interpolation typed "trusted" because data originated internally is the classic drift into injection - internal systems get compromised too, and the typing should track data sensitivity, not data owner. Unicode line separators slipping past an aging validator mean the normalization table needs updating; treat parser-library updates as security-relevant changes requiring the full fuzz corpus run.

## Limitations

Defense is per-composer-path, and completeness depends on the entry-point map staying current as applications evolve - no framework makes unlisted paths safe automatically. Downstream parser behavior is outside your control: a sufficiently permissive receiving MTA can still create structure from malformed input emitted before defenses existed, so historical message stores may contain latent injections. Unicode canonicalization varies across libraries and runtimes, making normalization a moving target. Encoded-word transport constrains header content with size overhead and display quirks in old clients. Detection at the application layer is weak - successful defenses reject quietly, so abuse telemetry requires deliberately instrumented logging that privacy constraints may bound. Header injection overlaps adjacent problems (MIME parameter injection, SMTP smuggling) whose defenses are related but distinct, and fixing one does not fix the others.

## Canonical sources

- [RFC 5322: Internet Message Format (folding, FWS, line limits)](https://www.rfc-editor.org/rfc/rfc5322.html)
- [RFC 2047: MIME Part Three (encoded-words)](https://www.rfc-editor.org/rfc/rfc2047.html)
- [RFC 5321: Simple Mail Transfer Protocol (line termination, transport boundaries)](https://www.rfc-editor.org/rfc/rfc5321.html)
- [RFC 2231: MIME Parameter Value and Encoded Word Extensions](https://www.rfc-editor.org/rfc/rfc2231.html)
- [M3AAWG best practices and published documents](https://www.m3aawg.org/published-documents/)
