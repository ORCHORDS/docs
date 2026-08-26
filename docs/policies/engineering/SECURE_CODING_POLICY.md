---
title: "Secure Coding Policy"
owner: "Engineering Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Secure Coding Policy

## Purpose

Set company-wide secure coding expectations independent of programming language
or framework.

## Requirements

Engineering changes MUST consider:

- untrusted input validation and output encoding;
- authorization at the point of sensitive action;
- safe error handling without sensitive disclosure;
- secure defaults;
- safe use of cryptography through established libraries;
- resource and concurrency bounds;
- file/path, serialization, and command-execution risks;
- sensitive data minimization in logs and telemetry;
- dependency trust and updateability.

Custom security primitives SHOULD be avoided when mature, reviewed
implementations exist.

## High-risk code

Authentication, authorization, cryptography, secrets, deserialization,
financial logic, file upload, privileged execution, and security-boundary code
require stronger review and testing.

## References

Use [Engineering Standards](ENGINEERING_STANDARDS.md),
[Secure Design and Threat Modeling](SECURE_DESIGN_THREAT_MODELING.md), and
the verification references in [Standards](../standards/README.md).
