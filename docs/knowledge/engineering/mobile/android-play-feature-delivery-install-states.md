# Android Play Feature Delivery Install States

Play Feature Delivery splits an app into a base APK and dynamic feature modules installed on demand — the camera filters ship later, the AR module only for devices that ask. The engineering surface that makes or breaks the experience is install-state handling: your app requests a module, Play runs a multi-phase session (pending, downloading, installing, then requiring restart or merging), and each state demands UI and failure handling. Treat it as a state machine with platform-driven transitions and cancellation semantics, not a fire-and-forget download. This article covers the SplitInstallManager state model, on-demand and conditional delivery configuration, restart-versus-instant merges, and the operational failure modes.

## Scope

This article addresses Play Feature Delivery via the Play Core Library: `SplitInstallManager` (`startInstall`/`getSessionState`/`registerListener`/`cancelInstall`), `SplitInstallSessionState` statuses (`PENDING`, `DOWNLOADING`, `DOWNLOADED`, `INSTALLING`, `INSTALLED`, `REQUIRES_USER_CONFIRMATION`, `FAILED`, `CANCELING`, `CANCELED`), module configuration (`dist:on-demand`, `dist:instant`, conditional device-feature/ABI/country delivery), and deferred/instant component injection. It covers client-side state handling. It does not cover asset delivery (Play Asset Delivery), app bundles generally, or backend feature-flag systems.

## Workflow or implementation guidance

The mental model: a module install is a session with an ID, transitioning through states reported via listeners. Your app starts one, observes states, and reacts — with exactly two terminal patterns: modules that merge into the running process without restart (small code-only modules on supported conditions) and modules that require a process restart (`SplitInstallSessionStatus.INSTALLED` followed by app restart for the classloader to see the code; or `REQUIRES_USER_CONFIRMATION` for large downloads).

The flow in code shape:

```kotlin
val request = SplitInstallRequest.newBuilder()
    .addModule("camera_filters")
    .build()
splitInstallManager.startInstall(request)
    .addOnSuccessListener { sessionId -> /* track it */ }
    .addOnFailureListener { e -> /* SplitInstallException with errorCode */ }

val listener = SplitInstallStateUpdatedListener { state ->
    when (state.status()) {
        DOWNLOADING -> showProgress(state.bytesDownloaded(), state.totalBytesToDownload())
        REQUIRES_USER_CONFIRMATION -> splitInstallManager.startConfirmationDialogForResult(state, activity, RC)
        INSTALLING -> showIndeterminate("Finishing")
        INSTALLED -> routeToFeature()          // or schedule restart if classes needed
        FAILED -> handleError(state.errorCode())
    }
}
splitInstallManager.registerListener(listener)
```

State-handling decisions:

