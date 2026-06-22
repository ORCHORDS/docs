> Auto-generated from `Issue 271 Spec.md` in the docs repo.

> Auto-generated from `Issue 271 Spec.md` in the docs repo.

> Auto-generated from `Issue 271 Spec.md` in the docs repo.

> Auto-generated from `Issue 271 Spec.md` in the docs repo.

> Auto-generated from `Issue 271 Spec.md` in the docs repo.

> Auto-generated from `Issue 271 Spec.md` in the docs repo.

> Auto-generated from `Issue 271 Spec.md` in the docs repo.

> Auto-generated from `Issue 271 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_271_SPEC.md` in the docs repo.

---
title: "TokenManager Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# TokenManager Feature Spec

**Resolves:** #271, #272, #279, #280

This file documents the design for TokenManager, located at `src/Backend/TokenManager.h` and `src/Backend/TokenManager.cpp`.

> Note: issues #271 / #272 and #279 / #280 both target the same file paths (`src/Backend/TokenManager.{h,cpp}`). This spec covers both — they are duplicates and should be closed together.

## Goals

- Track the editor's two-tier token system:
  - **Beta keys** (`CUTSHIT-XXXX-XXXX-XXXX`) — generated on signup, redeemed on first launch of the desktop app.
  - **CS Tokens** — earned via in-app compute contribution; balance is fetched from Firestore.
- Provide atomic issue / redeem / revoke / balance operations with audit logging.
- Surface the current user's balance to the dashboard and to the export flow (premium export options gated by balance).

## Public API (sketch)

```cpp
struct BetaKey {
    std::string key;             // "CUTSHIT-XXXX-XXXX-XXXX"
    std::string issuedToUid;     // Firebase UID
    int64_t     issuedAt;        // unix seconds
    int64_t     redeemedAt;      // 0 if unredeemed
    std::string installIdHash;   // set on redeem
    bool        revoked = false;
};

struct CsBalance {
    int64_t     available = 0;
    int64_t     pending   = 0;
    int64_t     lifetimeEarned = 0;
};

class TokenManager {
public:
    bool Initialize(FirebaseIntegration& fb);
    void Shutdown();

    // Beta keys
    std::optional<BetaKey> IssueBetaKey (const std::string& uid);
    bool                    RedeemBetaKey(const std::string& key,
                                          const std::string& installIdHash,
                                          const std::string& uid);
    bool                    RevokeBetaKey(const std::string& key);
    std::optional<BetaKey>  LookupBetaKey(const std::string& key);

    // CS tokens
    CsBalance GetBalance(const std::string& uid);
    bool      Credit   (const std::string& uid, int64_t amount, const std::string& reason);
    bool      Debit    (const std::string& uid, int64_t amount, const std::string& reason);
};
```

## Dependencies

- `Backend/FirebaseIntegration.h` (for the Firestore handle).
- `CommonTypes.h`, `Logging.h`, `Utils/Uuid.h`.

## Threading

- All methods are UI-thread.
- Firestore reads / writes are async; the methods block (with a short timeout) for the result so the caller can use them synchronously.

## Error Handling

- `RedeemBetaKey` returns `false` for: malformed key, key already redeemed, key revoked, installIdHash mismatch.
- `Debit` returns `false` if the balance would go negative; no partial debit is performed.

## Security

- Beta keys are generated with a cryptographically-secure RNG (`Utils/SecureRandom.h`).
- All key mutations are audited to a `beta_key_audit` Firestore collection with timestamp + actor + reason.
- CS Token credit / debit requires the signed-in user's UID to match the request — server-side enforcement via Firestore rules.

## Performance Budget

- Key lookup: under 50 ms (Firestore point-read).
- Balance fetch: under 100 ms (Firestore point-read).
