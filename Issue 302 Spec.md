> Auto-generated from `Issue 302 Spec.md` in the docs repo.

> Auto-generated from `Issue 302 Spec.md` in the docs repo.

> Auto-generated from `Issue 302 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_302_SPEC.md` in the docs repo.

---
title: "Compositor Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Compositor Feature Spec

**Resolves:** #302

This file documents the design for Compositor, located at `src/Engine/Compositor.cpp`.

## Goals

- Combine multiple layers (video frames, overlays, UI composited onto the playback texture) into a single output render target for presentation.
- Support per-layer opacity, blend mode (normal / additive / multiply), and a simple z-order stack.
- Run as a single pass inside the render graph after the EffectChain.

## Public API (sketch)

```cpp
class Compositor {
public:
    bool Initialize(ShaderManager& shaders, RenderBackend& backend);
    void Shutdown();

    void AddLayer(Layer&& layer);
    void ClearLayers();

    void Composite(ID3D12GraphicsCommandList* cmdList,
                   D3D12_GPU_DESCRIPTOR_HANDLE outputRTV);

private:
    std::vector<Layer> m_layers;
    ShaderManager&     m_shaders;
    RenderBackend&     m_backend;
};
```

## Dependencies

- `Engine/ShaderManager.h`, `Engine/RenderBackend.h`, `Engine/Effect.h`.
- `CommonTypes.h` for `BlendMode`, `Layer`.

## Threading

- `AddLayer` / `ClearLayers` are setup-thread only.
- `Composite` runs on the render thread.

## Performance Budget

- Layered composite pass: 2 ms at 4K with up to 8 layers.
- Layers beyond 8 should be flagged with a `log_warn` and rendered with a fallback (skip).
