# Android SDK Runtime process death and backward compatibility

**Issue:** An app integrates a runtime-enabled SDK as if it were an in-process library. It keeps direct object references, stores important state only inside the SDK process, or assumes every supported Android device provides SDK Runtime. Process death and older devices then produce stale handles, lost state, and divergent privacy boundaries.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental platform integration; validate current release support

## Problem and applicability

Android's Privacy Sandbox SDK Runtime can load a runtime-enabled SDK into a separate sandboxed process with restricted permissions and communication through defined interfaces. Current platform availability and distribution rules vary by Android release and Privacy Sandbox program status, so an integration also needs the documented backward-compatibility path.

Use the model for eligible SDKs whose vendor and Play distribution support the runtime. Do not describe it as a general-purpose isolation sandbox for arbitrary app plugins.

## Controls and implementation

1. Integrate the runtime-enabled SDK through the current Android/Privacy Sandbox toolchain and generated interface contract. Keep direct app dependencies on the provider implementation out of the client module.
2. Treat every remote reference as revocable. Handle binder disconnection, sandbox death, app-process death, and SDK reload without assuming the previous object or session remains valid.
3. Store authoritative business state in the app or backend, not only inside the SDK sandbox. After reload, re-establish the minimum session state through a versioned, idempotent handshake.
4. Keep calls coarse-grained and asynchronous. Define timeouts, cancellation, payload-size bounds, and explicit error mapping; a remote call is not equivalent to a local method call.
5. Use the official backward-compatibility library/path for Android versions without platform SDK Runtime. Test it as a separate security and lifecycle cohort rather than claiming identical isolation.
6. Request only documented SDK Runtime APIs and permissions. A capability missing in the sandbox must not trigger a hidden in-process fallback with broader access.
7. Validate SDK and interface versions before use. Fail closed for sensitive operations and show a recoverable product fallback when the provider is unavailable.
8. Keep telemetry partitioned by platform-runtime versus compatibility mode, without collecting cross-app identifiers or data the runtime is intended to restrict.

## Verification

Test supported and unsupported Android versions, platform runtime and compatibility mode, first load, concurrent load, provider initialization failure, sandbox kill during each call, app process death, device reboot, SDK update, client/provider version skew, IPC timeout, oversized payload, offline mode, and Play delivery failure.

Assert no durable entitlement or purchase is granted solely from sandbox memory, all remote handles are reacquired after death, and fallback mode receives an explicit review for permissions and data access.

## Gotchas

- Separate process does not remove the need to distrust and validate SDK outputs.
- Backward compatibility can have different isolation properties from platform SDK Runtime.
- Program APIs and availability can change; pin and verify official release documentation.
- UI rendering and lifecycle callbacks crossing the boundary require their own ownership rules.

## Official sources

- [Privacy Sandbox on Android — SDK Runtime architecture](https://privacysandbox.google.com/private-advertising/sdk-runtime/architecture)
- [Privacy Sandbox on Android — SDK Runtime key concepts](https://privacysandbox.google.com/private-advertising/sdk-runtime/developer-guide/key-concepts)
