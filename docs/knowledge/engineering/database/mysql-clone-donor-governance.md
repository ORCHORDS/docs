# MySQL Clone donor governance

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Remote cloning can replace instance data and transfer credentials or incompatible state unless donor selection and recovery are controlled.

## When to use

Use for controlled MySQL provisioning or recovery from an approved donor.

## Controls

Pin compatible donor versions, restrict clone privileges, encrypt transport, validate capacity, and preserve independent backups.

## Implementation

Configure an allowlisted donor, verify plugin and version compatibility, snapshot configuration, clone into an isolated target, then validate identity and replication before promotion.

## Tests

Test rejected donors, version mismatch, interrupted transfer, low disk, credential revocation, restart, and post-clone replication.

## Gotchas

Clone is destructive to target data; copied configuration and secrets require separate review.

## Official sources

- [Official documentation](https://dev.mysql.com/doc/refman/8.4/en/clone-plugin-remote.html)
