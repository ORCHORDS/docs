> Auto-generated from `Issue 288 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_288_SPEC.md` in the docs repo.

---
title: "TrackManager Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# TrackManager Feature Spec

**Resolves:** #288, #289

This file documents the design for TrackManager, located at `src/Timeline/TrackManager.h` and `src/Timeline/TrackManager.cpp`.

## Goals

- Own the ordered list of tracks in a project (video, audio, overlay, effect).
- Support add / remove / re-order / mute / solo / lock / rename on tracks.
- Persist track layout to the project file via `BSP_FORMAT.md`.
- Expose change-notification callbacks so the UI (timeline panel, mixer) can react.

## Public API (sketch)

```cpp
enum class TrackKind { Video, Audio, Overlay, Effect };

struct Track {
    std::string id;          // uuid
    TrackKind   kind;
    std::string name;
    bool        muted   = false;
    bool        solo    = false;
    bool        locked  = false;
    int         height  = 64;  // px, for the UI
};

class TrackManager {
public:
    using ChangeCallback = std::function<void()>;

    bool Initialize();
    void Shutdown();

    // Track CRUD
    std::string AddTrack(TrackKind kind, const std::string& name);
    bool        RemoveTrack(const std::string& id);
    bool        RenameTrack (const std::string& id, const std::string& name);
    bool        ReorderTrack(const std::string& id, int newIndex);
    bool        SetMuted    (const std::string& id, bool muted);
    bool        SetSolo     (const std::string& id, bool solo);
    bool        SetLocked   (const std::string& id, bool locked);

    // Query
    const Track*           FindById(const std::string& id) const;
    std::vector<Track>     All() const;
    std::vector<Track>     OfKind(TrackKind kind) const;
    size_t                 Count() const { return m_tracks.size(); }

    // Persistence
    nlohmann::json ToJson() const;
    bool           FromJson(const nlohmann::json& j);

    // Change notification
    void OnChange(ChangeCallback cb) { m_onChange = std::move(cb); }

private:
    std::vector<Track>  m_tracks;
    ChangeCallback      m_onChange;
};
```

## Dependencies

- `nlohmann/json` (vcpkg).
- `CommonTypes.h`, `Logging.h`, `Utils/Uuid.h`.

## Threading

- All public methods are UI-thread only.
- The change callback fires synchronously after the mutation.

## Persistence

- Serialized into the project file under the `tracks` key. See `docs/architecture/BSP_FORMAT.md` for the on-disk schema.

## Performance Budget

- `AddTrack` / `RemoveTrack` / `ReorderTrack`: under 0.5 ms.
- `All()` returns a copy; the caller may iterate without locking.
