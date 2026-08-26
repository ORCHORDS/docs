# arc-authenticated-received-chain

**Issue:** Preserving authentication results through email forwarding using ARC headers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Legitimate forwarded email (mailing lists, email forwarding services) fails DMARC at the final destination because SPF breaks when the forwarder's IP is not in the original domain's SPF record.

## Pattern / Solution
ARC adds three headers at each hop that preserve and chain authentication results:

- `ARC-Authentication-Results` (AAR) — copy of the `Authentication-Results` header at that hop
- `ARC-Message-Signature` (AMS) — DKIM-like signature over the message at that hop
- `ARC-Seal` (AS) — signature over all ARC sets from previous hops

Example headers added by a forwarder:
```
ARC-Seal: i=1; a=rsa-sha256; cv=none; d=forwarder.example; s=arc-selector;
  b=<base64-signature>
ARC-Message-Signature: i=1; a=rsa-sha256; d=forwarder.example; s=arc-selector;
  h=from:to:subject:date; bh=<body-hash>; b=<signature>
ARC-Authentication-Results: i=1; mx.forwarder.example;
  dkim=pass header.i=@originaldomain.com; spf=pass smtp.mailfrom=originaldomain.com
```

Final receivers that trust the forwarder's ARC seal can use the preserved results to pass DMARC even when SPF fails.

Implementation: handled automatically by MTAs like Postfix (with milter), rspamd, and cloud providers (Google, Microsoft). Most senders do not need to implement ARC themselves; receiving MTAs process it.

## Gotchas
- ARC is a trust-based system; receivers maintain their own lists of trusted ARC sealers
- ARC does not make unauthenticated mail pass DMARC; it only preserves results from earlier hops
- `cv=none` on the first hop, `cv=pass` on subsequent hops if chain is intact, `cv=fail` if broken

## Related
- `dmarc-policy-setup.md`
- `email-forwarding-setup.md`
