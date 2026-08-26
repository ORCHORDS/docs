# Null MX handling for domains that accept no mail

**Issue:** A domain intentionally publishes that it accepts no email, but a sender falls back to its A or AAAA record, repeatedly queues delivery, or interprets the record as an incomplete MX configuration. The result is pointless connection traffic and delayed non-delivery reports.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

RFC 7505 defines a null MX: a single MX record with preference 0 and exchange name ".". It states that the domain accepts no email. This is different from publishing no MX record, where SMTP's implicit-MX fallback can still direct delivery to the address record.

Publish null MX only for a domain that is not supposed to receive mail. A domain used in visible From addresses, return paths, automated replies, abuse handling, password recovery, or customer support needs a deliberate receiving design instead.

## Sender controls

1. Resolve the complete MX RRset using a validating, bounded DNS path.
2. Recognize null MX only when the RRset contains exactly the RFC-defined record. Do not treat an arbitrary root-like name, empty string, preference alone, or a null MX mixed with ordinary MX records as the signal.
3. When a valid null MX is found, do not fall back to A or AAAA and do not open an SMTP connection. Fail the delivery as a permanent address-domain failure using the applicable SMTP enhanced status behavior.
4. Preserve the distinction between NXDOMAIN, NODATA/no MX, SERVFAIL, timeout, DNSSEC validation failure, and null MX. Only the last is an affirmative no-mail declaration.
5. Cache the DNS answer only within DNS TTL and negative-caching rules. Re-resolve after expiry rather than turning a temporary observation into account state.
6. Generate one bounded, privacy-safe delivery diagnostic. Avoid repeated retries, connection probes, and noisy alerts for an intentional policy.
7. If accepting SMTP on behalf of another sender, use the 556 reply and enhanced status 5.1.10 where RFC 7505 makes that response applicable.

## Publisher controls

Publish exactly MX 0 . at the no-mail domain and remove all other MX records there. Verify that DNS tooling preserves the root label and does not rewrite it as an empty hostname or the zone apex. Review subdomains independently; a null MX at one owner name does not automatically define every delegated or explicitly configured subdomain.

Document the product consequences before rollout. A domain that cannot receive bounces or replies can undermine sender reputation and user recovery even if outbound mail technically succeeds.

## Verification

Test an exact null MX RRset, no MX with A/AAAA fallback, ordinary MX, mixed null and ordinary MX, multiple null records, CNAME/DNAME traversal, DNSSEC bogus answers, NXDOMAIN, SERVFAIL, stale resolver cache, and TTL-based policy change.

Confirm the sender creates no TCP attempt for a valid null MX, produces a permanent delivery result once, and resumes ordinary routing after the DNS declaration is removed and caches expire.

## Gotchas

- Preference zero alone does not make a null MX; the exchange must be the root label.
- Null MX is an explicit policy, not a shortcut for a temporarily offline mail server.
- A wildcard or parent-zone assumption can conceal separately configured child names.
- Removing MX records is not equivalent because implicit-MX fallback can apply.

## Official sources

- [RFC 7505 — A Null MX Resource Record for Domains That Accept No Mail](https://www.rfc-editor.org/rfc/rfc7505.html)
- [RFC 5321 — Simple Mail Transfer Protocol](https://www.rfc-editor.org/rfc/rfc5321.html)
