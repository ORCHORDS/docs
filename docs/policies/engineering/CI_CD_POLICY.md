---
title: "CI/CD Policy"
owner: "Engineering and Security Leads"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# CI/CD Policy

## Purpose

Reduce delivery risk and software-supply-chain exposure in automated build,
test, and deployment workflows.

## Least privilege

- Workflow tokens MUST have only the permissions required by the job.
- Read-only should be the default where practical.
- Write, deployment, identity-token, and secret access should be granted only
  to the specific job that needs them.
- Long-lived credentials SHOULD be replaced with short-lived federated
  credentials where the target platform supports them.

## Third-party automation

- Third-party actions or reusable automation SHOULD be pinned to immutable
  revisions.
- For GitHub Actions, a full-length commit SHA is the preferred immutable
  reference according to GitHub's secure-use guidance.
- The source and publisher of privileged automation should be reviewed.
- Dependency-update automation should keep pinned revisions current.

## Untrusted input

Privileged workflows MUST NOT execute untrusted pull-request code with secrets
or write credentials. Workflow triggers that run in a privileged context must
be designed so untrusted content cannot influence executed commands, checked
out code, artifacts, paths, or scripts.

## Pipeline gates

Risk-appropriate pipelines should include:

- formatting or linting;
- tests;
- build/packaging validation;
- dependency and vulnerability checks;
- secret detection;
- security analysis appropriate to the language and application;
- documentation quality checks when documentation changes.

A check is described as a **gate** only when the platform actually blocks the
change on failure.

## Artifacts

Release artifacts should be traceable to source revision and build process.
Higher-assurance releases should add provenance, integrity verification, and
SBOM evidence where useful.

## Evidence

Retain enough build and release evidence to answer:

- what source revision was used;
- which checks ran and their result;
- what artifact was produced;
- who approved promotion;
- when and where promotion occurred;
- how to verify integrity.
