# ShadCN UI Component Library Integration Patterns

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You want a consistent, accessible component library for a React/Next.js project without the
overhead of a traditional npm-installed component package. ShadCN UI offers components that live
*in your codebase*, fully customisable, built on Radix UI primitives and styled with Tailwind CSS.
Common pain points: understanding the copy-not-install model, wiring up the CLI in a monorepo,
theming across products, and keeping components in sync after upstream changes.

## Context

ShadCN UI is not an npm package in the traditional sense. Instead, the `shadcn` CLI scaffolds
source files directly into your project under `components/ui/`. You own the code. There is no
black-box abstraction between your design system and the components.

The component layer is:

```
Radix UI primitives (headless, fully accessible)
  ↓
Class Variance Authority (CVA) – manages variant classes
  ↓
Tailwind CSS – visual styling
  ↓
Your project's component files (you own these)
```

As of 2025, ShadCN supports React 18/19, Next.js 14/15 (App Router), Vite, Remix, Astro, and
Tanstack Start. The CLI auto-detects the framework.

## Installation and Initialisation

```bash
npx shadcn@latest init
```

The init wizard asks:

1. **Style**: New York or Default. New York uses tighter spacing and rounded-md everywhere; Default
   is slightly looser. This is cosmetic — it sets the base CSS variables.
2. **Base colour**: Slate, Zinc, Stone, Gray, Neutral. Sets `--background`, `--foreground`, etc.
3. **CSS variables**: Yes (recommended). Components reference `var(--primary)` rather than
   hardcoded Tailwind colour classes, so one `@theme` block controls the whole UI.

Init writes:
- `components.json` — project config consumed by future `shadcn add` calls
- `src/app/globals.css` (or your CSS entry) — theme variables block
- `src/lib/utils.ts` — the `cn()` helper (thin wrapper over `clsx` + `tailwind-merge`)
- `components/ui/` — initially empty, populated by `shadcn add`

## components.json

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/app/globals.css",
    "baseColor": "zinc",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }
}
```

`rsc: true` tells the CLI to generate components without `"use client"` where possible, defaulting
to React Server Components.

## Adding Components

```bash
npx shadcn@latest add button
npx shadcn@latest add dialog sheet dropdown-menu
npx shadcn@latest add table data-table  # data-table is a compound component
```

Each command writes files to `components/ui/`. Some components bring peer dependencies:

| Component | Peer dependency installed |
|---|---|
| `dialog` | `@radix-ui/react-dialog` |
| `dropdown-menu` | `@radix-ui/react-dropdown-menu` |
| `toast` (Sonner) | `sonner` |
| `chart` | `recharts` |
| `date-picker` | `react-day-picker`, `date-fns` |

## Theming with CSS Variables

The CSS-variables approach maps design tokens to Tailwind utility classes:

```css
/* globals.css – light theme */
:root {
  --background: 0 0% 100%;
  --foreground: 240 10% 3.9%;
  --primary: 240 5.9% 10%;
  --primary-foreground: 0 0% 98%;
  --muted: 240 4.8% 95.9%;
  --muted-foreground: 240 3.8% 46.1%;
  --border: 240 5.9% 90%;
  --radius: 0.5rem;
}

.dark {
  --background: 240 10% 3.9%;
  --foreground: 0 0% 98%;
  --primary: 0 0% 98%;
  --primary-foreground: 240 5.9% 10%;
  --muted: 240 3.7% 15.9%;
  --muted-foreground: 240 5% 64.9%;
  --border: 240 3.7% 15.9%;
}
```

In Tailwind v4 projects, wrap these in `@theme inline`:

```css
@theme inline {
  --color-background: hsl(var(--background));
  --color-foreground: hsl(var(--foreground));
  --color-primary: hsl(var(--primary));
}
```

This lets you use `bg-background`, `text-foreground`, `bg-primary` as utility classes while the
actual colour value comes from the CSS custom property.

## Customising a Component

Because you own the source, edit `components/ui/button.tsx` directly. Example: adding an icon
variant using CVA:

```typescript
import { cva, type VariantProps } from "class-variance-authority";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        outline: "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        // Custom addition
        brand: "bg-brand text-white shadow hover:bg-brand/90",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);
