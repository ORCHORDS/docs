# Git worktree-specific configuration boundaries

**Issue:** Repository configuration is shared by default, so changing sparse-checkout, worktree paths, or other checkout-specific settings in one linked worktree can unexpectedly affect its siblings.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Enable `extensions.worktreeConfig` only after confirming every Git client that opens the repository supports it. Move `core.worktree` and applicable `core.bare` values out of the common configuration as required, then set checkout-local values with `git config --worktree`. Resolve the file with `git rev-parse --git-path config.worktree`; never assume the administrative layout. Keep identity, remotes, and policy settings common unless isolation is intentional.

## Verification

From every linked tree, use `git config --show-origin --get-regexp` to confirm the winning source. Change a harmless worktree-local sentinel and prove siblings retain their values. Test the oldest supported Git client before rollout and validate sparse-checkout behavior independently in each tree.

## Gotchas

Older Git versions refuse repositories using this extension. Worktree-local overrides can hide common policy drift, and incorrectly leaving `core.worktree` in common config can point multiple checkouts at the wrong directory.

## Official sources

- https://git-scm.com/docs/git-worktree
- https://git-scm.com/docs/git-config
