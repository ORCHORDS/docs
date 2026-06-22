> Auto-generated from `Module Map.md` in the docs repo.

> Auto-generated from `Module Map.md` in the docs repo.

> Auto-generated from `Module Map.md` in the docs repo.

> Auto-generated from `Module Map.md` in the docs repo.

> Auto-generated from `Module Map.md` in the docs repo.

> Auto-generated from `Module Map.md` in the docs repo.

> Auto-generated from `docs/architecture/MODULE_MAP.md` in the docs repo.

---
title: "Module Map - Issue to Files"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Module Map - Issue to Files

This document maps each open issue to the source files it expects to land in.
Use this when scoping work and reviewing PRs.

| Issue | Title | Owner | Target files |
|-------|-------|-------|--------------|
| #72 | Firebase Auth (Google Sign-In) | maya.rodriguez | `src/backend/FirebaseAuth.{h,cpp}` |
| #73 | Firestore token system | maya.rodriguez | `src/backend/TokenSystem.{h,cpp}` |
| #74 | File I/O | amanda.clark | `src/project/ProjectFile.{h,cpp}` (uses `docs/architecture/BSP_FORMAT.md`) |
| #75 | Timeline data model | emma.thompson | `src/timeline/{TimelineModel,Track,Clip}.{h,cpp}` |
| #76 | Video preview/playback | james.park | `src/preview/PreviewPanel.{h,cpp}`, `src/codec/FFmpegDecoder.{h,cpp}` |
| #77 | Audio engine | ryan.foster | `src/audio/AudioEngine.{h,cpp}` |
| #78 | Effects pipeline | daniel.kim | `src/effects/Effect.{h,cpp}`, `src/effects/EffectGraph.{h,cpp}` |
| #79 | Render/export pipeline | sophie.williams | `src/render/Exporter.{h,cpp}` |
| #80 | Properties panel | alex.chen | `src/ui/PropertiesPanel.{h,cpp}` |
| #82 | Undo/redo | emma.thompson | `src/core/UndoStack.{h,cpp}` |
| #84 | Color picker | alex.chen | `src/ui/ColorPicker.{h,cpp}` |

## Cross-cutting foundation (already landed)

- `cmake/CompilerFlags.cmake`, `cmake/Dependencies.cmake`, `cmake/Platform.cmake`
- `vcpkg.json` (Qt6, ffmpeg, vulkan, nlohmann-json, spdlog, fmt)
- `docs/architecture/BSP_FORMAT.md`

## Cross-cutting foundation (TODO before any of #72-#84 can compile end-to-end)

- `include/beetle/core/{Types,Log,Result}.h` — common types & error model
- `src/main.cpp` — application entrypoint wiring the subsystems
- A "scaffolding" sub-target that builds only the headers + empty .cpp so CI
  can validate dependencies before any feature work lands.

## Dependency graph

```
                +-- #75 timeline  +-- #76 preview
                |                 +-- #82 undo/redo (operates on timeline)
                v
            #74 file I/O     +-- #77 audio  (reads timeline tracks)
                |             +-- #78 effects (operates on preview frames)
                v             +-- #79 render (reads timeline + effects)
            #84 color picker  +-- #80 properties panel (binds to selections)
                                              ^
                                              |
                                         #73 tokens (backend)
                                         #72 Firebase Auth (backend)
```

## Sequencing recommendation

1. Land `include/beetle/core/` foundation headers first (shared by all).
2. Land #75 timeline data model (no UI, easy to review).
3. Land #74 file I/O using the BSP spec (depends on #75 for type defs).
4. From there, parallelize #76/#77/#78/#82/#79/#80/#84.
5. Backend (#72/#73) can land in parallel from step 1.