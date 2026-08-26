# typescript-discriminated-unions-ui

**Issue:** Components with mutually exclusive prop combinations need type narrowing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An Alert component accepts either message or children but not both; TypeScript accepts any combination.

## Pattern / Solution
```tsx
type AlertProps =
  | { variant: 'text'; message: string; children?: never }
  | { variant: 'node'; children: React.ReactNode; message?: never };

function Alert(props: AlertProps) {
  if (props.variant === 'text') {
    return <div>{props.message}</div>; // message is string here
  }
  return <div>{props.children}</div>; // children is ReactNode here
}

// Button with vs without href
type ButtonProps =
  | ({ as?: 'button' } & React.ButtonHTMLAttributes<HTMLButtonElement>)
  | ({ as: 'a' } & React.AnchorHTMLAttributes<HTMLAnchorElement>);
```

## Gotchas
- never type on unused branch members enforces mutual exclusivity
- Discriminant property must be a literal type, not a primitive
- Exhaustive checks: add a default that asserts never for complete coverage

## Related
- `typescript-generic-components.md`
- `typescript-satisfies-operator.md`
