# SMTP LIMITS extension session and transaction bounds

**Issue:** A sending system discovers a server's message-size limit but still starts transactions that exceed the server's recipient, domain, or MAIL-command limits. It then treats a LIMITS advertisement as permanent configuration, or assumes every server supports the extension, causing avoidable mid-transaction failures and unsafe retry behavior.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

RFC 9422 defines the SMTP LIMITS extension for servers to advertise selected operational limits in EHLO or LHLO responses. It complements, rather than replaces, the SIZE extension: message octet accounting remains a separate contract.

Use LIMITS when a sender can cheaply reshape work before issuing MAIL or RCPT commands. It is especially useful for batched delivery, mailing-list expansion, and relays that otherwise learn bounds only after consuming transaction state.

## Controls and implementation

1. Parse LIMITS only after a successful EHLO or LHLO response and only according to the registered extension syntax. Ignore unknown limit names while preserving strict numeric parsing for known names.
2. Treat MAILMAX as the maximum number of MAIL commands permitted in the current session, RCPTMAX as the maximum recipients in one transaction, and RCPTDOMAINMAX as the maximum distinct recipient domains in one transaction.
3. Plan each envelope below every advertised applicable bound. Count envelope recipients and distinct recipient domains, not visible To or Cc headers.
4. Keep SIZE handling independent. A transaction that satisfies LIMITS can still exceed the advertised message size, and the inverse is also true.
5. Scope advertisements to the current SMTP session. Do not persist them as an enduring property of a hostname, MX, tenant, or provider; policy can differ by connection and change after reconnect.
6. When LIMITS is absent, use ordinary SMTP reply handling. Do not invent defaults or interpret absence as unlimited capacity.
7. If a server rejects a command despite a compliant plan, honor the returned enhanced status and retry semantics. Never restart an accepted transaction from an ambiguous point without first resetting or opening a new session.
8. Bound local parsing and arithmetic. Reject negative, fractional, overflowing, duplicated-conflicting, or otherwise malformed values instead of letting them influence batching.

## Verification

Test extension absent, one and multiple registered limits, unknown future names, malformed and overflowing values, mixed-case EHLO text, SMTP and LMTP, reconnect with changed limits, and servers that enforce a smaller contextual policy during the transaction. Exercise exact-bound and bound-plus-one cases.

Assert that batching preserves every original envelope recipient exactly once, keeps domain counting case-insensitive after domain normalization, and never splits a single atomic business operation in a way that changes its semantics.

## Gotchas

- LIMITS is capability negotiation, not a reservation or delivery guarantee.
- RCPTMAX limits an SMTP transaction, not a message header or mailing-list membership.
- A server can advertise only the limits it supports; clients must tolerate partial advertisements.
- Connection pools must not share one session's advertised values with another session.

## Official sources

- [RFC 9422 — SMTP Service Extension for Server Limits](https://www.rfc-editor.org/rfc/rfc9422.html)
- [RFC 1870 — SMTP Service Extension for Message Size Declaration](https://www.rfc-editor.org/rfc/rfc1870.html)
