# react-portal-patterns

**Issue:** Modals and tooltips clip behind overflow:hidden or stacking context ancestors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A dropdown inside a table cell clips because the table has overflow:hidden; z-index wars result.

## Pattern / Solution
```tsx
import { createPortal } from 'react-dom';

function Modal({ children, onClose }) {
  return createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        {children}
      </div>
    </div>,
    document.body
  );
}

useEffect(() => {
  const first = ref.current?.querySelector('button, [href], input');
  first?.focus();
}, []);
```

## Gotchas
- Events bubble through the React tree, not the DOM tree
- SSR: document is undefined server-side; guard with typeof window check
- Manage focus trap and aria-modal for accessibility

## Related
- `html-accessibility-aria.md`
- `react-ref-forwarding.md`
