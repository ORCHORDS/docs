# browser-mutation-observer

**Issue:** Detecting DOM changes from third-party code without polling
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A chat widget needs to react when a third-party script injects a notification badge into the DOM.

## Pattern / Solution
```ts
const observer = new MutationObserver((mutations) => {
  for (const mutation of mutations) {
    if (mutation.type === 'childList') {
      mutation.addedNodes.forEach(node => {
        if (node instanceof HTMLElement && node.matches('.badge')) {
          handleBadge(node);
        }
      });
    }
  }
});

observer.observe(document.body, {
  childList: true,
  subtree: true,
  attributes: true,
  attributeFilter: ['class', 'data-state'],
});

observer.disconnect(); // always cleanup
```

## Gotchas
- subtree: true observes all descendants; can be expensive on large DOMs
- Mutations are batched and delivered as a microtask
- Modifying observed nodes inside the callback can cause infinite loops

## Related
- `browser-intersection-observer.md`
- `browser-resize-observer.md`
