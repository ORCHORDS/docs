> Auto-generated from `Issue 284 Spec.md` in the docs repo.

> Auto-generated from `docs/engineering/ISSUE_284_SPEC.md` in the docs repo.

---
title: "AccessibilityPanel Feature Spec"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# AccessibilityPanel Feature Spec

**Resolves:** #284, #285

This file documents the design for AccessibilityPanel, located at `src/UI/AccessibilityPanel.h` and `src/UI/AccessibilityPanel.cpp`.

## Goals

- Provide a single in-app panel that exposes the editor's accessibility settings (per WCAG 2.1 AA).
- Surface the settings as keyboard-reachable controls (Tab order, focus rings, ARIA labels).
- Persist accessibility preferences to user settings; live-apply across the running editor.

## Public API (sketch)

```cpp
class AccessibilityPanel {
public:
    bool Initialize(ThemeManager& theme, UserSettings& settings);
    void Shutdown();

    void Render();                              // draws the panel
    bool HandleKey(const KeyEvent& e);         // returns true if consumed

    // Live-apply without re-render
    void SetHighContrast(bool on);
    void SetReduceMotion(bool on);
    void SetFontScale(float scale);             // 0.85 .. 1.5
    void SetColorblindMode(ColorblindMode mode); // none / protanopia / deuteranopia / tritanopia
};
```

## Dependencies

- `UI/ThemeManager.h`, `UserSettings.h`, `Window.h`.
- `Utils/JsonUtils.h` for persisted state.

## Threading

- All public methods run on the UI thread.
- The panel itself owns no worker threads.

## Accessibility Requirements

- All interactive controls must be reachable via Tab in document order.
- Visible focus ring on every focusable element (3 px solid, theme-driven color).
- All controls have an `accessible name` (via `AccessibleName` member) read by screen readers.
- Color is never the sole channel for state — high-contrast mode swaps the palette; patterns are available as a future enhancement.
- Respect the user's `prefers-reduced-motion` (Windows: `SystemParametersInfo(SPI_GETCLIENTAREAANIMATION)`).

## Performance Budget

- Panel render: 1 ms per frame.
- Setting changes take effect on the next frame; no full editor reload.
