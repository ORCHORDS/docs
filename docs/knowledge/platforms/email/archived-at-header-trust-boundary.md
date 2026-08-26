# Archived-At header trust boundary

**Issue:** The RFC 5064 `Archived-At` field can link a message to an archive URI, but it is sender-supplied metadata. Automatically fetching it leaks recipient activity, enables phishing, and may expose a different message than the one received.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation
Parse the field under normal header-size/count limits and retain multiple values without fetching. Display the normalized HTTPS origin and require user action. Apply URL, redirect, DNS-rebinding, private-network, and download controls; open externally or in an isolated origin. Bind archive links to the message fingerprint for audit, but never treat the remote representation as authenticated content.

## Verification
Test malformed/folded/multiple fields, non-HTTPS schemes, credentials, IDNs, redirects, private IPs, changed archive content, offline use, and DKIM pass/fail.

## Gotchas
DKIM can authenticate the header's signer, not future bytes at the URI. Archive access may require credentials and reveal mailbox membership.

## Sources
- RFC Editor, [RFC 5064 — Archived-At Message Header Field](https://www.rfc-editor.org/rfc/rfc5064.html)
- IETF, [URI security considerations](https://www.rfc-editor.org/rfc/rfc3986.html#section-7)
