# Android Play Feature Delivery: conditional and on-demand modules

**Issue:** Code assumes every dynamic feature exists after base-app installation. A conditional rule changes, an on-demand install fails, or Play delivers a different split set, producing missing screens, broken deep links, and startup crashes.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Delivery model

Play Feature Delivery lets an Android App Bundle package functionality in feature modules with delivery configured for installation time, conditions, or on demand. A delivered module is not equivalent to an enabled or authorized product feature.

- **Conditional delivery** can make a module available at install time only when configured device/user conditions match.
- **On-demand delivery** requires the app to request installation at runtime and observe the install session.
- The base module must remain valid without an optional module.

Do not place unconditional base startup references to classes/resources that can be absent. Route access through a stable capability boundary in the base module.

## Runtime state machine

1. Check both product entitlement and installed-module state before navigation.
2. For on-demand access, request the module through the Play Core feature-delivery API and persist only the session identifier/state—not a guessed completion flag.
3. Handle pending, downloading, downloaded/installing, installed, failed, canceled, and user-confirmation states exposed by the API.
4. Make listener registration lifecycle-safe and re-query installed modules after process death or app restart.
5. Show bytes/progress when available, a cancel path, and a retry that maps known error codes to useful actions.
6. Validate the destination again after installation. Entitlement, account, and policy can change while bytes download.
7. Keep deep links recoverable: retain a bounded pending destination, install, then re-resolve it.
8. Remove only modules designed for on-demand uninstall and tolerate delayed reclamation.

## Packaging controls

Keep contracts/interfaces and fallback UI in the base. Avoid duplicate native libraries/resources across modules, and verify code shrinking does not remove entry points loaded after installation. Version base and features together through the App Bundle; do not design a dynamic feature as an independent arbitrary-code update channel.

Conditional country/device rules are distribution hints, not security enforcement. Server authorization and runtime capability checks remain required.

## Verification

Use bundle/APK split tooling and Play-supported test paths to cover base-only install, condition true/false, slow and interrupted download, insufficient storage, network loss, confirmation required/denied, process death at every state, update with module installed, module removal, and deep links before installation. Test split-compatible resources and native ABIs on real supported devices.

## Gotchas

- Local monolithic debug installs can hide missing-split bugs.
- “Requested” is not “installed”; class loading must wait for confirmed installed state.
- Delivery configuration changes require a new release and can affect upgrade cohorts.
- Play Feature Delivery is Play-specific; define behavior for non-Play distribution.

## Sources

- [Android Developers — Configure on-demand delivery](https://developer.android.com/guide/playcore/feature-delivery/on-demand)
- [Android Developers — Configure conditional delivery](https://developer.android.com/guide/playcore/feature-delivery/conditional)
