> Auto-generated from `Issue 298 Spec.md` in the docs repo.

> Auto-generated from `Issue 298 Spec.md` in the docs repo.

> Auto-generated from `Issue 298 Spec.md` in the docs repo.

> Auto-generated from `Issue 298 Spec.md` in the docs repo.

> Auto-generated from `Issue 298 Spec.md` in the docs repo.

> Auto-generated from `Issue 298 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_298_SPEC.md` in the docs repo.

---
title: "ColorPipeline Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# ColorPipeline Feature Spec

**Resolves:** #298, #299

This file documents the design for ColorPipeline, located at `src/Engine/ColorPipeline.h` and `src/Engine/ColorPipeline.cpp`.

## Goals

- Apply color management (sRGB ↔ linear, REC.709 ↔ REC.2020, HDR PQ) to all rendered frames.
- Provide per-pass color-space conversion via a small set of shader-driven stages.
- Honor the project-wide `ColorManagement` settings configured in user preferences.

## Public API (sketch)

```cpp
class ColorPipeline {
public:
    bool Initialize(ShaderManager& shaders, RenderBackend& backend);
    void Shutdown();

    // Configure the conversion stages for a given render target.
    void Configure(ColorSpace input, ColorSpace output, HdrMode hdr);

    // Apply the pipeline to a render target. Issues draw calls on the supplied command list.
    void Apply(ID3D12GraphicsCommandList* cmdList,
               D3D12_GPU_DESCRIPTOR_HANDLE inputSRV,
               D3D12_GPU_DESCRIPTOR_HANDLE outputRTV);

private:
    ShaderManager&  m_shaders;
    RenderBackend&  m_backend;
    ColorSpace      m_input  = ColorSpace::SRgb;
    ColorSpace      m_output = ColorSpace::SRgb;
    HdrMode         m_hdr    = HdrMode::Off;
};
```

## Dependencies

- `Engine/ShaderManager.h`, `Engine/RenderBackend.h`, `CommonTypes.h` (for `ColorSpace`, `HdrMode`).
- D3D12 command-list APIs.

## Threading

- `Configure` is setup-thread only.
- `Apply` runs on the render thread.

## Performance Budget

- Hot-path: 1 ms per frame at 4K (single conversion pass).
- No heap allocation in `Apply` — pre-allocate the PSO at `Initialize` and rebind parameters per call.
