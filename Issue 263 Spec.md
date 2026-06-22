> Auto-generated from `Issue 263 Spec.md` in the docs repo.

> Auto-generated from `Issue 263 Spec.md` in the docs repo.

> Auto-generated from `Issue 263 Spec.md` in the docs repo.

> Auto-generated from `Issue 263 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_263_SPEC.md` in the docs repo.

---
title: "PluginHost Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# PluginHost Feature Spec

**Resolves:** #263, #264

This file documents the design for PluginHost, located at `src/Plugins/PluginHost.h` and `src/Plugins/PluginHost.cpp`.

## Goals

- Manage the lifecycle of all loaded OFX plug-ins: scan, load, hot-reload, unload.
- Maintain a directory of bundled plug-ins (under `<user-data>/Plug-ins/`) plus an opt-in system scan (under `/Library/Plug-Ins/OFX` on macOS, `%PROGRAMFILES%\Common Files\OFX\Plug-ins` on Windows).
- Surface a stable enumeration to the rest of the editor — `EffectRegistry` consumes this.
- Hot-reload: when a bundle file changes on disk (FSEvents / ReadDirectoryChangesW / inotify), unload and re-load without restarting the editor.

## Public API (sketch)

```cpp
class PluginHost {
public:
    static PluginHost& Get();

    bool Initialize();
    void Shutdown();

    // Discovery
    void ScanUserBundles  (const std::filesystem::path& userDir);
    void ScanSystemBundles();
    void RescanAll();

    // Query
    std::vector<std::string> LoadedPluginIds() const;
    const OpenFXPlugin*      FindPlugin(const std::string& id) const;

    // Hot-reload
    void SetHotReload(bool enabled);

    // Watcher events
    using EventCallback = std::function<void(const std::string& pluginId,
                                              const std::string& kind)>; // "loaded" / "unloaded" / "error"
    void OnEvent(EventCallback cb) { m_onEvent = std::move(cb); }

private:
    void WatchLoop();   // runs on a worker; emits events
};
```

## Dependencies

- `Plugins/OpenFXPlugin.h` (the per-bundle wrapper).
- `Utils/DynamicLibrary.h`, `Utils/FileSystem.h`, `Utils/DirWatcher.h` (per-platform FS event wrapper).
- `CommonTypes.h`, `Logging.h`.

## Threading

- `Initialize` / `Shutdown` are UI-thread.
- `Scan*` may be called from UI-thread but run a worker internally.
- The hot-reload watcher runs on a dedicated worker; events are marshalled to the UI thread.

## Error Handling

- A bundle that fails to load is logged and excluded from the registry (not removed from disk).
- Hot-reload of a broken bundle leaves the previous instance loaded (no disruption to in-progress effects).

## Performance Budget

- Initial scan of 50 bundles: under 1 s.
- Hot-reload latency (file change → callback): under 500 ms.
