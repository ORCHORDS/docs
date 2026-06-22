> Auto-generated from `Issue 265 Spec.md` in the docs repo.

> Auto-generated from `Issue 265 Spec.md` in the docs repo.

> Auto-generated from `Issue 265 Spec.md` in the docs repo.

> Auto-generated from `Issue 265 Spec.md` in the docs repo.

> Auto-generated from `Issue 265 Spec.md` in the docs repo.

> Auto-generated from `Issue 265 Spec.md` in the docs repo.

> Auto-generated from `Issue 265 Spec.md` in the docs repo.

> Auto-generated from `Issue 265 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_265_SPEC.md` in the docs repo.

---
title: "AppServices Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# AppServices Feature Spec

**Resolves:** #265, #266

This file documents the design for AppServices, located at `src/App/AppServices.h` and `src/App/AppServices.cpp`.

## Goals

- Hold singleton-style handles to the editor's long-lived service objects (analytics, update checker, firebase auth, telemetry) so other modules can resolve them via dependency injection without globals.
- Own the lifecycle of those services: initialize at startup, shut down in reverse order at exit.
- Provide a single `Services()` accessor that returns the bundle to UI / Engine layers.

## Public API (sketch)

```cpp
class AppServices {
public:
    static AppServices& Get();

    bool Initialize();   // constructs and initializes all sub-services
    void Shutdown();     // shuts down in reverse order

    // Sub-services are accessed by reference. Pointers are non-null after Initialize.
    Backend::AuthManager&        Auth()       { return *m_auth; }
    Backend::TokenManager&       Tokens()     { return *m_tokens; }
    Backend::FirebaseIntegration& Firebase()  { return *m_firebase; }
    App::AnalyticsTracker&       Analytics()  { return *m_analytics; }
    App::UpdateChecker&          Updater()    { return *m_updater; }

    // Liveness check; returns false during Initialize / after Shutdown.
    bool IsReady() const { return m_ready; }

private:
    AppServices() = default;
    std::unique_ptr<Backend::AuthManager>         m_auth;
    std::unique_ptr<Backend::TokenManager>        m_tokens;
    std::unique_ptr<Backend::FirebaseIntegration> m_firebase;
    std::unique_ptr<App::AnalyticsTracker>        m_analytics;
    std::unique_ptr<App::UpdateChecker>           m_updater;
    bool m_ready = false;
};
```

## Dependencies

- `Backend/AuthManager.h`, `Backend/TokenManager.h`, `Backend/FirebaseIntegration.h`.
- `App/AnalyticsTracker.h`, `App/UpdateChecker.h`.
- `CommonTypes.h`, `Logging.h`.

## Threading

- `Initialize` and `Shutdown` are called once from the main thread.
- Sub-service accessors may be called from any thread after `Initialize` returns.
- The references returned are stable for the program's lifetime.

## Error Handling

- `Initialize` returns `false` if any sub-service fails to start. Already-initialized services are shut down before returning.
- Sub-services log their own errors; `AppServices` does not swallow them.

## Performance Budget

- `Initialize` should complete in under 1 s on a cold start.
- Service accessors are inline and lock-free.
