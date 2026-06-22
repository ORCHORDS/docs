> Auto-generated from `Issue 292 Spec.md` in the docs repo.

> Auto-generated from `Issue 292 Spec.md` in the docs repo.

> Auto-generated from `Issue 292 Spec.md` in the docs repo.

> Auto-generated from `Issue 292 Spec.md` in the docs repo.

> Auto-generated from `Issue 292 Spec.md` in the docs repo.

> Auto-generated from `Issue 292 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_292_SPEC.md` in the docs repo.

---
title: "UpdateChecker Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# UpdateChecker Feature Spec

**Resolves:** #292, #293

This file documents the design for UpdateChecker, located at `src/App/UpdateChecker.h` and `src/App/UpdateChecker.cpp`.

## Goals

- Periodically poll the project's update manifest (`https://cutshit.net/api/updates/stable.json`) and notify the user when a newer version is available.
- Compare the local app version (read from the build's `VERSION` resource or `version.h`) against the manifest's `latest.stable` field using semantic-version ordering.
- Support channels: `stable`, `beta`, `nightly`. The channel is user-selectable; default is `stable`.
- Throttle network calls to one per hour, regardless of how often `Tick()` is called.

## Public API (sketch)

```cpp
enum class UpdateChannel { Stable, Beta, Nightly };

struct UpdateInfo {
    std::string latestVersion;
    std::string releaseNotesUrl;
    bool        mandatory = false;
};

class UpdateChecker {
public:
    bool Initialize(const std::string& localVersion,
                    UpdateChannel channel = UpdateChannel::Stable);
    void Shutdown();

    // Call once per UI frame. Internally throttles to 1 call / hour.
    void Tick();

    // Subscribe to update notifications. Callback fires on the UI thread.
    void OnUpdateAvailable(std::function<void(const UpdateInfo&)> cb);

    // Force a check now (bypasses the throttle). Used by the "Check now" menu item.
    void CheckNow();

    // Channel
    void SetChannel(UpdateChannel c);
    UpdateChannel Channel() const { return m_channel; }

private:
    void FetchManifest();  // runs on a worker; results delivered via m_cb on UI thread
};
```

## Dependencies

- `Utils/HttpClient.h`, `Utils/SemanticVersion.h`, `nlohmann/json`, `CommonTypes.h`, `Logging.h`.

## Threading

- `Tick` and `CheckNow` are UI-thread.
- `FetchManifest` runs on an internal worker.
- The update callback is marshalled back to the UI thread before invocation.

## Error Handling

- Network failure → log warn; do not invoke the callback. Retry on next `Tick()` past the throttle window.
- Manifest schema mismatch → log error and disable the checker for the session (avoid spamming bad manifests).

## Privacy

- The HTTP request includes only the channel, the local version, and a generic User-Agent. No installId, no analytics tags.
