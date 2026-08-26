# React Native Web Shared Component Library

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your team maintains a React web app and a React Native mobile app that share domain logic but
duplicate UI components entirely. You want a shared component library where a `<Button>` renders
a `<div>` with CSS on web and a `<TouchableOpacity>` on native, from the same source file, without
forking or maintaining two component trees.

## Context

React Native Web (RNW) is a library that implements the React Native component and style APIs on
top of the browser DOM. A component written with `View`, `Text`, `Pressable`, and `StyleSheet`
renders correctly in both environments:

- **Native** (iOS/Android): via React Native's native bridge
- **Web**: via `react-native-web`, which maps `View` → `div`, `Text` → `span`, etc.

This is the "write once, run anywhere" promise for UI. The trade-offs are real: the React Native
style model (Yoga flexbox, no cascade, no pseudo-elements, limited animations) is a subset of CSS.
Components must stay within that intersection.

**When to use RNW:**

- Team ships both a web app and a React Native mobile app
- Most components are structural / form / data display (not rich CSS-heavy marketing pages)
- Acceptable trade-off: reduced styling flexibility for cross-platform parity

**When NOT to use RNW:**

- Web app uses advanced CSS (grid, scroll-snap, clip-path, CSS animations)
- Native app is greenfield and can use Expo-native alternatives
- Teams are separate and can afford independent codebases

## Monorepo Structure

Use a Turborepo or similar workspace:

```
packages/
  shared-ui/
    src/
      components/
        Button/
          index.tsx        ← shared source (uses View, Text, Pressable)
          Button.web.tsx   ← web-specific override (optional)
          Button.native.tsx ← native-specific override (optional)
      tokens/
        colors.ts
        spacing.ts
    package.json
apps/
  web/                     ← Next.js or Vite
    next.config.ts         ← must transpile shared-ui + react-native-web alias
  mobile/                  ← Expo / React Native CLI
    metro.config.js        ← resolves shared-ui from workspace
```

## Platform-Specific File Extensions

React Native's Metro bundler resolves `.native.tsx` over `.tsx` on native builds. For web, Webpack
and Vite resolve `.web.tsx` over `.tsx`. This gives you a clean escape hatch without `Platform.OS`
conditionals in shared code:

```
Button/
  index.tsx           ← shared: types, logic, re-exports platform file
  Button.web.tsx      ← web: can use HTML button, CSS class, web-only a11y props
  Button.native.tsx   ← native: uses Pressable, haptics, native a11y
```

`index.tsx`:
```typescript
export { Button } from './Button.web';  // bundler overrides with platform file
export type { ButtonProps } from './types';
```

For simple components that truly share implementation, a single file using RNW primitives is fine:

```typescript
// components/Badge/index.tsx
import { View, Text, StyleSheet } from 'react-native';

interface BadgeProps {
  label: string;
  variant?: 'success' | 'warning' | 'error';
}

export function Badge({ label, variant = 'success' }: BadgeProps) {
  return (
    <View style={[styles.root, styles[variant]]}>
      <Text style={styles.text}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 12 },
  text: { fontSize: 12, fontWeight: '600' },
  success: { backgroundColor: '#22c55e' },
  warning: { backgroundColor: '#f59e0b' },
  error: { backgroundColor: '#ef4444' },
});
```

This renders identically on iOS, Android, and Chrome.

## Configuring the Web App (Next.js)

React Native Web must be aliased so that `react-native` imports resolve to `react-native-web`:

```typescript
// next.config.ts
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  transpilePackages: ['react-native', 'react-native-web', '@company/shared-ui'],
  webpack(config) {
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      'react-native$': 'react-native-web',
    };
    config.resolve.extensions = [
      '.web.js', '.web.jsx', '.web.ts', '.web.tsx',
      ...config.resolve.extensions,
    ];
    return config;
  },
};

export default nextConfig;
```

For Vite-based web projects:

```typescript
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'react-native': 'react-native-web',
    },
    extensions: ['.web.tsx', '.web.ts', '.web.jsx', '.web.js', '.tsx', '.ts', '.jsx', '.js'],
  },
  optimizeDeps: {
    include: ['react-native-web'],
  },
});
```

## Configuring the Native App (Expo)

Expo handles React Native resolution automatically. To use the shared package from the monorepo:

```javascript
// metro.config.js
const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, '../..');

const config = getDefaultConfig(projectRoot);

config.watchFolders = [workspaceRoot];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, 'node_modules'),
  path.resolve(workspaceRoot, 'node_modules'),
];

// Prefer .native.tsx over .tsx, then .web.tsx (never picked on native)
config.resolver.sourceExts = ['native.tsx', 'native.ts', 'native.js', 'tsx', 'ts', 'js', 'json'];

module.exports = config;
```

