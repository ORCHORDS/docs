> Auto-generated from `Issue 300 Spec.md` in the docs repo.

> Auto-generated from `Issue 300 Spec.md` in the docs repo.

> Auto-generated from `Issue 300 Spec.md` in the docs repo.

> Auto-generated from `Issue 300 Spec.md` in the docs repo.

> Auto-generated from `Issue 300 Spec.md` in the docs repo.

> Auto-generated from `Issue 300 Spec.md` in the docs repo.

> Auto-generated from `Issue 300 Spec.md` in the docs repo.

> Auto-generated from `Issue 300 Spec.md` in the docs repo.

> Auto-generated from `Issue 300 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_300_SPEC.md` in the docs repo.

---
title: "EffectChain Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# EffectChain Feature Spec

**Resolves:** #300, #301

This file documents the design for EffectChain, located at `src/Engine/EffectChain.h` and `src/Engine/EffectChain.cpp`.

## Goals

- Compose an ordered list of `Effect` instances (color grade, blur, sharpen, LUT, etc.) and apply them sequentially to a render target.
- Each effect reads a source texture and writes to a ping-pong target to avoid read/write hazards.
- The chain is a node in `RenderGraph` and runs after primary compositing.

## Public API (sketch)

```cpp
class EffectChain {
public:
    bool Initialize(ShaderManager& shaders, RenderBackend& backend, RenderGraph& graph);
    void Shutdown();

    // Append an effect. Effects run in the order they were appended.
    void AppendEffect(std::unique_ptr<Effect> effect);

    // Apply all effects to the given input texture, writing the final result to outputRTV.
    void Apply(ID3D12GraphicsCommandList* cmdList,
               D3D12_GPU_DESCRIPTOR_HANDLE inputSRV,
               D3D12_GPU_DESCRIPTOR_HANDLE outputRTV);

    size_t NumEffects() const { return m_effects.size(); }
    void   Clear()           { m_effects.clear(); }
};
```

## Dependencies

- `Engine/Effect.h` (the abstract effect base class — see `docs/graphics/SHADER_SPEC.md` for the EffectRegistry pattern).
- `Engine/ShaderManager.h`, `Engine/RenderBackend.h`, `Engine/RenderGraph.h`.
- `Utils/JsonUtils.h` for serialising the chain to project files.

## Threading

- `AppendEffect` / `Clear` are setup-thread only.
- `Apply` runs on the render thread.

## Error Handling

- `Initialize` returns `false` if any effect's shader fails to compile. The chain is then unusable.
- `Apply` is a no-op if the chain is empty.

## Performance Budget

- Each effect's pass must complete under 0.5 ms at 1080p.
- The chain's total budget per frame: `NumEffects() * 0.5 ms + 1 ms` overhead.
- Use the render graph's transient resource pool — do not allocate per-frame render targets.
