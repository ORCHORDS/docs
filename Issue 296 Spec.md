> Auto-generated from `Issue 296 Spec.md` in the docs repo.

> Auto-generated from `Issue 296 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_296_SPEC.md` in the docs repo.

---
title: "RenderGraph Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# RenderGraph Feature Spec

**Resolves:** #296

This file documents the design for RenderGraph, located at `src/Engine/RenderGraph.h` and `src/Engine/RenderGraph.cpp`.

## Goals

- Provide a DAG-based render graph that sequences GPU passes for the video editor's preview and export pipelines.
- Allow passes (EffectChain, ViewportCompositor, ColorPipeline, etc.) to declare resource dependencies (input textures, output render targets) without manually managing transitions.
- Execute the graph on the D3D12 command queue with a topological sort and a transition-resource barrier pass.

## Public API (sketch)

```cpp
class RenderGraph {
public:
    bool Initialize(RenderBackend& backend, ShaderManager& shaders, Window& window, ColorManagement& colors);
    void Shutdown();

    void AddNode(const std::string& name,
                 const D3D12_RESOURCE_DESC& resourceDesc,
                 D3D12_RESOURCE_STATES initialState);
    void AddEdge(const std::string& from, const std::string& to);

    void Compile();   // topological sort
    void Execute();   // barrier transitions + per-pass dispatch

    RenderGraphNode* GetNode(const std::string& name);
};
```

## Dependencies

- `Engine/RenderBackend.h`, `Graphics/ShaderManager.h`, `Window.h`, `ColorManagement.h`.
- D3D12 (`<d3d12.h>`, `<dxgi1_6.h>`), `<wrl/client.h>`, `<DirectXMath.h>`.
- STL containers: `std::unordered_map`, `std::vector`, `std::mutex`.

## Threading

- `AddNode` / `AddEdge` / `Compile` must be called from a single setup thread.
- `Execute` may run on the render thread.
- Internal `m_mutex` protects the node/edge maps.

## Performance Budget

- `Compile()` on a graph with up to 64 nodes must complete under 5 ms.
- `Execute()` dispatches each pass; per-pass cost is the pass's own command-list recording.
- Resource barriers are batched into a single `ResourceBarrier` call per transition group.
