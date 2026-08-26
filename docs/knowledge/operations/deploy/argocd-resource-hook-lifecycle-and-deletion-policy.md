# Argo CD resource-hook lifecycle and deletion policy

**Issue:** Deployment hooks can run twice, never run during selective sync, retain sensitive Jobs, or leave an application OutOfSync when their identity and deletion lifecycle are not explicit.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin the Argo CD version and choose the documented phase deliberately: `PreSync`, `Sync`, `PostSync`, `SyncFail`, or the supported delete phase for that version.
- Make every hook idempotent and least-privileged. A retried schema migration, cleanup, or notification must be safe after partial completion.
- Use `generateName` for a new execution object, or a stable name with `BeforeHookCreation` when replacement is intended. Set `HookSucceeded` and/or `HookFailed` retention from evidence and incident needs.
- Do not rely on hooks during selective sync; block selective production sync when a mandatory hook would be skipped.
- Prefer Argo CD hook deletion policy over an uncoordinated Job TTL when deleting the Job would make desired and live state appear different.

## Verification

Test first sync, normal resync, failed hook, controller restart, concurrent sync request, selective sync, application deletion, and retry after a partially completed side effect. Assert phase ordering, exit status, cleanup, logs, and application health/Sync state.

## Gotchas

- A named hook is not automatically a fresh execution on every sync.
- Hook cleanup can remove forensic evidence; export bounded logs before deletion.
- Helm hooks are translated with Argo CD semantics, which are not identical to Helm release events.

## Official source

- [Argo CD resource hooks](https://argo-cd.readthedocs.io/en/stable/user-guide/resource_hooks/)
- [Argo CD Helm hook mapping](https://argo-cd.readthedocs.io/en/latest/user-guide/helm/#helm-hooks)
