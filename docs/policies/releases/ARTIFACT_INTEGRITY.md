---
title: "Release Artifact Integrity"
owner: "Release Manager"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Release Artifact Integrity

## Purpose

Define integrity and provenance expectations for distributed software or other
release artifacts.

## Requirements

Material release artifacts SHOULD have controls that support:

- traceability to approved source and build inputs;
- integrity verification;
- controlled signing or attestation where appropriate;
- immutable or versioned publication;
- reproducible metadata sufficient to identify the release;
- retention of release evidence;
- revocation or withdrawal procedures for compromised releases.

## Supply chain

Artifact integrity should be considered with
[Software Supply Chain](../engineering/SOFTWARE_SUPPLY_CHAIN.md), not as a
standalone signing exercise.

## Claims

Signing proves control of a signing identity and artifact integrity under the
chosen mechanism; it does not prove that the software is vulnerability-free.
