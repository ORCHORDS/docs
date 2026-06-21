# ShortcutManager Feature Spec

**Resolves:** #83

Location: ``src/Core/ShortcutManager.h``

## Goals

- Implement the user-facing behaviour from issue #83.
- Small public surface, framework-agnostic.

## Public API (sketch)

```cpp
class ShortcutManager {
public:
    bool Initialize();
    void Shutdown();
};
```

## Dependencies

- `CommonTypes.h`, `Logging.h`.
