> Auto-generated from `Issue 261 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_261_SPEC.md` in the docs repo.

---
title: "OpenFXPlugin Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# OpenFXPlugin Feature Spec

**Resolves:** #261, #262

This file documents the design for OpenFXPlugin, located at `src/Plugins/OpenFXPlugin.h` and `src/Plugins/OpenFXPlugin.cpp`.

## Goals

- Wrap a single OpenFX (OFX) plug-in binary into the editor's effect system.
- Conform to the OpenFX 1.5 spec (see https://openfx.readthedocs.io) for image-effect plug-ins.
- Provide the C-side `OfxGetPlugin`, `OfxGetNumberOfPlugins`, `OfxGetPluginInfo` entry points and the `OfxHost` descriptor.
- Load the plug-in as a dynamic library (`.ofx.bundle` on macOS, `.ofx` on Windows / Linux) and expose its effects via `EffectRegistry`.

## Public API (sketch)

```cpp
class OpenFXPlugin {
public:
    bool Load(const std::filesystem::path& bundlePath);
    void Unload();

    // OFX metadata
    std::string Name()        const;
    std::string Identifier()  const;
    std::string Version()     const;
    std::string FactoryScope() const;  // "image-effect", "transition", ...

    // Effects exposed by this plug-in
    struct EffectDescriptor {
        std::string id;
        std::string name;
        std::string group;
        std::string description;
    };
    std::vector<EffectDescriptor> ListEffects() const;

private:
    void* m_handle = nullptr;          // dlopen / LoadLibrary handle
    void* m_pluginEntry = nullptr;     // OfxPlugin*
    std::string m_path;
};
```

## Dependencies

- OFX C headers (`ofxCore.h`, `ofxImageEffect.h`) — header-only, no link.
- `Utils/DynamicLibrary.h` (platform-abstracted dlopen / LoadLibrary).
- `Engine/Effect.h` (the editor-side base class that wraps an OFX effect instance).

## Threading

- `Load` / `Unload` are UI-thread.
- The OFX descriptor queries in `ListEffects` are UI-thread; the actual `describeInContext` callback may run on a worker.

## Error Handling

- `Load` returns `false` if the bundle is malformed, the entry points are missing, or the OFX version is unsupported.
- Loaded plug-ins that fail `describe` are listed as "broken" in the registry with a warning icon, not removed.

## Security

- Plug-ins run in-process. The editor should display a one-time consent prompt the first time a third-party `.ofx` bundle is loaded.
- The plug-in's bundle path is hashed and stored; subsequent loads skip the consent prompt unless the hash changes.
