# react-profiler

**Issue:** React re-renders are slow and hard to attribute to specific components
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
React DevTools Profiler records component render times and reasons. Essential for identifying performance bottlenecks in React applications.

## Pattern / Solution
1. Open React DevTools > Profiler > Record > interact > Stop.\n2. Look for components with high render duration or many rendered times.\n3. Check Why did this render? to see which prop or state triggered the re-render.\n4. Use the Flamegraph view to find cascading re-renders.\n5. Wrap the Profiler component around critical sections in production for RUM data.

## Gotchas
- Profiler only shows commit (DOM update) time; also check the Chrome Performance panel for full thread cost.\n- Development builds are significantly slower than production; profile production builds for accurate numbers.\n- The onRender callback of Profiler has overhead; sample rather than always-on in production.

## Related
react-render-optimization, react-memo-patterns, chrome-devtools-performance
