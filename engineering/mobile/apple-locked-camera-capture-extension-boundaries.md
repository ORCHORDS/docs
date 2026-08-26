# Apple LockedCameraCapture extension boundaries

**Issue:** A camera experience launched while the device is locked assumes normal app storage, account, networking, and UI state are available.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer Apple platform API; gate by OS availability

LockedCameraCapture supports camera capture from the Lock Screen through a constrained extension experience. Design it as a separate execution boundary with minimal dependencies and a deliberate handoff into the unlocked app.

**Source:** [Apple LockedCameraCapture documentation](https://developer.apple.com/documentation/lockedcameracapture)

## Controls

- collect only media and metadata required for the explicit capture;
- keep extension startup small and avoid assuming network/account availability;
- use approved shared-container/handoff mechanisms;
- protect captured files with appropriate data protection;
- defer sensitive editing, sharing, and account actions until unlock;
- make imports idempotent and clean abandoned temporary data.

## Verification

Test locked/unlocked launch, no storage, interruption, camera denial, orientation, repeated capture, app update, extension crash, unlock handoff, import retry, and deletion. Verify other accounts cannot see captured content through shared state.

## Gotchas

Lock-screen availability is not user authentication for a backend action. Extensions have lifecycle/resource constraints. Never place secrets or broad app state in shared defaults for convenience.
