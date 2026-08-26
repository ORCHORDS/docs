# macOS SMAppService login item and agent lifecycle

**Issue:** A macOS app edits LaunchAgents directly, copies an unsigned helper into a user directory, or assumes registration means the helper is running. Updates leave duplicate background processes, user denial is invisible, and uninstall fails to remove the app-owned service cleanly.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

On macOS 13 and later, Service Management's SMAppService is the supported application-facing API for registering bundled login items, launch agents, and launch daemons represented by the API. Registration remains subject to platform policy and user control in Login Items settings.

Use it only for background behavior that is necessary, disclosed, and owned by the installed app. Prefer foreground launch or an explicit scheduled action when persistent background execution is not needed.

## Controls and implementation

1. Choose the correct service kind: main-app login item, bundled login item, launch agent, or launch daemon. Do not use elevated daemon machinery for per-user work.
2. Embed the executable and its property list in the documented application-bundle location. Keep bundle identifiers, executable names, team identity, and signing requirements consistent.
3. Treat register as an idempotent desired-state operation and handle its error. Query SMAppService status to distinguish enabled, requiring approval, not registered, and other documented states.
4. When approval is required or denied, explain the exact feature impact and provide a user-initiated route to the relevant System Settings pane. Do not nag, repeatedly relaunch settings, or claim the OS toggle is an app-owned preference.
5. Design process startup as replayable. Registration does not prove immediate launch, one instance, connectivity, or successful work; the service must acquire its own single-instance and job-idempotency controls.
6. Use a versioned IPC contract between app and helper. Validate caller identity where required, reject unknown messages, and avoid passing secrets through arguments or environment.
7. Unregister when the user disables the feature and before removing an app-owned service during a managed uninstall/update transition. Tolerate already-unregistered state.
8. Keep observability bounded: registration status, helper version, launch outcome, and sanitized error. Never collect the user's complete Login Items inventory.

## Verification

Test clean install, upgrade from a legacy helper, register twice, unregister twice, approval pending/accepted/denied, user toggling the OS setting, login/logout, reboot, helper crash, app moved, signature or identifier mismatch, multi-user machines, and uninstall.

Confirm one background instance performs each logical job, UI reflects current system status after returning from Settings, and an unsupported pre-macOS-13 path is explicit rather than silently invoking the new API.

## Gotchas

- Registered, approved, launched, and healthy are four different states.
- Editing launchd files outside the documented app lifecycle can conflict with user management and updates.
- A launch daemon has a much larger privilege and review surface than a user agent.
- Distribution and notarization requirements still apply to embedded helpers.

## Official sources

- [Apple — SMAppService](https://developer.apple.com/documentation/servicemanagement/smappservice)
- [Apple — Updating your app package installer to use the new Service Management API](https://developer.apple.com/documentation/servicemanagement/updating-your-app-package-installer-to-use-the-new-service-management-api)
