# ARC Chain Validation and Trust Boundaries

**Issue:** Forwarders and mailing lists can break SPF/DKIM alignment, but a cryptographically valid Authenticated Received Chain does not prove that its sealers or message content are trustworthy.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use an RFC 8617 implementation to validate the ordered ARC sets: exactly one ARC-Authentication-Results, ARC-Message-Signature, and ARC-Seal per instance; continuous instance numbers; valid signatures; and correct chain-validation values. Treat `fail` the same as no usable ARC chain for authentication purposes.

Apply ARC evidence only through a local trust policy for known intermediaries. Combine it with current SPF, DKIM, DMARC, reputation, malware, phishing, and content checks. A passing chain can explain an authentication change; it must not independently override a reject decision.

Sealers should authenticate on receipt, finish their modifications, then add one complete ARC set. Protect signing keys like DKIM keys, rotate selectors, and monitor DNS/signing errors. Bound header size, chain length, validation CPU, and DNS work.

## Verification

Replay direct mail, trusted forwarding, mailing-list modification, unknown/malicious sealer, missing/gapped/duplicate instances, altered body/header, expired DNS key, chain over 50 sets, and slow DNS. Confirm invalid chains fail closed without causing queue exhaustion and trusted ARC improves only the intended indirect flow.

## Gotchas

ARC is experimental and explicitly not a trust framework. It can expose handler domains and IP-related evidence. Long chains increase header size and DNS queries, creating denial-of-service concerns.

## Sources

- [RFC 8617: Authenticated Received Chain](https://www.rfc-editor.org/rfc/rfc8617.html)
- [RFC 8601: Authentication-Results](https://www.rfc-editor.org/rfc/rfc8601.html)
- [RFC 7489: DMARC](https://www.rfc-editor.org/rfc/rfc7489.html)
