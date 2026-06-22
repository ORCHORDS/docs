> Auto-generated from `docs/engineering/ISSUE_267_SPEC.md` in the docs repo.

---
title: "FirebaseIntegration Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# FirebaseIntegration Feature Spec

**Resolves:** #267, #268

This file documents the design for FirebaseIntegration, located at `src/Backend/FirebaseIntegration.h` and `src/Backend/FirebaseIntegration.cpp`.

## Goals

- Own the singleton `firebase::App` instance for the editor (one `App` per process).
- Provide lazy access to Firebase sub-services (`Auth`, `Firestore`, `Storage`, `Functions`) so callers don't need to know about the C++ SDK's handle types.
- Initialize from `google-services.json` / `GoogleService-Info.plist` resources (Android / iOS) or from `firebase.json` env vars on desktop.
- Cleanly tear down the `firebase::App` on `Shutdown()` to avoid dangling handles.

## Public API (sketch)

```cpp
class FirebaseIntegration {
public:
    bool Initialize(const FirebaseConfig& cfg);   // reads env vars if cfg is empty
    void Shutdown();

    bool IsInitialized() const { return m_app != nullptr; }

    firebase::App&       App()        { return *m_app; }
    firebase::auth::Auth& Auth();                   // lazy-init the Auth handle
    firebase::firestore::Firestore& Firestore();
    firebase::storage::Storage&   Storage();
    firebase::functions::Functions& Functions();

private:
    std::unique_ptr<firebase::App>  m_app;
    AuthHandle    m_auth;
    FirestoreHandle m_firestore;
    StorageHandle   m_storage;
    FunctionsHandle m_functions;
};
```

## Dependencies

- Third-party: `firebase_cpp_sdk` (link via CMake `Firebase::firebase_app`, `Firebase::firebase_auth`, etc.).
- `CommonTypes.h`, `Logging.h`, `Utils/Env.h`.

## Threading

- `Initialize` and `Shutdown` are called once from the main thread.
- Firebase sub-service handles are safe to use from any thread (per Firebase C++ SDK contract).

## Error Handling

- `Initialize` returns `false` if the SDK fails to load or `google-services.json` is malformed. The previous instance (if any) is cleaned up before returning.
- Sub-service getters return references; the caller can check `IsInitialized()` first.

## Configuration

- Desktop: reads `FIREBASE_API_KEY`, `FIREBASE_PROJECT_ID`, `FIREBASE_APP_ID`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_STORAGE_BUCKET` from environment.
- Android: bundled `google-services.json` is unpacked by Gradle and read at runtime.
- iOS: bundled `GoogleService-Info.plist` read via the SDK.

## Performance Budget

- `Initialize` should complete in under 500 ms on desktop.
- Lazy sub-service getters should complete in under 5 ms after `Initialize`.
