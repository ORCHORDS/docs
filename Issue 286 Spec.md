> Auto-generated from `Issue 286 Spec.md` in the docs repo.

> Auto-generated from `Issue 286 Spec.md` in the docs repo.

> Auto-generated from `Issue 286 Spec.md` in the docs repo.

> Auto-generated from `Issue 286 Spec.md` in the docs repo.

> Auto-generated from `Issue 286 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_286_SPEC.md` in the docs repo.

---
title: "BetaTesterDashboard Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# BetaTesterDashboard Feature Spec

**Resolves:** #286, #287

This file documents the design for BetaTesterDashboard, located at `src/UI/BetaTesterDashboard.h` and `src/UI/BetaTesterDashboard.cpp`.

## Goals

- Surface beta-program status to enrolled testers: current build, days-in-beta, known-issues count, "report a problem" CTA.
- Display the tester's installId hash, their plan tier, and a regenerate-key button.
- Read most state from a Firestore-backed user record (see `Backend/FirebaseAuth`); cache locally with a short TTL.

## Public API (sketch)

```cpp
class BetaTesterDashboard {
public:
    bool Initialize(FirebaseAuth& auth, UserSettings& settings, ThemeManager& theme);
    void Shutdown();

    void Render();

    // Returns the installId hash that should be paired with any telemetry from #294
    // (AnalyticsTracker). Stable per-install.
    std::string InstallIdHash() const;

    void Refresh();    // forces a re-fetch from Firestore
};
```

## Dependencies

- `Backend/FirebaseAuth.h` (for the signed-in user record).
- `UserSettings.h`, `UI/ThemeManager.h`, `Window.h`.
- `Utils/HttpClient.h` (for Firestore REST reads).

## Threading

- Render runs on the UI thread.
- Firestore fetch is async; results are delivered via `Refresh()` continuation.

## Error Handling

- Offline / Firestore unreachable: render an empty-state card with a retry button.
- 401 from Firestore: prompt re-auth via the existing `FirebaseAuth` sign-in flow.

## Privacy

- The installId hash is generated locally (SHA-256 of MAC + machine-id, salted with the user's UID at first launch). No PII is sent to Firestore from this dashboard directly.
