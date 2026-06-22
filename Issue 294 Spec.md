> Auto-generated from `Issue 294 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_294_SPEC.md` in the docs repo.

---
title: "AnalyticsTracker Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# AnalyticsTracker Feature Spec

**Resolves:** #294, #295

This file documents the design for AnalyticsTracker, located at `src/App/AnalyticsTracker.h` and `src/App/AnalyticsTracker.cpp`.

## Goals

- Buffered, batched, opt-in client-side analytics. Disabled by default; user must enable in `AccessibilityPanel > Privacy` (or via the system installer flag).
- Queue events in memory and flush every 60 s to the project's analytics endpoint (`POST https://cutshit.net/api/analytics/events`).
- Drop events older than 24 h or when the queue exceeds 10,000 entries (memory bound).
- Honor `AppSettings::GetAnalyticsEnabled()` — when false, all public methods are no-ops.

## Public API (sketch)

```cpp
struct AnalyticsEvent {
    std::string name;                                  // e.g. "export_completed"
    std::unordered_map<std::string, std::string> params; // small, JSON-serialisable values only
};

class AnalyticsTracker {
public:
    bool Initialize();
    void Shutdown();

    void TrackEvent(const std::string& name,
                    const std::unordered_map<std::string, std::string>& params = {});

    void Flush();   // call on graceful shutdown to drain the queue

    bool IsEnabled() const;
};
```

## Dependencies

- `UserSettings.h` (for `GetAnalyticsEnabled()`).
- `Utils/HttpClient.h`, `Utils/Timer.h`, `Utils/Logger.h`.
- `nlohmann/json`.

## Threading

- `TrackEvent` is safe to call from any thread (the queue is mutex-protected).
- The flush timer runs on a dedicated worker; the network POST is async.
- `Shutdown` blocks until any in-flight flush completes.

## Privacy

- **No PII is ever included.** The event payload is limited to: event name, params (small strings / numbers), installId hash, app version.
- InstallId hash is a salted SHA-256 of `{MAC, machineId, userUid}` — see `BetaTesterDashboard.InstallIdHash()`.
- The queue is in-memory only; nothing is written to disk. If the process crashes before the 60 s flush, those events are lost (intentional).

## Error Handling

- HTTP failure → log warn, leave events in the queue for the next flush.
- Schema-validation failure on the response → log error, drop the entire queued batch (avoid bad-server feedback loops).

## Performance Budget

- `TrackEvent` must complete under 0.05 ms (just a queue push under a mutex).
- The flush POST must not block the UI thread.