## Design Tokens

Share colour, spacing, and typography tokens across platforms as plain TypeScript. Do not use CSS
variables (not available in React Native StyleSheet) or Tailwind (web only).

```typescript
// packages/shared-ui/src/tokens/colors.ts
export const colors = {
  brand: {
    50: '#eff6ff',
    500: '#3b82f6',
    900: '#1e3a8a',
  },
  neutral: {
    0: '#ffffff',
    950: '#0a0a0a',
  },
  semantic: {
    success: '#22c55e',
    warning: '#f59e0b',
    error: '#ef4444',
  },
} as const;

// packages/shared-ui/src/tokens/spacing.ts
export const spacing = {
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  6: 24,
  8: 32,
} as const;
```

Web components translate tokens to CSS variables or Tailwind classes; native components use them
directly in `StyleSheet.create`.

## Storybook for Cross-Platform Components

Run two Storybook instances — one for web (Vite + react-native-web), one for native (Storybook RN):

```
packages/shared-ui/
  .storybook-web/
    main.ts    ← uses @storybook/react-vite, aliases react-native to rnw
  .storybook-native/
    main.ts    ← uses @storybook/react-native
```

Stories are shared:

```typescript
// components/Button/Button.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { Button } from './index';

const meta: Meta<typeof Button> = {
  title: 'Components/Button',
  component: Button,
};
export default meta;

export const Primary: StoryObj<typeof Button> = {
  args: { label: 'Continue', variant: 'primary' },
};
```

## Testing

Use Jest with `jest-expo` preset for native tests and `@testing-library/react` with the
`react-native-web` resolver for web tests. Platform-specific files are picked up automatically.

```javascript
// jest.config.base.js
module.exports = {
  moduleNameMapper: {
    '^react-native$': 'react-native-web',
  },
  moduleFileExtensions: ['web.tsx', 'web.ts', 'tsx', 'ts', 'web.js', 'js', 'json'],
};
```

## Anti-patterns

**Using CSS classes in shared components**: `className` is not a React Native prop. It silently
does nothing on native. Use `StyleSheet.create` for shared styles; add a `.web.tsx` override if
CSS is needed on web.

**Using `Platform.OS === 'web'` for branching**: This works, but it embeds both platform branches
in the native bundle. Use file extension splitting (`.web.tsx` / `.native.tsx`) so dead code is
eliminated at bundle time.

**Sharing complex list implementations**: `FlatList` and `SectionList` are virtualised on native
but their web counterparts via RNW are not true virtual scrollers. Use platform splits for lists
over 500 items.

**Importing from react-native-web directly in shared code**: The shared package should import from
`react-native` only. The alias in each app's bundler config maps this to `react-native-web` on
web at build time, so the shared package stays platform-agnostic.

## Gotchas

- `StyleSheet.create` compiles styles to integers (native) but to plain objects (web via RNW). Do
  not compare style objects by reference across platform environments.
- `Animated` and `Reanimated` have web implementations but they diverge in capability. Complex
  gesture-driven animations typically need `.native.tsx` overrides using `react-native-reanimated`
  and a `.web.tsx` override using CSS transitions.
- `react-native-web` lags behind the latest React Native releases by a few months. Check
  compatibility before upgrading `react-native` in the mobile workspace.
- The `Text` component on web renders as `<span>` by default. For semantic HTML heading levels, use
  `accessibilityRole="heading"` and `aria-level` together: `<Text accessibilityRole="heading"
  aria-level={1}>`.
- Not all third-party React Native libraries have web support. Check
  https://reactnative.directory and filter by "web" before adding a dependency to the shared
  package.

## Verification

1. Import a shared component (`Badge`) in the Next.js app. Verify it renders in the browser with
   correct styles and `data-testid` passes through.
2. Import the same component in Expo Go. Verify it renders on iOS simulator.
3. Run `npx react-native-bundle-visualizer` on the native bundle to confirm no `react-native-web`
   code leaked into the native output.
4. Run `BUNDLE_ANALYZE=true npm run build` on the web app to confirm `react-native` source code
   is not included (should be replaced by `react-native-web` via alias).

## Related

- `frontend-monorepo-package-boundaries.md`
- `design-token-pipelines.md`
- `react-component-composition.md`
- `tailwind-component-patterns.md`
- `storybook-component-driven.md`
- `typescript-react-patterns.md`

## Sources

- React Native Web: https://necolas.github.io/react-native-web/
- Expo monorepo guide: https://docs.expo.dev/guides/monorepos/
- React Native Directory: https://reactnative.directory/
- Metro bundler config: https://metrobundler.dev/docs/configuration/
- Turborepo: https://turborepo.com/docs
