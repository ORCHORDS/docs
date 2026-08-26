# typescript-satisfies-operator

**Issue:** Type assertions lose type information; explicit annotations prevent inference
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A route config typed as Record<string, RouteConfig> loses per-key type info; using as RouteConfig bypasses checks.

## Pattern / Solution
```ts
type Color = 'red' | 'green' | 'blue';
type Palette = Record<Color, string | [number, number, number]>;

const palette = {
  red: [255, 0, 0],
  green: '#00ff00',
  blue: [0, 0, 255],
} satisfies Palette;

// palette.red is [number, number, number] (inferred), not string | [number, number, number]
// palette.green is string (inferred)

// Route config with full inference
const routes = {
  home: { path: '/', component: Home },
  about: { path: '/about', component: About },
} satisfies Record<string, RouteConfig>;
```

## Gotchas
- satisfies checks the type but preserves the widest inferred type
- Use instead of as Type when you want both validation and inference
- Introduced in TypeScript 4.9

## Related
- `typescript-discriminated-unions-ui.md`
- `typescript-react-patterns.md`
