> Auto-generated from `Issue 281 Spec.md` in the docs repo.

> Auto-generated from `Issue 281 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_281_SPEC.md` in the docs repo.

---
title: "OpenFXPluginHost Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# OpenFXPluginHost Feature Spec

**Resolves:** #281, #282

This file documents the design for OpenFXPluginHost, located at `src/Plugins/OpenFXPluginHost.h` and `src/Plugins/OpenFXPluginHost.cpp`.

## Goals

- Provide the OFX host descriptor (`OfxHost`) that loaded plug-ins call back into.
- Implement the host-side `host` suite (memory, threading, image-effect, parameter suites).
- Bridge OFX's plug-in lifecycle (`createInstance`, `destroyInstance`, `getInstanceEffectDescriptor`) to the editor's `Effect` base class.
- Manage per-instance GPU resources (D3D12 textures) for OFX effects that opt into GPU rendering.

## Public API (sketch)

```cpp
class OpenFXPluginHost {
public:
    static OpenFXPluginHost& Get();

    bool Initialize(RenderBackend& backend);
    void Shutdown();

    // Per-instance lifecycle (called by OpenFXPlugin when creating an effect instance).
    void* CreateInstance (const OpenFXPlugin& plugin, const std::string& effectId);
    void  DestroyInstance(void* instance);

    // Per-frame render dispatch.
    void RenderInstance (void* instance,
                         ID3D12GraphicsCommandList* cmdList,
                         const OfxRenderArgs& args);

private:
    RenderBackend& m_backend;
    OfxHost        m_hostDescriptor;
};
```

## Dependencies

- OFX C headers (`ofxCore.h`, `ofxImageEffect.h`, `ofxGPU.h` if GPU effects are supported).
- `Plugins/OpenFXPlugin.h`, `Engine/RenderBackend.h`, `Engine/Effect.h`.
- D3D12 (`<d3d12.h>`) for GPU effect resources.

## Threading

- All public methods are UI-thread.
- The OFX `render` action runs on the render thread inside `RenderInstance`.

## Error Handling

- An OFX effect that fails `createInstance` is logged and excluded from the registry (the bundle stays loaded for other effects).
- `render` failures from a plug-in are caught; the effect slot is rendered as a transparent checkerboard pattern.

## Security

- Per-instance memory is tracked; an effect that allocates >256 MB via the host's `memoryAlloc` suite is flagged and killed.
- No host-provided thread or async suite is exposed in v2.0 (return `kOfxStatErrUnsupported` from those suite entries).
