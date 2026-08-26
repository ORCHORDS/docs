# Android 16 granular health permission migration

**Issue:** A health application targeting newer Android versions keeps broad body-sensor permissions, leading to denied access, revoked grants, or misleading consent.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Android 16 moves relevant health access toward granular `android.permissions.health` permissions. Request only the data type and access mode needed, and provide the required privacy-policy/rationale activity.

**Source:** [Android 16 behavior changes](https://developer.android.com/about/versions/16/behavior-changes-16)

## Controls

- map each feature to its exact read/write health permission, such as heart-rate access;
- use the dedicated background health-data permission only for a justified background feature;
- declare and maintain the privacy-policy activity expected by the platform;
- request permissions in user context, explain purpose, and keep the feature usable when optional access is denied;
- migrate target-SDK behavior behind compatibility tests rather than retaining deprecated broad permissions.

## Verification

- clean install, upgrade, denial, revocation, and “don't ask again” paths are tested;
- foreground-only access cannot continue in the background;
- removing a feature also removes its manifest permission and data collection;
- policy/rationale navigation works offline and after process recreation.

## Gotchas

- a manifest declaration does not grant access.
- Health Connect record permissions and platform sensor permissions have different lifecycles.
- never infer consent for one health type from another.
