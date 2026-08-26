# react-component-composition

**Issue:** How to structure components using composition instead of inheritance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Components become tightly coupled or duplicated when logic is embedded in deep hierarchies rather than composed from smaller, focused pieces.

## Pattern / Solution
```tsx
// Prefer composition via children and render props
function Card({ header, children, footer }: CardProps) {
  return (
    <div className="card">
      <div className="card-header">{header}</div>
      <div className="card-body">{children}</div>
      {footer && <div className="card-footer">{footer}</div>}
    </div>
  )
}

// Usage
<Card header={<Title />} footer={<Actions />}>
  <Content />
</Card>
```

## Gotchas
- Avoid prop drilling more than 2 levels — use context or state lifting instead
- Don't over-compose; each split should have a clear reason
- Slots via named children props are more explicit than arbitrary children

## Related
- `react-compound-components.md`
- `react-render-props-pattern.md`
