---
title: "Automated Updates of DNS Security (DNSSEC) Trust Anchors: Engineering and Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Automated DNSSEC Trust-Anchor Updates

## Normative protocol requirements

A new SEP key learned from an RRset validated by an existing anchor enters AddPend and requires continuous observation for the normally 30-day add hold-down before Valid; absence resets pending acceptance. REVOKE is accepted only through a valid RRset and the key’s self-signature. The REVOKE bit changes the DNSKEY RDATA and key tag, so implementations must identify the same key by a fingerprint over the key material rather than relying on the key tag. Persist states and timers safely across restart and clock rollback.

## Validation and interoperability

Simulate introduction, disappearance, hold-down, active signing, revoke, and removal. Test forged revoke, untrusted-only signatures, changed key tag with stable key fingerprint, downtime, snapshot rollback, and corrupt state. Initial bootstrap and recovery require separately authenticated operator action.

## Meaningful failure handling

Do not promote AddPend after lost observation or hold-down state, and do not honor REVOKE without validation by current anchors plus the key self-signature. Persist the key fingerprint, state transitions, timestamps, and validated RRsets; require authenticated recovery after corrupt or rolled-back state.

## Canonical sources

- [RFC 5011](https://www.rfc-editor.org/rfc/rfc5011)
