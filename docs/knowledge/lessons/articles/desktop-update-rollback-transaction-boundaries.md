# Desktop update and rollback are separate transactions

**Issue**

A desktop updater that can download and install a new build is not automatically capable of safe rollback. Application binaries, user data, helper services, and update metadata can advance on different schedules.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Separate download verification, staged installation, first-launch health, and promotion into explicit states.
- Sign update metadata and packages; pin the expected publisher identity and reject downgrade unless a reviewed rollback manifest permits it.
- Keep user-data migrations backward-readable until the new version passes its health window, or take a recoverable versioned backup.
- Record the last known-good version outside the directory replaced by the updater.
- Make helper/service version compatibility bidirectional during the rollout window.

## Verification

1. Interrupt download, install, first launch, migration, and restart independently.
2. Install a bad-but-validly-signed build and prove the health gate restores the last known-good binary without corrupting data.
3. Test offline startup after staging and after rollback on every packaging target.

## Gotchas

- Electron's autoUpdater behavior and events vary by platform/provider.
- Code rollback cannot undo an irreversible schema migration.
- OS package managers may own rollback and repair semantics.

## Official sources

- [Electron autoUpdater](https://www.electronjs.org/docs/latest/api/auto-updater)
- [Tauri updater plugin](https://v2.tauri.app/plugin/updater/)
