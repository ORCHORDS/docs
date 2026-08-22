---
title: "Security Baseline Configuration"
owner: "Security Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Security Baseline Configuration

## Purpose

Define how secure configuration baselines are selected, maintained, and
verified without exposing private configuration values.

## Requirements

Material technology classes SHOULD have documented baseline expectations for:

- unnecessary services and features;
- authentication and privileged access;
- logging and time synchronization;
- encryption and protocol settings;
- patching and supported versions;
- network exposure;
- administrative interfaces;
- default accounts and credentials;
- backup and recovery configuration where relevant.

## Baseline sources

Baseline requirements may draw from vendor hardening guidance, CIS Benchmarks,
NIST guidance, and threat-informed internal experience. Sources must be
versioned where practical.

## Exceptions

A deviation from a required baseline must have an owner, rationale,
compensating controls when necessary, and review or expiry date.

## Verification

Baselines should be assessed after material change and periodically according
to risk. Configuration drift is a control failure even when the original build
was compliant with the baseline.
