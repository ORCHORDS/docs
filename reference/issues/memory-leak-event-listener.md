# memory-leak-event-listener

**Issue:** Adding event listeners without removing them causes memory leaks that grow with each request or component mount
**Date:** 2026-08-11
**Status:** documented

## Symptom
Node.js emits `MaxListenersExceededWarning: Possible EventEmitter memory leak detected. 11 message listeners added`. Process memory grows steadily over hours without leveling off.

## Root cause
Every call to `emitter.on('event', handler)` adds a listener to an internal array. If the component/module that adds the listener is torn down without calling `emitter.off('event', handler)` or `emitter.removeAllListeners()`, the listener (and its closure's references) remain in memory, preventing GC.

## Fix
```ts
// Always pair add with remove
const handler = (data: Data) => process(data);
emitter.on('data', handler);

// On cleanup
emitter.off('data', handler);

// React useEffect pattern
useEffect(() => {
  window.addEventListener('resize', onResize);
  return () => window.removeEventListener('resize', onResize);
}, []);
```

## Detection
```
node --trace-warnings server.js
```
Look for `MaxListenersExceededWarning`. Also: `grep -rn "\.on('" src/ | grep -v "\.off\|removeListener\|removeAllListeners"`.

## Related
- `closure-loop-variable-capture.md`
