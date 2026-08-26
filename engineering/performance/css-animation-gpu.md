# css-animation-gpu

**Issue:** CSS animations cause layout and paint instead of running on the compositor
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Animations using layout-triggering properties run on the main thread. Animating only transform and opacity runs on the compositor thread without touching the main thread.

## Pattern / Solution
1. Replace left/top animations with transform: translate().\n2. Replace width/height animations with transform: scale().\n3. Replace background-color fade with opacity on an overlay.\n4. Verify in Chrome DevTools Layers panel that animated elements are promoted.\n5. Use CSS @keyframes over JS setInterval for smoother compositor-driven animation.

## Gotchas
- Some browsers promote elements with opacity < 1 to a layer even without will-change.\n- filter animations (blur, brightness) run on the GPU but are still expensive.\n- Too many GPU layers consume VRAM; monitor memory usage on low-end devices.

## Related
css-will-change-property, requestanimationframe-patterns, cls-prevention
