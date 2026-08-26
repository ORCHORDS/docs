# Wear OS Tiles freshness, timeline, and update budget

**Issue:** A Wear OS Tile polls frequently to keep a value “live,” performs network work during every tile request, or assumes an update request redraws immediately. The system throttles it, battery use rises, and users see blank or stale content when connectivity is weak.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

Wear OS Tiles are glanceable, system-rendered surfaces with system-controlled update timing. The platform provides timelines for predictable future states, freshness intervals for periodic refresh, and explicit update requests when app data changes. None is a real-time execution guarantee.

Use a Tile for small, quickly understandable state and actions. Move continuous interaction, long content, authentication, and heavy processing into the app or another appropriate surface.

## Controls and implementation

1. Return a valid cached layout promptly from the Tile service. Do not block tile rendering on a network request, database migration, or expensive computation.
2. Put predictable future changes into the tile timeline so the system can select entries without waking the app for each transition.
3. Set a freshness interval only for data that can tolerate inexact periodic refresh. The platform can delay updates and does not promise a precise alarm.
4. When local or externally delivered data changes, persist it first and request a tile update. Treat the request as a hint; the next render must read the durable current state.
5. Use WorkManager for deferrable expensive refresh and an appropriate push path for genuinely external changes. Coalesce repeated triggers and respect platform limits; do not build a one-minute polling loop.
6. Maintain a last-known-good snapshot with timestamp and a readable stale/offline state. Never show fabricated “current” data when refresh fails.
7. Keep actions idempotent and route complex work to the app. The Tile should remain correct when tapped twice, restored after process death, or rendered from cache.
8. Version state and layout resources together. If a schema changes, migrate the stored snapshot before it is consumed by a new Tile provider.

## Verification

Test timeline boundary changes, freshness refresh, explicit update request, repeated/coalesced requests, device offline, stale cache, low battery, doze, process death, reboot, app update, timezone and clock changes, locale and font scale, removed Tile, and companion phone unavailable.

Measure response latency and wakeups on physical watches. Confirm the Tile always returns a valid fallback within platform expectations and never requires an immediate system callback for correctness.

## Gotchas

- Update requests are rate-limited and asynchronous; they do not promise an instant redraw.
- Freshness intervals are minimum intentions, not exact schedules.
- A timeline is best for known future states, not speculative network results.
- The official guidance can change with Wear OS releases; recheck limits during upgrades.

## Official sources

- [Android Developers — Update information displayed in Tiles](https://developer.android.com/training/wearables/tiles/update)
- [Android Developers — Build a Tile service](https://developer.android.com/training/wearables/tiles)
