---
title: "NIST SSDF — Protect the Software"
owner: "Governance Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# NIST SSDF — Protect the Software

## Purpose

Provide public governance guidance for the **Protect the Software (PS)** practice group in NIST SP 800-218 SSDF Version 1.1.

## Baseline

Protect the Software focuses on safeguarding software source code, executables, configuration, and other software artifacts against unauthorized access and tampering throughout development and distribution.

## Governance guidance

- restrict access to source code and build-related artifacts according to role and need;
- protect source repositories, build environments, signing material, and release artifacts from unauthorized modification;
- preserve artifact integrity and provenance through controlled build and release processes;
- securely archive or retain software releases and supporting evidence where required;
- protect credentials and other sensitive material used by development and delivery systems;
- define and monitor exceptions to software-protection requirements.

## Verification

Confirm that access controls, integrity controls, artifact handling, and release protections are operating as designed and that sensitive development material is not exposed through repositories, build output, or distribution channels.

## Sources

- NIST SP 800-218, **Secure Software Development Framework (SSDF) Version 1.1**: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SSDF project: https://csrc.nist.gov/projects/ssdf
