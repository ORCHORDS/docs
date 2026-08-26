# Mobile binaries require server compatibility windows

**Issue:** A backend deploy assumes every mobile client upgrades immediately, breaking older store-approved binaries or new binaries during staged rollout.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Lesson

Mobile release and server release are separate distributed rollouts. Maintain an explicit compatibility window across API schemas, authentication, feature flags, and data formats, because review, staged distribution, user choice, and managed devices keep several binary versions active.

**Sources:** [Google Play staged rollouts](https://support.google.com/googleplay/android-developer/answer/6346149) · [Apple phased release](https://developer.apple.com/help/app-store-connect/update-your-app/release-a-version-update-in-phases/)

## Apply

- publish minimum, current, and tested client-version policy;
- make additive API changes before removing fields or behavior;
- gate new server behavior on negotiated capabilities, not user-agent guesses;
- retain kill switches and a safe degraded path for old clients;
- separate “upgrade available” from “upgrade required” policy;
- monitor errors by app build, OS, API version, and rollout cohort.

## Verify

Run contract tests for every supported binary/API combination, including new-client/old-server during preproduction. Simulate rollout pause, rollback, store rejection, offline device returning later, and forced-upgrade escape paths.

## Gotchas

A staged rollout does not update existing users on demand. Remote flags cannot repair code before flag initialization. Forced upgrades can lock out users whose device cannot install the new OS requirement.
