# RenderPipeline Feature Spec

**Resolves:** #79

Location: ``src/Export/RenderPipeline.h``

## Goals

- Implement the user-facing behaviour from issue #79.
- Small public surface, framework-agnostic.

## Public API (sketch)

```cpp
class RenderPipeline {
public:
    bool Initialize();
    void Shutdown();
};
```

## Dependencies

- `CommonTypes.h`, `Logging.h`.
