---
title: "Cryptography and Key Management"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "180 days"
next-review: "2027-02-18"
---

# Cryptography and Key Management

## Purpose

Define high-level governance for encryption, signing keys, credentials, and
cryptographic material without publishing operational key locations or
topology.

## Principles

- Use well-established, currently acceptable cryptographic algorithms and
  protocols appropriate to the risk.
- Do not design proprietary cryptography for security-sensitive purposes.
- Keys and credentials are scoped to the minimum necessary privilege and
  environment.
- Private keys and secrets are not committed to source or public documents.
- Key generation, storage, use, rotation, backup, revocation, and destruction
  are controlled according to sensitivity.
- Compromise or suspected exposure triggers containment and replacement where
  technically applicable.
- Signing keys receive stronger protection because compromise can affect
  software or document trust.

## Lifecycle controls

A governed key lifecycle defines owner, purpose, authorized use, access model,
rotation/replacement condition, recovery approach where justified, and
revocation/destruction process.

## Algorithm agility

Systems should support replacement of algorithms, certificates, or keys without
unnecessary redesign. Deprecation by authoritative standards or credible
cryptanalytic developments triggers review.

## Public boundary

This document intentionally does not publish real key identifiers, locations,
providers, recovery methods, access membership, or rotation schedules.