1. **Progress is only in DOWNLOADING.** `bytesDownloaded`/`totalBytesToDownload` populate during download; show MB-based progress there and indeterminate elsewhere. DOWNLOADED is a brief staging state before INSTALLING on most paths.
2. **`REQUIRES_USER_CONFIRMATION` is Play's consent wall** for large downloads (typically over 10 MB on metered conditions — Play prompts about download size). You must call `startConfirmationDialogForResult` and handle the Activity result: user decline delivers CANCELED; never assume the install proceeds without the dialog.
3. **INSTALLED is not "usable" for code.** For dynamic feature modules containing code, new classes become available to the running process only when the platform supports deferred components injection or after restart. The pragmatic patterns: (a) navigate the user to a "restart to finish" step; (b) use `SplitInstallHelper`/deferred-components APIs to inject activities/services when supported; (c) architect the feature so entry points resolve post-restart (deep links into the feature module's activity work after install+restart because the manifest entries merge). Decide per feature which pattern applies, and test on the devices you ship to — injection support varies.
4. **Sessions are resumable and observable across processes.** `splitInstallManager.sessionStates` returns in-flight sessions (including ones started before a process death); on app start, re-register listeners and reconcile UI with existing sessions — the install continues in the background, and an app that forgets this shows "install" buttons for modules already downloading.
5. **Cancellation.** `cancelInstall(sessionId)` moves to CANCELING → CANCELED; cancellation races with completion (an INSTALLING session may finish). CANCELED is a user-actionable state (offer retry), not an error.
6. **Failure taxonomy.** `SplitInstallException.errorCode` carries Play Core codes: network errors, storage-full (`ACTIVE_SESSIONS_LIMIT_EXCEEDED` family, insufficient storage), module-not-found (name mismatch between build config and request — a release-gate bug, not a runtime event), API-unavailable (device Play Store too old or sideloaded app — the big one: sideloaded APKs have no Play connection, all installs fail; detect and disable on-demand paths). Map each to user guidance, not a generic toast.
7. **Conditional delivery vs. on-demand.** `dist:on-demand="true"` modules install by request; conditional modules (`fusing`/device-feature/ABI rules) install automatically at base-install time when conditions match — no runtime session. Choose conditional for device-gated (e.g., ARCore-present) features where availability is static; on-demand for user-timed features. Misclassifying shows up as "we requested a module already there" (harmless) or "feature unavailable on capable devices" (conditional didn't fire).
8. **Don't uninstall what's running.** `deferredUninstall` APIs exist but interact with active sessions and process state; treat uninstall as a maintenance operation, not a UX path.

A worked example: a photo app's `filters` module (18 MB) installs on first tap of the Filters tab. Flow: tap → `startInstall(["filters"])` → DOWNLOADING with progress bar inline in the tab → size crosses the confirmation threshold on mobile data → REQUIRES_USER_CONFIRMATION → dialog → user accepts → INSTALLING → INSTALLED → the app checks whether injection is supported; if not, it presents "Filters ready — restart to use" with a one-tap relaunch (the module's activity is launchable post-restart). The tab remembers pending installs across process death by reconciling `sessionStates` on app open — a user who backgrounded during download returns to a live progress bar, not a reset button.

## Controls

- Gate on-demand UI on Play availability: sideloaded builds and Play-less devices must hide module-entry points (all sessions would fail); detect via Play Services availability checks.
- Reconcile `sessionStates` on every cold start and re-register listeners before user interaction; UI state derives from sessions, never from local "installing" booleans that drift from reality.
- Map every `SplitInstallException` error code to specific user guidance and telemetry; alert on module-not-found (config drift) and API-unavailable spikes (distribution anomaly).
- Instrument state-transition timing (download duration, INSTALLING dwell, confirmation decline rate); confirmation declines are a product signal about download size, not a Play defect.
- Test on the full matrix: Play Store current + old, metered/unmetered, storage-pressure devices, mid-install process death, and sideloaded builds.

## Validation evidence

- The `SplitInstallManager` API (session lifecycle, listener registration, confirmation-dialog flow, cancellation), `SplitInstallSessionState` status values and byte counters, error-code semantics, deferred components/injection behavior, and module `dist:` configuration attributes (`on-demand`, `instant`, conditional delivery) are documented in the Android Developers Play Feature Delivery guide published by Google.
- Play's confirmation-threshold behavior and sideloaded-app limitations are documented in the same guide's behavioral notes and the Play Console delivery documentation.
- A reproducible test: on a device with the app installed from Play, request a module, kill the process mid-download, relaunch, and assert the UI reconciles to the live session state and completes; then build a sideloaded variant and assert the on-demand entry points are correctly hidden — two harness runs covering the two most common production complaints.

## Failure modes and correction

- **"Installed" but classes missing.** Cause: process not restarted on the non-injection path. Correct by restart-gating entry or using supported injection deliberately, per feature.
- **Ghost sessions / stuck buttons.** Cause: UI state local instead of session-derived. Correct by `sessionStates` reconciliation on start.
- **Silent no-op on sideloads.** Cause: Play APIs unavailable. Correct by availability gating and distribution policy (feature modules only make sense for Play-distributed builds).
- **Confirmation treated as error.** Cause: `REQUIRES_USER_CONFIRMATION` not handled. Correct by launching the dialog and handling the activity result path.
- **Module name drift.** Cause: build config renamed, request string stale. Correct by a single constant source shared by build config and code, verified in a release smoke test.

## Limitations

- Requires distribution through Play with app-bundle delivery; sideloaded and alternative-store builds cannot fetch modules.
- Instant-delivery modules carry their own constraints (size ceilings, instant-app runtime) beyond on-demand flow.
- Injection support and restart requirements vary by Android version; feature availability must be probed at runtime.
- Sessions depend on Play Store state (signed-in, storage, connectivity) outside app control; design UX for those externalities.

## Canonical sources

- Google, Android Developers — Play Feature Delivery (on-demand, conditional, install states, confirmation, deferred components): https://developer.android.com/guide/playcore/feature-delivery
- Google, Android Developers — Dynamic feature module configuration (`dist:` attributes): https://developer.android.com/guide/playcore/dynamic-delivery/on-demand-delivery
