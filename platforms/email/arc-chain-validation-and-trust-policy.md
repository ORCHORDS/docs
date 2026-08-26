# ARC Chain Validation and Trust Policy

**Issue:** A syntactically valid Authenticated Received Chain (ARC) can preserve authentication results through forwarders, but it does not prove that the message or sealer is trustworthy. Treating `arc=pass` as an allow decision can turn a compromised or careless intermediary into an authentication bypass.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Parse ARC as ordered sets. Every instance must contain exactly one ARC-Authentication-Results, ARC-Message-Signature, and ARC-Seal field, with contiguous instance numbers.
- Enforce the RFC limit of 50 ARC sets before doing signature or DNS work.
- Run the complete chain-validation algorithm and record `none`, `pass`, or `fail`. Handle a failed chain like no ARC chain, never like authenticated mail.
- Separate cryptographic validity from organizational trust. Maintain an explicit, reviewed allowlist or reputation policy for sealing domains; default an unknown sealer to no authentication override.
- Use preserved results only as one input to disposition. Continue content, reputation, DMARC, malware, and abuse checks.
- Cache DNS results within their TTL and cap validation work to resist DNS amplification and header-size resource exhaustion.
- Retain the local validation result, trusted sealer identity, chain length, and reason for any DMARC override in structured audit data.

## Verification

1. Test no chain, a valid one-set chain, a valid forwarded multi-set chain, missing and duplicate fields, gaps in instance numbering, a bad signature, and more than 50 sets.
2. Confirm an untrusted `arc=pass` cannot independently change reject/quarantine to accept.
3. Confirm a trusted sealer policy is scoped and reversible and that every override emits an auditable reason.
4. Measure DNS queries and validation latency for long and adversarial chains.

## Gotchas

- ARC is an Experimental RFC and adoption cannot be assumed.
- A valid seal attributes an assertion to a domain; it does not establish message safety.
- Header growth can exceed limits in older MTAs.
- Re-sealing a broken chain does not restore the lost chain of custody.

## Sources

- [RFC 8617 — The Authenticated Received Chain Protocol](https://www.rfc-editor.org/rfc/rfc8617.html)
