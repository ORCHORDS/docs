---
title: "Secrets Management"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Secrets Management

## Purpose

Protect credentials, tokens, private keys, signing material, recovery secrets,
and other authentication material throughout their lifecycle.

## Requirements

Secrets MUST:

- be stored only in approved secret-handling mechanisms;
- be unavailable to unauthorized users and logs;
- have a named owner or owning service;
- be scoped to the minimum required permissions;
- be rotated or revoked when compromise is suspected;
- be removed when no longer required.

Secrets must not be committed to source repositories, documentation, tickets,
chat transcripts, build artifacts, or test fixtures unless the value is
explicitly fictitious and cannot authenticate.

## Exposure response

Suspected exposure requires immediate containment assessment. Where a value may
still be usable, rotate or revoke it as soon as safely practical and preserve
enough evidence to determine scope.

See [Secrets Rotation SOP](../sop/SECRETS_ROTATION_SOP.md).
