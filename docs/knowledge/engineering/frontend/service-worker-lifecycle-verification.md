---
title: "Service Workers Lifecycle Algorithms"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Service Workers Lifecycle Algorithms

## Pinned snapshot and status
This article pins the **Service Workers Candidate Recommendation Draft dated 12 August 2026**. It is not a W3C Recommendation; record this dated snapshot because lifecycle algorithms can change before Recommendation status. The tested concepts are registration, update, install, waiting, activation, clients, and fetch handling.

## Lifecycle algorithms
`register()` resolves scope and script URL, applies same-origin and trustworthy-context checks, and creates or reuses a registration. The **Update** algorithm fetches the top-level script with the service-worker script fetch rules and compares script resources byte-for-byte with the incumbent worker; imported scripts participate according to update-via-cache behavior. A changed script creates an **installing** worker and dispatches `install`.

`event.waitUntil(promise)` extends install lifetime. Rejection makes installation fail and the new worker becomes redundant; it must not replace the active worker. A successful install normally moves the worker to **waiting** while controlled clients still use the old active worker. `skipWaiting()` requests activation without waiting for those clients to disappear; this can mix a new worker with old page assets and therefore requires an application protocol.

Activation replaces the active worker, dispatches `activate`, and waits for its lifetime promises. `clients.claim()` makes eligible uncontrolled clients controlled by the active worker; it is not equivalent to activation. Workers may be terminated between events, so correctness cannot rely on globals. A fetch event must call `respondWith()` synchronously during dispatch; its promise may resolve later. Navigation preload and cache migration need explicit failure behavior.

## Release design and tests
Version cache names by release, precache into a temporary cache during install, and reject install if required assets fail integrity or status checks. During activate, delete only caches owned by this registration. Coordinate `skipWaiting` through a user-visible update message and reload clients after `controllerchange` when schema/assets are incompatible.

Test first registration, byte-identical update, changed top-level script, changed import under each `updateViaCache` value, failed install, waiting with two open tabs, explicit skip-waiting, activation failure, claim, offline navigation, worker termination, cache eviction, and rollback. Use DevTools protocol or WebDriver logs to retain worker state transitions, script response headers, registration scope, controller identity, and cache contents.

## Sources
- [Service Workers living specification](https://w3c.github.io/ServiceWorker/)
- [Service Workers lifecycle model](https://w3c.github.io/ServiceWorker/#service-worker-lifetime)
