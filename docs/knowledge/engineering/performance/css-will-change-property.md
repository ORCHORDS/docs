# css-will-change-property

**Issue:** Animations jank because the browser hasn't promoted elements to GPU layers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
will-change hints to the browser that an element will change, allowing it to create a compositor layer in advance. This enables GPU-accelerated rendering for animations.

## Pattern / Solution
1. Add before animation: will-change: transform, opacity.\n2. Remove after animation to free GPU memory.\n3. Apply only to elements that actually animate; do not apply globally.\n4. Use JavaScript to add/remove will-change dynamically.

## Gotchas
- will-change: transform on too many elements exhausts GPU memory and degrades performance.\n- Do not use will-change as a performance fix before profiling -- it adds overhead.\n- will-change: auto is a no-op; specify the actual property.

## Related
css-animation-gpu, css-performance-containment, layout-thrashing-prevention
