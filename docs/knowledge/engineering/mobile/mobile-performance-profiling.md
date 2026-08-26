# mobile-performance-profiling

**Issue:** Profiling and diagnosing performance problems in mobile apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Performance issues manifest as dropped frames (< 60 fps), high memory usage, or slow cold start. Profiling without the right tools leads to guessing rather than fixing actual bottlenecks.

## Pattern / Solution
**React Native — JS thread profiling:**
```bash
# In Metro dev server, press 'p' to start profiling
# Or use Hermes sampling profiler:
# React Native DevTools → Profiler tab → Record
```

**Flipper plugins:**
- **React DevTools**: component re-render tracking, state diffs
- **Network**: inspect API calls, response sizes
- **Hermes Debugger**: CPU sampling profiler
- **React Native Performance**: frame rate monitor

**iOS Instruments:**
- **Time Profiler**: CPU usage by function
- **Allocations**: memory allocations over time (find leaks)
- **Core Animation**: frame rendering, layer stats
- **Leaks**: retained cycle detection

```bash
# Launch with Instruments from command line
instruments -t "Time Profiler" -D /tmp/trace.trace \
  -w <device_udid> com.example.myapp
```

**Android — Android Studio Profiler:**
- CPU Profiler: method traces, system traces
- Memory Profiler: heap dumps, allocation tracking
- Network Profiler: timeline of requests

```bash
# Systrace for frame timing
python $ANDROID_HOME/platform-tools/systrace/systrace.py \
  --time=10 -o trace.html gfx view sched
```

**Key metrics to track:**
| Metric | Target |
|---|---|
| JS thread frame time | < 16.7 ms |
| Cold start (TTI) | < 2 s |
| Memory (midrange device) | < 150 MB heap |
| App bundle size | < 10 MB download |
| API response (P95) | < 500 ms |

## Gotchas
- Profile on a real device (midrange, not flagship); simulators are not representative
- `__DEV__` mode disables many RN optimizations; always profile release builds
- Memory leaks in RN often come from event listeners not removed in cleanup functions
- JavaScript performance in Hermes differs from V8/JSC; profile on target engine
- Android's "strict mode" (`StrictMode.setThreadPolicy`) catches disk/network on the main thread

## Related
- `react-native-performance-optimization.md`
- `react-native-hermes-engine.md`
- `mobile-crash-reporting.md`
