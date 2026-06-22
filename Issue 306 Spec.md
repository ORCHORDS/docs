> Auto-generated from `Issue 306 Spec.md` in the docs repo.

> Auto-generated from `Issue 306 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_306_SPEC.md` in the docs repo.

---
title: "UIOverlayRenderer Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# UIOverlayRenderer Feature Spec

**Resolves:** #306

This file documents the design for UIOverlayRenderer, located at `src/Engine/UIOverlayRenderer.cpp`.

## Goals

- Render editor chrome (timeline scrubber, transport controls, selection handles) on top of the preview viewport.
- Decouple the overlay drawing from the main render graph — run as a separate pass after `ViewportCompositor`.
- Support per-overlay theming (light / dark / high-contrast) read from user preferences.

## Public API (sketch)

```cpp
class UIOverlayRenderer {
public:
    bool Initialize(ShaderManager& shaders, RenderBackend& backend, ThemeManager& theme);
    void Shutdown();

    // Register an overlay widget. Widgets are drawn in registration order.
    void RegisterOverlay(std::unique_ptr<OverlayWidget> widget);
    void UnregisterOverlay(const std::string& id);

    // Draw all overlays onto the supplied render target.
    void Render(ID3D12GraphicsCommandList* cmdList,
                D3D12_GPU_DESCRIPTOR_HANDLE targetRTV);
};
```

## Dependencies

- `Engine/ShaderManager.h`, `Engine/RenderBackend.h`, `UI/ThemeManager.h`, `UI/OverlayWidget.h`.
- `CommonTypes.h`.

## Threading

- `RegisterOverlay` / `UnregisterOverlay` are setup-thread only.
- `Render` runs on the render thread.

## Performance Budget

- Overlay rendering: 1 ms per frame with up to 16 active widgets.
- Text rendering uses a glyph atlas cached at `Initialize`; do not rebuild per frame.
