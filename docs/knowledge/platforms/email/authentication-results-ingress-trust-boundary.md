# Authentication-Results ingress trust boundary

**Issue:** A mail pipeline parses every `Authentication-Results` header as authoritative. An external sender can prepend a convincing `dkim=pass` or `spf=pass` value and influence filtering or UI even though the local receiver never produced it.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Trust model

RFC 8601 standardizes the field syntax; it does not make the field self-authenticating. Trust comes from the administrative boundary that inserted it. The `authserv-id` identifies the authentication service, but a matching string is not proof that the service wrote the header.

At the first trusted ingress:

1. Remove, quarantine, or mark untrusted any existing `Authentication-Results` fields that could be mistaken for locally generated results.
2. Run authentication checks at the controlled receiver.
3. Add a new field with an `authserv-id` owned by that administrative domain.
4. Let downstream consumers accept results only from an explicit allowlist of trusted ingress services and header positions established by the mail topology.

If trusted intermediaries exist, document each hop and its allowed `authserv-id`. Do not turn “same company domain” into a wildcard trust rule.

## Parser and data controls

Parse the RFC grammar rather than splitting on semicolons. A field can contain multiple method results, comments, reason text, property types, and properties. Method and result tokens are extensible, so an unknown method must be retained or ignored safely—not coerced to failure or success.

Store at least:

- the trusted/untrusted decision and reason;
- `authserv-id`;
- method and result;
- property type/name/value where present;
- the receiving hop that accepted the field;
- the raw header for bounded diagnostics.

Normalize only where the specification permits. Keep `none` distinct from `neutral`, `temperror`, `permerror`, `fail`, and `pass`. A “pass” is scoped to its method and evaluated identity; it is not a general sender authorization.

## Consumer rules

Filtering and UI must query structured trusted results, never scan raw header text. Combine SPF, DKIM, DMARC, ARC, and other methods according to their own specifications. ARC can transport an upstream assessment, but it does not remove the local `Authentication-Results` trust decision.

Do not expose comments or property values as trusted HTML. Treat them as untrusted text even when the enclosing field came from a trusted MTA.

## Verification

Inject mail with forged leading and trailing fields, duplicated `authserv-id` values, folded lines, comments containing separators, unknown methods, malformed properties, and multiple trusted hops. Verify the boundary strips or labels external claims and that only the locally inserted result reaches policy decisions.

Log the producer hop and trust decision without logging full addresses unnecessarily. A useful invariant is: every result consumed by policy can be traced to one configured authentication service.

## Gotchas

- Header order alone is unsafe unless the receiving topology enforces it.
- `authserv-id` is an identifier, not a signature.
- Forwarding can legitimately change SPF outcomes; preserve evaluated identities.
- A parser failure should make the result unavailable, not silently convert it to `pass` or `fail`.

## Sources

- [RFC 8601 — Message Header Field for Indicating Message Authentication Status](https://www.rfc-editor.org/rfc/rfc8601.html)