```

## Monorepo Setup

In a monorepo (Turborepo, Nx), share components across apps via a dedicated UI package:

```
packages/
  ui/
    components.json   ← shadcn config pointing to this package
    components/ui/    ← shared shadcn components live here
    src/lib/utils.ts
    package.json      ← exports { "./button": "./components/ui/button.tsx" }
apps/
  web/
  mobile-web/
```

Set the aliases in `components.json` of the UI package:

```json
{
  "aliases": {
    "components": "@company/ui/components",
    "utils": "@company/ui/src/lib/utils",
    "ui": "@company/ui/components/ui"
  }
}
```

Apps import `import { Button } from "@company/ui/button"`. Tailwind must be configured in each app
to include the UI package source for class scanning:

```css
/* app globals.css – v4 */
@source "../../packages/ui/components";
```

## Keeping Components Updated

ShadCN components are copied, not versioned. When upstream fixes a bug or adds an a11y improvement,
you must re-copy. The recommended flow:

```bash
# See what has changed upstream
npx shadcn@latest diff button

# Re-add (overwrites the file — commit first)
npx shadcn@latest add button --overwrite
```

Use `shadcn diff` in CI as an optional audit step to surface stale components. It exits non-zero
when drift is detected, useful as a scheduled check rather than a blocking gate.

## Anti-patterns

**Installing shadcn as a dependency**: `npm install shadcn-ui` installs the old v0-era package, not
the current CLI-driven system. Use `npx shadcn@latest`.

**Modifying the Radix primitive props directly**: Instead of changing `DialogContent` internals,
wrap the component. Upstream re-adds may overwrite inline edits silently.

**Hardcoding Tailwind colour classes inside components**: `bg-blue-600` breaks theming. Use the
semantic tokens (`bg-primary`, `bg-destructive`) so a theme swap changes everything.

**Skipping `tailwind-merge` in `cn()`**: Without `twMerge`, two conflicting class strings (e.g.,
`p-4 p-2` from variant + caller) keep both classes, and the winner is unpredictable. The built-in
`cn()` helper fixes this.

**One giant `ui` component file per domain**: ShadCN intends each primitive to be a separate file.
Bundling `button + badge + avatar` into one file breaks tree-shaking and makes `shadcn diff`
useless.

## Gotchas

- The `toast` component was replaced by a `Sonner`-based implementation. Projects using the old
  `useToast` hook from the Radix-based toast must migrate to `import { toast } from "sonner"`.
- Some components (`DataTable`, `Calendar`, `Command`) are "blocks" — larger compositions. They
  depend on each other. Run `npx shadcn@latest add` for the block name, which resolves the tree.
- RSC components cannot use React context or event handlers. Any component that needs interactivity
  (`"use client"`) is marked by the CLI automatically. Do not remove this directive to force SSR.
- Radix UI v2 (released mid-2025) changed some prop names. If you add a component after upgrading
  Radix but your peers haven't, type errors will surface on `asChild`, `onOpenChange` etc. Keep
  `@radix-ui/*` packages in sync via a single workspace root lock.
- The `cn()` helper must use `tailwind-merge` v3+ when used with Tailwind v4. Earlier versions of
  `tailwind-merge` do not know about v4 class naming changes and can incorrectly merge classes.

## Verification

1. Run `npx shadcn@latest diff` — output should be clean or list only intentional local changes.
2. Render each component variant in a Storybook story or route and verify keyboard navigation,
   focus ring visibility, and dark mode styles.
3. Run an a11y audit (`axe` or `@axe-core/react`) against a page that includes modal, dropdown,
   and form components.
4. In production build, verify no Tailwind classes are purged that exist only in `components/ui`
   by checking that buttons, badges, and dialogs render with correct styles.

## Related

- `tailwind-component-patterns.md`
- `tailwind-css-v4-cloudflare-pages-build-pipeline.md`
- `headless-ui-architecture-patterns.md`
- `react-compound-components.md`
- `design-token-pipelines.md`

## Sources

- ShadCN UI docs: https://ui.shadcn.com
- Radix UI primitives: https://www.radix-ui.com
- Class Variance Authority: https://cva.style/docs
- tailwind-merge: https://github.com/dcastil/tailwind-merge
- Sonner toast: https://sonner.emilkowal.ski
