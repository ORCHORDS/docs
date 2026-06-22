> Auto-generated from `Api Reference.md` in the docs repo.

> Auto-generated from `Api Reference.md` in the docs repo.

> Auto-generated from `docs/dev/API_REFERENCE.md` in the docs repo.

---
title: "Beetle Studio API Reference"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Beetle Studio API Reference

## Engine API

### CodecPipeline
Core video decode/encode interface wrapping FFmpeg.

```cpp
auto codec = beetle::engine::CodecPipeline();
codec.open_input("video.mp4");
auto frame = codec.decode_next_frame();
```

### Renderer
Graphics backend abstraction (DirectX 12 / Vulkan).

```cpp
auto renderer = beetle::engine::Renderer::create(GraphicsBackend::Auto);
renderer->initialize(hwnd, config);
```

### Timeline
Multi-track timeline data structure with undo/redo.

```cpp
auto timeline = beetle::engine::Timeline();
auto& track = timeline.add_video_track("V1");
timeline.add_clip(track.id, clip);
```

### EffectsPipeline
GPU-accelerated effect chain with parameter control.

```cpp
auto fx = beetle::engine::EffectsPipeline();
auto id = fx.add_effect(BuiltinEffect::GaussianBlur);
fx.set_parameter(id, "radius", 5.0f);
```

### AudioEngine
Audio playback with WASAPI/ASIO and VST plugin support.

```cpp
auto audio = beetle::audio::AudioEngine();
audio.initialize({.sample_rate = 48000, .buffer_size = 256});
audio.play();
```

## Plugin API (OpenFX)
See `src/Plugins/OpenFXHost.h` for the plugin host interface.
Plugins are loaded from `.ofx` bundles in the plugins directory.