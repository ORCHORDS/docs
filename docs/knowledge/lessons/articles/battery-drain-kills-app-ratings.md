# Mobile Energy Use Is a Release Constraint

**Issue:** Unnecessary location, network, CPU, wakeup, and background activity consume energy and may be deferred or suspended by the operating system. Functional foreground tests do not reveal this boundary.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Lesson

Treat energy behavior as a measured release property. Ask for the lowest location accuracy and update frequency that satisfy the user-visible purpose, stop work when it is no longer needed, and schedule deferrable work through platform lifecycle APIs.

## Controls

- Maintain an energy budget per representative user journey and compare it with a controlled baseline on supported physical devices.
- Prefer event-driven delivery and batched transfers to frequent polling and small network wakeups.
- Request location only for a declared purpose; reduce accuracy, defer delivery, pause, or stop updates when possible.
- Use Android WorkManager constraints and Apple background-task mechanisms for deferrable work rather than assuming a permanent process.
- Handle platform cancellation or expiration and checkpoint work so an interrupted task can resume safely.
- Remove accidental wake locks, runaway timers, retries without backoff, and background animations.
- Review privacy permissions and energy behavior together because continuous sensors affect both.

## Verification

- Profile foreground, background, screen-off, poor-network, stationary, and moving scenarios on physical devices.
- Force Android background restrictions and Apple task expiration or suspension paths.
- Compare energy diagnostics before and after dependency, retry, location, and synchronization changes.
- Assert services stop when the feature, session, permission, or lifecycle state no longer requires them.
- Run a long-duration soak test to reveal periodic wakeups that a short trace misses.

## Gotchas

There is no universal “percent battery per hour” threshold: hardware, battery condition, radio state, signal, temperature, and workload change results. Simulator traces do not reproduce radio and battery behavior. Significant-change location is one option, not a universal substitute for every background-location requirement.

## Official sources

- [Android: Optimize for battery life](https://developer.android.com/develop/background-work/background-tasks/optimize-battery)
- [Android WorkManager](https://developer.android.com/topic/libraries/architecture/workmanager)
- [Apple: Handling location updates in the background](https://developer.apple.com/documentation/corelocation/handling-location-updates-in-the-background)
- [Apple: Measure energy impact with Xcode](https://developer.apple.com/library/archive/documentation/Performance/Conceptual/EnergyGuide-iOS/MonitorEnergyWithXcode.html)
