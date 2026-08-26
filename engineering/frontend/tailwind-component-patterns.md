# tailwind-component-patterns

**Issue:** Tailwind class lists grow unmanageable; components become hard to customise
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A Button with 25 utility classes is hard to read and impossible for consumers to override selectively.

## Pattern / Solution
```tsx
import { cva, type VariantProps } from 'class-variance-authority';
import { twMerge } from 'tailwind-merge';

const button = cva('inline-flex items-center rounded font-medium', {
  variants: {
    variant: {
      primary: 'bg-blue-600 text-white hover:bg-blue-700',
      secondary: 'bg-gray-100 text-gray-900 hover:bg-gray-200',
    },
    size: {
      sm: 'px-3 py-1.5 text-sm',
      md: 'px-4 py-2 text-base',
    },
  },
  defaultVariants: { variant: 'primary', size: 'md' },
});

function Button({ variant, size, className, ...props }: VariantProps<typeof button> & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={twMerge(button({ variant, size }), className)} {...props} />;
}
```

## Gotchas
- tailwind-merge resolves class conflicts (e.g. p-2 and p-4 on same element)
- cva handles variant logic cleanly without conditional string concatenation
- Add safelist in tailwind.config for dynamically generated class names

## Related
- `tailwind-dark-mode.md`
- `tailwind-responsive-design.md`
