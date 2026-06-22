> Auto-generated from `Issue 290 Spec.md` in the docs repo.

> Auto-generated from `Issue 290 Spec.md` in the docs repo.

> Auto-generated from `Issue 290 Spec.md` in the docs repo.

> Auto-generated from `Issue 290 Spec.md` in the docs repo.

> Auto-generated from `Issue 290 Spec.md` in the docs repo.

> Auto-generated from `Issue 290 Spec.md` in the docs repo.

> Auto-generated from `Issue 290 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_290_SPEC.md` in the docs repo.

---
title: "ClipProcessor Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# ClipProcessor Feature Spec

**Resolves:** #290, #291

This file documents the design for ClipProcessor, located at `src/Timeline/ClipProcessor.h` and `src/Timeline/ClipProcessor.cpp`.

## Goals

- Process a single timeline clip: trim, split, ripple, slip, slide, roll, and speed change.
- Apply operations to the underlying `Clip` data without mutating the source media.
- Notify the timeline + preview when a clip's range changes so the preview can re-seek.

## Public API (sketch)

```cpp
struct ClipRange {
    int64_t startMs;       // start on the timeline
    int64_t endMs;         // end on the timeline
    int64_t sourceInMs;    // in-point in the source media
    int64_t sourceOutMs;   // out-point in the source media
    double  speed = 1.0;   // playback rate (0.25 .. 4.0)
};

class ClipProcessor {
public:
    bool Initialize(TrackManager& tracks);
    void Shutdown();

    // Returns the new clip id (or empty string on failure).
    std::string Split(const std::string& clipId, int64_t atMs);

    bool Trim  (const std::string& clipId, int64_t newStartMs, int64_t newEndMs);
    bool Ripple(const std::string& clipId, int64_t deltaMs);   // shifts neighbours
    bool Slip  (const std::string& clipId, int64_t deltaMs);   // shifts source in/out
    bool Slide (const std::string& clipId, int64_t deltaMs);   // shifts neighbours' positions
    bool SetSpeed(const std::string& clipId, double speed);

    const ClipRange* GetRange(const std::string& clipId) const;

    // History integration: every mutation emits a command the UndoStack can capture.
    std::unique_ptr<Command> LastCommand() const { return m_lastCmd; }
};
```

## Dependencies

- `Timeline/TrackManager.h`, `Timeline/Clip.h`.
- `CommonTypes.h`, `Utils/Uuid.h`, `Core/UndoStack.h`.

## Threading

- All mutation methods are UI-thread only.
- Range getters are read-only and safe from any thread (returned pointer is stable until the next mutation on that clip).

## Error Handling

- Returns empty string / false on illegal operations (negative duration, clip not found, speed out of range).
- Errors are logged via `Logging.h` at `warn` level.

## Performance Budget

- Single-clip operation: under 0.1 ms.
- A 1,000-clip ripple must complete under 50 ms.
