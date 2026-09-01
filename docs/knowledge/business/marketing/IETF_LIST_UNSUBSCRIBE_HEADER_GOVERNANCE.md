# IETF List-Unsubscribe Header Governance

## Scope

This control governs the technical implementation, validation, and monitoring of List-Unsubscribe and List-Unsubscribe-Post headers for bulk, list, and marketing email. It focuses on protocol depth: header syntax, URI ordering, one-click signaling, HTTPS POST behavior, token design, authentication interaction, receiver behavior assumptions, bounce-safe processing, and evidence that the deployed message stream conforms to the intended implementation. It does not focus on general unsubscribe policy, marketing preference strategy, or statutory opt-out deadlines.

The core protocol sources are [RFC 2369: The Use of URLs as Meta-Syntax for Core Mail List Commands and their Transport through Message Header Fields](https://www.rfc-editor.org/rfc/rfc2369) and [RFC 8058: Signaling One-Click Functionality for List Email Headers](https://www.rfc-editor.org/rfc/rfc8058). Additional IETF context and document metadata are available through [IETF Datatracker: RFC 8058](https://datatracker.ietf.org/doc/html/rfc8058). These are the canonical primary sources for the fields discussed here.

## Requirements Versus Recommendations

Internal requirements are mandatory for message streams where the organization claims one-click List-Unsubscribe support. A message must include a syntactically valid `List-Unsubscribe` field with an HTTPS URI suitable for automated processing, and it must include `List-Unsubscribe-Post: List-Unsubscribe=One-Click` when one-click POST semantics are intended. The HTTPS endpoint must accept the POST request without requiring the user to log in, render a page, solve a challenge, or manually confirm. The token must identify the subscription or recipient-list relationship without exposing raw email addresses or accepting unauthenticated arbitrary address removal.

Recommendations include also including a `mailto:` URI as a secondary unsubscribe path, aligning visible footer unsubscribe links with the same subscription model, DKIM-signing the List-Unsubscribe fields where feasible, monitoring receiver-generated POSTs separately from human browser traffic, and returning stable success responses even when the subscription was already removed. These recommendations improve interoperability and operational resilience, but implementers should distinguish them from requirements in RFC language.

## Workflow

The workflow begins with message-stream classification. Transactional, security, legal notice, support, marketing, newsletter, product update, and community-list streams should not be configured identically by accident. Only streams that are intended to expose unsubscribe controls should receive these headers. For each eligible stream, record the list identifier, subscription table, recipient key, sending domain, DKIM domain, envelope sender, visible From domain, and unsubscribe endpoint.

Header construction must be deterministic. The `List-Unsubscribe` field contains one or more angle-bracketed URLs. RFC 2369 defines list command fields that use URLs as structured command locations. For one-click behavior under RFC 8058, the field must contain an HTTPS URI that the receiver can POST to. If multiple URLs are supplied, the implementation should place the HTTPS one-click endpoint first for receivers that select the first usable HTTPS URI. A `mailto:` fallback may be included after the HTTPS URI, but it should not be the only URI for one-click semantics.

The `List-Unsubscribe-Post` field signals that the HTTPS URI supports one-click. For the standard one-click unsubscribe case, the field value is `List-Unsubscribe=One-Click`. Receivers performing the action send an HTTPS POST to the HTTPS URI. The sender endpoint should process the request as an unsubscribe for the encoded subscription token. It should not depend on cookies, browser sessions, JavaScript, CSRF tokens designed for browser forms, or query parameters that can be modified into another user’s subscription without cryptographic protection.

Token design is a core protocol-control issue. The URL should contain an opaque, high-entropy token or signed payload that maps to a subscription, list, tenant, and recipient. Avoid placing the raw email address in the URL. Avoid using only base64 encoding, sequential IDs, or reversible identifiers without integrity protection. Token claims should have enough data to resolve the subscription and enough versioning to support rotation, but they should not disclose sensitive profile data.

Endpoint behavior should be idempotent. A repeated POST for the same token should return a success-class response if the subscription is already unsubscribed. Unknown, expired, or malformed tokens should not reveal whether an address exists. The endpoint should record event type, token version, list ID if resolvable, message stream, request timestamp, source IP, user agent, result, and failure reason category. It should not require a GET request to cause the unsubscribe; accidental URL fetching is the problem RFC 8058 was designed to avoid.

## Concrete Fields And Controls

Minimum message fields are: `List-Unsubscribe`, `List-Unsubscribe-Post` for one-click streams, `List-ID` where the list architecture uses it, `From`, `Sender` if used, `Return-Path` as observed after delivery, `DKIM-Signature`, and message ID. Minimum governance fields are stream ID, list ID, sending domain, DKIM selector, endpoint URL template, token algorithm, token lifetime, recipient mapping table, suppression action, retry policy, monitoring owner, and deployment date.

Controls include header serialization tests, DKIM coverage review, token integrity validation, endpoint method enforcement, POST body validation, idempotency, privacy-preserving logs, rate limiting, alerting, and receiver compatibility sampling. Header serialization tests should inspect raw RFC 5322 message output, not merely application object state. Line folding must preserve field semantics. URLs must remain inside angle brackets and must not be broken by template escaping or tracking-link rewriting.

DKIM review should confirm whether the unsubscribe headers are signed and whether downstream mail infrastructure modifies them after signing. Signing these headers can help receivers trust that unsubscribe commands are tied to the sending domain, but operational mail paths vary. If a relay rewrites headers, either fix the signing point or document the residual risk.

Endpoint controls should accept only POST for one-click processing. A GET request may return a neutral page or no-op response, but it should not unsubscribe a user. POST body handling should recognize the RFC 8058 one-click form value and reject unrelated state-changing commands. Do not require cookies because automated receiver requests typically will not carry a user session.

## Validation Evidence And Tests

Evidence should include raw message samples from each stream, header parser output, DKIM verification output, endpoint integration tests, token validation tests, live receiver tests where available, and unsubscribe event logs. Store complete headers for test messages because rendered email clients often hide the relevant fields.

Tests should include syntax parsing, one-click POST, GET no-op, repeated POST idempotency, malformed token, expired token, wrong-list token, already-unsubscribed recipient, DKIM preservation, and tracking rewrite detection. A syntax test should feed the raw message to an email parser and assert that `List-Unsubscribe` contains the expected HTTPS URI and optional fallback URI. A POST test should submit the exact body `List-Unsubscribe=One-Click` to the HTTPS URI and verify that the subscription state changes once. A GET test should fetch the URL and verify no state change occurs.

Receiver simulation should avoid browser assumptions. Use an HTTP client without cookies, without JavaScript, and without prior authentication. The test should follow the behavior expected from a mail receiver acting on a user’s unsubscribe command. Preserve HTTP status, response body class, and subscription database result.

Deliverability validation should sample messages after the final sending infrastructure, not only before injection. Some ESPs, MTAs, or security appliances rewrite links, fold headers, remove duplicate list headers, or alter signing. Governance evidence should show the final delivered header state for major mailbox providers or seed accounts when possible.

## Failures And Corrections

Common failures include missing angle brackets, HTTPS URL rewritten through click tracking, `List-Unsubscribe-Post` present without a usable HTTPS URI, one-click endpoint requiring login, GET requests unsubscribing users, tokens exposing raw addresses, non-idempotent POST handling, DKIM signatures broken after header insertion, and shared tokens removing the wrong subscription. Each failure should create a correction record with stream ID, sample message ID, raw headers, endpoint logs, root cause, fix, retest, and deployment version.

If tracking rewrite breaks the HTTPS endpoint, exclude List-Unsubscribe URLs from click tracking and retest final delivered headers. If GET causes state change, change the endpoint so only POST with the one-click body performs removal, then test scanner-style GETs. If tokens are guessable or expose personal data, rotate token format, invalidate vulnerable tokens where feasible, and monitor for abnormal unsubscribe volume. If headers are inserted before DKIM signing but later modified, move insertion closer to final signing or adjust signing infrastructure.

## Limitations

This control is not a CAN-SPAM, GDPR, ePrivacy, CASL, or platform-policy compliance procedure. It does not decide which messages must include unsubscribe mechanisms or how quickly legal opt-out requests must be honored. It also does not guarantee mailbox-provider UI treatment, because receivers decide whether and how to surface unsubscribe controls.

Protocol conformance is necessary but not sufficient for trustworthy unsubscribe handling. The implementation must be tested from generated message through delivered header and endpoint side effect. Assertions should be limited to what evidence proves: syntactic header presence, RFC 8058 one-click behavior, endpoint idempotency, token safety, and observed receiver compatibility.

## Canonical sources

- **Primary authority 1 — RFC 2369: The Use of URLs as Meta-Syntax for Core Mail List Commands and their Transport through Message Header Fields:** [https://www.rfc-editor.org/rfc/rfc2369](https://www.rfc-editor.org/rfc/rfc2369)
- **Primary authority 2 — RFC 8058: Signaling One-Click Functionality for List Email Headers:** [https://www.rfc-editor.org/rfc/rfc8058](https://www.rfc-editor.org/rfc/rfc8058)
- **Primary authority 3 — IETF Datatracker: RFC 8058:** [https://datatracker.ietf.org/doc/html/rfc8058](https://datatracker.ietf.org/doc/html/rfc8058)
