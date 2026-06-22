> Auto-generated from `Issue 269 Spec.md` in the docs repo.

> Auto-generated from `Issue 269 Spec.md` in the docs repo.

> Auto-generated from `Issue 269 Spec.md` in the docs repo.

> Auto-generated from `Issue 269 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_269_SPEC.md` in the docs repo.

---
title: "AuthManager Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# AuthManager Feature Spec

**Resolves:** #269, #270

This file documents the design for AuthManager, located at `src/Backend/AuthManager.h` and `src/Backend/AuthManager.cpp`.

## Goals

- Wrap Firebase Authentication (email/password, Google, GitHub OAuth) for the editor's sign-in flow.
- Persist the ID token + refresh token across app restarts using the platform keychain (Windows Credential Manager, macOS Keychain, Linux Secret Service).
- Expose sign-in / sign-out / current-user / token-refresh as a small synchronous-feeling API; the underlying SDK calls are async.
- Emit change callbacks so the UI (the "Sign in" button, the dashboard, the beta tester dashboard) can react.

## Public API (sketch)

```cpp
struct AuthUser {
    std::string uid;
    std::string email;
    std::string displayName;
    std::string photoUrl;
    std::string idToken;          // current ID token (JWT)
    int64_t     idTokenExpiresAt; // unix seconds
};

class AuthManager {
public:
    using ChangeCallback = std::function<void(const AuthUser* user)>;

    bool Initialize(FirebaseIntegration& fb);
    void Shutdown();

    // Sign-in flows (return immediately; result via callback).
    void SignInWithEmail(const std::string& email, const std::string& password);
    void SignInWithGoogle();
    void SignInWithGitHub();
    void SignOut();

    // Query
    const AuthUser* CurrentUser() const { return m_current.get(); }
    bool IsSignedIn() const { return m_current != nullptr; }

    // Token refresh
    bool RefreshIdToken();   // returns true if a fresh token is now available

    // Subscriptions
    void OnChange(ChangeCallback cb) { m_onChange = std::move(cb); }

private:
    void PersistTokens();     // keychain write
    void LoadPersistedTokens(); // keychain read at Initialize
};
```

## Dependencies

- `Backend/FirebaseIntegration.h` (which owns the `firebase::auth::Auth` handle).
- Platform keychain wrappers (`Utils/Keychain_win.h`, `Utils/Keychain_mac.h`, `Utils/Keychain_linux.h`).
- `CommonTypes.h`, `Logging.h`.

## Threading

- Public methods are UI-thread.
- Firebase's async callbacks are marshalled back to the UI thread before invoking `m_onChange`.

## Error Handling

- Sign-in failures populate `m_lastError` (a struct with code + message) and invoke `m_onChange(nullptr)` to let the UI show an error.
- No exceptions cross the module boundary.

## Security

- ID tokens are written to the keychain only, never to plain config files.
- The refresh token is rotated on every successful use of the ID token.

## Performance Budget

- `SignInWith*` returns in under 5 ms (the actual sign-in runs async).
- `CurrentUser()` is a lock-free getter.
