# GitHub environment deployment branch and tag policy

**Issue:** GitHub environments can restrict deployments to selected branches or tags, but similarly named branches/tags and unprotected rules can route an unintended ref toward privileged environment secrets.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Choose protected-branch or selected-pattern policy explicitly; keep release tag and branch naming disjoint; require reviewers; verify the deployed SHA/ref after approval; deny environment secrets to PR and untrusted reusable callers.

## Tests

Try matching/nonmatching branch and tag names, slash patterns, deleted/recreated tags, unprotected branch, fork PR, reviewer bypass, and rerun after ref movement.

## Gotchas

A branch and tag with the same name can create ambiguity, and environment admission does not validate artifact provenance or runner cleanliness.

## Official sources

- https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
