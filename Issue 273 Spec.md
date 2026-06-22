> Auto-generated from `docs/engineering/ISSUE_273_SPEC.md` in the docs repo.

---
title: "Whisper Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Whisper Feature Spec

**Resolves:** #273, #274

This file documents the design for Whisper, located at `src/AI/Whisper.h` and `src/AI/Whisper.cpp`.

## Goals

- Wrap the `whisper.cpp` library (https://github.com/ggml-org/whisper.cpp) for local speech-to-text transcription of project audio.
- Provide a small, idiomatic C++ API that hides the C-style `whisper_context` / `whisper_full` calls.
- Stream transcripts back to the caller via a callback so the UI can render captions incrementally.
- Run inference on CPU by default; opt into GPU acceleration (CUDA / Metal / Vulkan) at `Initialize` time.

## Public API (sketch)

```cpp
class Whisper {
public:
    struct Config {
        std::string modelPath;          // e.g. "models/ggml-base.en.bin"
        int         nThreads   = 4;     // CPU thread count
        bool        useGpu     = false; // opt-in GPU acceleration
        std::string language   = "en";  // ISO 639-1
    };

    struct Segment {
        int64_t startMs;
        int64_t endMs;
        std::string text;
    };

    using SegmentCallback = std::function<void(const Segment&)>;

    bool Initialize(const Config& cfg);
    void Shutdown();

    // Transcribe a 16 kHz mono PCM buffer. Segments are reported incrementally.
    void Transcribe(const std::vector<float>& pcm16k,
                    SegmentCallback onSegment);

    bool IsReady() const { return m_ctx != nullptr; }
};
```

## Dependencies

- Third-party: `whisper.cpp` (link statically via CMake target `Whisper::whisper`).
- `CommonTypes.h`, `Logging.h`.
- `<functional>`, `<vector>`, `<string>`.

## Threading

- A single Whisper instance may only run one `Transcribe` at a time. Concurrent calls return an error via the callback (`Segment{0,0,""}` + a log error) rather than throwing.
- Long-running `Transcribe` calls dispatch to an internal worker thread; the callback fires on that worker. The caller is responsible for marshalling back to the UI thread if needed.

## Error Handling

- `Initialize` returns `false` if the model file is missing or fails to load.
- `Transcribe` never throws. Errors are surfaced via the logging facility and an empty-segments callback at the end of the run.

## Performance Budget

- A 10-second clip at the `base.en` model must transcribe in under 2× realtime on a modern desktop CPU (8 cores).
- GPU mode (CUDA) target: under 0.3× realtime.
