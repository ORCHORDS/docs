> Auto-generated from `Issue 278 Spec.md` in the docs repo.

> Auto-generated from `Issue 278 Spec.md` in the docs repo.

> Auto-generated from `Issue 278 Spec.md` in the docs repo.

> Auto-generated from `Issue 278 Spec.md` in the docs repo.

> Auto-generated from `Issue 278 Spec.md` in the docs repo.

> Auto-generated from `Issue 278 Spec.md` in the docs repo.

> Auto-generated from `Issue 278 Spec.md` in the docs repo.

> Auto-generated from `Issue 278 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_278_SPEC.md` in the docs repo.

---
title: "FirebaseAuth Feature Spec (supplementary)"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# FirebaseAuth Feature Spec (supplementary)

**Resolves:** #278

This file is a supplementary spec for the `.cpp` half of `src/Backend/FirebaseAuth.{h,cpp}`. The header side is covered by `ISSUE_72_SPEC.md`; this one covers the implementation file's contract.

## Goals

- Implement `FirebaseAuth::Initialize` / `Shutdown` and the `SignIn*` / `SignOut` flows defined in the header.
- Wire the C++ SDK's `firebase::auth::Auth` callbacks into the editor's UI-thread dispatcher.
- Persist the ID token across app restarts using `Utils/Keychain_*`.

## Public API (sketch)

The header is in `ISSUE_72_SPEC.md`. The implementation must provide:

```cpp
bool FirebaseAuth::Initialize();
void FirebaseAuth::Shutdown();

void FirebaseAuth::SignInWithEmailPassword(const std::string& email,
                                           const std::string& password);
void FirebaseAuth::SignInWithGoogle();         // OAuth redirect on desktop
void FirebaseAuth::SignInWithGitHub();
void FirebaseAuth::SignOut();

std::optional<AuthUser> FirebaseAuth::CurrentUser() const;
void                   FirebaseAuth::RefreshToken();
```

## Dependencies

- `firebase_cpp_sdk` (`firebase::auth::Auth`, `firebase::auth::Credential`).
- `Backend/FirebaseIntegration.h` (to get the `firebase::App`).
- `Utils/Keychain_*.h` (per-platform secret store).
- `CommonTypes.h`, `Logging.h`.

## Threading

- All public methods are UI-thread.
- Firebase's async callbacks are marshalled via the editor's `UiDispatcher::Post`.

## Error Handling

- Sign-in failure surfaces `m_lastError.code` + `m_lastError.message`.
- Network failure during token refresh falls back to the persisted token (still valid for its 1 h TTL).

## Performance Budget

- `Initialize` should complete in under 200 ms (token load from keychain).
- Sign-in round-trip should complete in under 2 s on a typical broadband connection.
