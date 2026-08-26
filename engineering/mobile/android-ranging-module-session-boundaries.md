# Android ranging module session boundaries

**Issue:** A proximity feature treats one ranging reading as identity or authorization and keeps scanning after the user-visible session ends.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer Android platform capability; gate by device/OS support

Android's Ranging module provides a common surface for supported ranging technologies. Model capability, permission, peer setup, active session, measurements, interruption, and closure separately.

**Source:** [Android ranging documentation](https://developer.android.com/develop/connectivity/ranging)

## Controls

- detect device/technology support and request only required permissions;
- start from explicit user intent and bind the peer/session to authenticated app state;
- validate freshness and quality before product use;
- stop promptly on lifecycle exit, permission revocation, or peer loss;
- keep high-risk authorization independent from proximity alone;
- minimize measurement retention.

## Verification

Test unsupported hardware, denial/revocation, multiple peers, stale/outlier readings, backgrounding, radio changes, interruption, duplicate start, close/reopen, and account switch.

## Gotchas

Distance estimates have uncertainty and environmental bias. Proximity is not identity or consent. Supported technologies and permissions vary across releases/devices.
