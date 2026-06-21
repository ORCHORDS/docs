---
title: "PresetManager Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# PresetManager Feature Spec

**Resolves:** #275, #276

This file documents the design for PresetManager, located at `src/Export/PresetManager.h` and `src/Export/PresetManager.cpp`.

## Goals

- Persist named export presets (codec, bitrate, resolution, container, audio settings) across application restarts.
- Ship a built-in starter pack: "YouTube 1080p", "YouTube 4K", "Twitter 720p", "Archive Master", "WebM VP9".
- Allow the user to clone, edit, delete, import, and export presets as JSON files.

## Public API (sketch)

```cpp
struct ExportPreset {
    std::string id;            // uuid
    std::string name;
    std::string container;     // mp4, webm, mov, mkv
    std::string videoCodec;    // h264, h265, vp9, av1
    int         width;
    int         height;
    int         fpsNum;
    int         fpsDen;
    int         videoBitrateKbps;
    std::string audioCodec;    // aac, opus, mp3
    int         audioBitrateKbps;
    int         sampleRate;
    std::string hdrMode;       // off, hdr10, hlg
};

class PresetManager {
public:
    bool Initialize(const std::filesystem::path& userPresetDir);
    void Shutdown();

    std::vector<ExportPreset> ListAll() const;
    const ExportPreset* FindById(const std::string& id) const;

    void Save(const ExportPreset& preset);     // upsert
    bool Remove(const std::string& id);

    bool ImportFromFile(const std::filesystem::path& path);
    bool ExportToFile  (const std::string& id, const std::filesystem::path& path);
};
```

## Dependencies

- `nlohmann/json` (already in `vcpkg.json`).
- `CommonTypes.h`, `Logging.h`, `Utils/FileSystem.h`.

## Threading

- All public methods are safe to call from the UI thread.
- File I/O is synchronous (presets are small — a few KB each).

## Error Handling

- `Save` / `Remove` log and return false on disk failure rather than throwing.
- `ImportFromFile` validates the JSON schema; malformed files return `false` and log a warning.

## Performance Budget

- `ListAll` must complete under 5 ms with up to 200 user presets.
