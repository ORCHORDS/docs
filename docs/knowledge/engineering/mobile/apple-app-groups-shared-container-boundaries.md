# Apple App Groups shared-container boundaries

**Issue:** An iOS or macOS app and its extension share files through ad hoc paths or assume App Groups are automatic synchronization. Data corrupts under concurrent access, targets use different entitlements, or sensitive data becomes available to every group member.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Entitlement boundary

The App Groups entitlement authorizes related, signed apps/extensions to access a shared container identified by an application-group identifier. Every participating target needs the correctly provisioned group entitlement.

Membership is a trust expansion: all entitled members can access group data according to platform APIs. App Groups do not provide per-file authorization between members, and they do not automatically share Keychain items—the Keychain access-groups entitlement is separate.

## Storage pattern

1. Define one owner and schema for each shared dataset. Document every target permitted to read or write.
2. Resolve the container with the platform container API; never construct a filesystem path from bundle identifiers or assume simulator paths match devices.
3. Treat a missing container URL as a provisioning/configuration failure and preserve local data. Do not fall back to a public or unprotected path.
4. Use an app-group user-defaults suite only for small preferences and coordination markers, not blobs, secrets, or transactional queues.
5. For files/databases, use atomic writes and a cross-process-safe coordination/locking design supported by the storage engine. In-process mutexes do not coordinate extensions.
6. Version the shared schema. Readers must tolerate an older/newer writer during application or extension updates.
7. Encrypt especially sensitive application data with keys whose access policy matches all intended group members. Avoid placing authentication bearer tokens in the container by default.
8. Bound extension work and recover from termination mid-write. Commit data before publishing a “ready” marker.

## macOS and mobile behavior

Use the same entitlement discipline on iOS-family and macOS targets, but test sandbox, provisioning, and lifecycle differences separately. An extension can be launched without the containing app running. Shared state must not depend on an in-memory app singleton.

If CloudKit or another remote synchronizer is used, the App Group remains only the local coordination boundary. Define conflict resolution and account scoping independently.

## Verification

Test each target's signed entitlements, first launch, missing/mismatched group ID, app/extension concurrent writes, one target updated before another, crash during commit, low storage, logout/account switch, reinstall, device lock state, and macOS/iOS platform variants. Assert one account never reads another account's residual group data.

## Gotchas

- Enabling a capability in one Xcode target does not configure every extension.
- Shared UserDefaults notifications are not a durable transaction protocol.
- Container access is not proof that the caller should see every record.
- Deleting the containing app does not justify assuming a particular container-retention lifecycle; clean sensitive state explicitly on logout.

## Sources

- [Apple — App Groups entitlement](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.application-groups)
- [Apple — Configuring App Groups](https://developer.apple.com/documentation/Xcode/configuring-app-groups)
