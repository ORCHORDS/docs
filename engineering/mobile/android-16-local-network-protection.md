# Android 16 local network protection

**Date:** 2026-08-26
**Status:** documented
**Source:** https://developer.android.com/about/versions/16/behavior-changes-16

## Context

Android's Local Network Protections project is moving LAN access away from being implicitly available to any app with `INTERNET` permission.

## What to test

Android documents local-network cases including outgoing and incoming TCP, UDP unicast/multicast/broadcast, local service discovery, `.local` resolution, and libraries or framework APIs that perform LAN operations.

The Android 16 phase is an opt-in compatibility-testing stage; developers should not misstate that every Android 16 app is already subject to final enforcement.

## Migration pattern

1. Inventory direct sockets, mDNS/SSDP, casting, service discovery, device pairing, and SDKs that touch LAN addresses.
2. Exercise the Android compatibility flag described in current platform guidance.
3. Test both permission-granted and permission-denied paths.
4. Treat permission rejection/revocation as normal runtime states.
5. Avoid silently falling back to unsafe discovery mechanisms.
6. Re-check platform guidance before shipping because the rollout spans Android releases.

## Verification

Test outbound and inbound LAN operations separately while confirming ordinary internet traffic remains functional when local-network access is denied.

## Gotcha

WebView-originated LAN traffic inherits the host app's permission state according to current Android guidance.
