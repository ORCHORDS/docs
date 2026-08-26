# Kubernetes pod-affinity label-key contract

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

matchLabelKeys and mismatchLabelKeys dynamically project incoming Pod labels into affinity selection; mutable or untrusted labels can change placement boundaries.

## When to use

Use for rollout-aware affinity or tenant separation when label ownership is strict.

## Controls

Use immutable controller-owned keys, explicit namespaces and selectors, admission validation, and topology capacity tests.

## Implementation

Define the smallest key list, render manifests, validate merged selector behavior, canary scheduling, and observe pending Pods before wider rollout.

## Tests

Test missing and mutated labels, old/new revisions, tenant collisions, topology loss, scheduler restart, and rollback.

## Gotchas

These fields complement rather than replace labelSelector; direct Pod label edits can produce surprising behavior.

## Official sources

- [Official documentation](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#matchlabelkeys)
