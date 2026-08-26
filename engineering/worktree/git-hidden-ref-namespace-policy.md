# Git hidden-reference namespace policy

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

hideRefs configuration can conceal refs from advertisement or transfer while they remain locally reachable, creating false assumptions about deletion or authorization.

## When to use

Use to keep administrative refs out of selected fetch, receive, upload-pack, or protocol views.

## Controls

Use a dedicated namespace, define service-specific rules, test negation order, and enforce authorization independently.

## Implementation

Inventory refs, add anchored hideRefs patterns in scoped configuration, trace advertisements from each protocol path, and document recovery access.

## Tests

Test fetch, push, protocol v2, negation, symbolic refs, namespace collisions, backups, and configuration rollback.

## Gotchas

Hidden refs still retain objects and are not a secrecy boundary against repository filesystem access.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-config#Documentation/git-config.txt-transferhideRefs)
