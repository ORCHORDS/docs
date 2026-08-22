---
title: "API Security Policy"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# API Security Policy

## Purpose

Define security expectations for machine-accessible interfaces without publishing private endpoint inventories.

## Requirements

APIs SHOULD apply authentication and authorization appropriate to resource sensitivity, validate untrusted input, constrain resource use, avoid excessive data exposure, handle errors safely, and provide security-relevant observability.

Authorization must be enforced server-side or at the authoritative control point rather than relying on user-interface restrictions.

## Credentials and tokens

Tokens, keys, and service credentials must follow identity and secrets-management policies. Long-lived broad-scope credentials should be avoided where safer alternatives exist.

## Compatibility

Security fixes may require version or behavior changes. Deprecation and migration must not preserve known unsafe behavior indefinitely.

## Testing

Use risk-appropriate abuse-case and application-security verification, informed by [Security Testing Policy](../security/SECURITY_TESTING_POLICY.md).
