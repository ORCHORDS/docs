---
title: "Code Signing Policy"
owner: "Release Manager and Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "180 days"
next-review: "2027-02-18"
---

# Code Signing Policy

## Purpose

Use code signing where it provides meaningful assurance of publisher identity
and artifact integrity.

## Requirements

When signing is used:

- signing credentials must be access-controlled and protected;
- private signing material must not be stored in source repositories;
- signing access should be limited to release automation or authorized roles;
- signatures should bind to the exact released artifact;
- certificate/key expiry and revocation capability must be monitored;
- compromise or suspected compromise triggers incident response and
  revocation/rotation assessment.

## Preferred design

Prefer signing mechanisms that keep private key material in protected hardware
or managed signing services and use short-lived workload identity where
available.

## Evidence

Release evidence should identify the artifact digest, signature method,
signing identity, source revision, and verification method when appropriate.
