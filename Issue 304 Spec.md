> Auto-generated from `Issue 304 Spec.md` in the docs repo.

> Auto-generated from `Issue 304 Spec.md` in the docs repo.

> Auto-generated from `Issue 304 Spec.md` in the docs repo.

> Auto-generated from `Issue 304 Spec.md` in the docs repo.

> Auto-generated from `Issue 304 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_304_SPEC.md` in the docs repo.

---
title: "ViewportCompositor Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# ViewportCompositor Feature Spec

**Resolves:** #304

This file documents the design for ViewportCompositor, located at `src/Engine/ViewportCompositor.h` and `src/Engine/ViewportCompositor.cpp`.

## Goals

- Composite the final preview frame into the editor's viewport (HWND-backed swap-chain surface).
- Apply letterboxing / pillarboxing when the source aspect ratio differs from the viewport.
- Support on-screen HUD overlays (safe-zone guides, rulers, timecode).

## Public API (sketch)

```cpp
class ViewportCompositor {
public:
    bool Initialize(Window& window, ShaderManager& shaders, RenderBackend& backend);
    void Shutdown();

    void SetViewportSize(uint32_t width, uint32_t height);
    void SetSourceSize(uint32_t width, uint32_t height);

    void Present(ID3D12GraphicsCommandList* cmdList,
                 D3D12_GPU_DESCRIPTOR_HANDLE frameSRV);

    // Overlay control
    void ShowOverlay(OverlayKind kind, bool show);
    void SetOverlayOpacity(OverlayKind kind, float alpha);

private:
    Window&           m_window;
    ShaderManager&    m_shaders;
    RenderBackend&    m_backend;
    ViewportState     m_state;
};
```

## Dependencies

- `Window.h`, `Engine/ShaderManager.h`, `Engine/RenderBackend.h`.
- D3D12 swap-chain APIs.

## Threading

- All public methods must be safe to call from the render thread.
- Window-resize callbacks should marshal to the render thread before mutating `m_state`.

## Performance Budget

- `Present` is on the render hot path; must complete under 0.5 ms.
- Overlay rendering uses a separate shader permutation so it can be toggled without recompiling the main composite shader.
