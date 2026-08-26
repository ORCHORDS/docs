# React Native RTL with I18nManager and Logical Style Properties

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

The example project mobile app adds Arabic and Hebrew locale support. On the web layer (Cloudflare Pages)
CSS logical properties (`margin-inline-start`, `padding-inline-end`, `inset-inline`) handle RTL
automatically via `dir="rtl"`. On the React Native layer the same CSS does not exist: StyleSheet
does not understand `inline-start` or `inline-end`. Naïve fixes—`if (isRTL) { marginLeft: 8 }
else { marginRight: 8 }`—scatter conditional logic across hundreds of components and invariably
miss callsites when new ones are added.

## Context

React Native has two interrelated RTL mechanisms that must be coordinated:

1. **`I18nManager`** — a native module that flips the global layout direction. When
   `I18nManager.isRTL` is `true`, the native layout engine mirrors the flex axis: flex row
   direction reverses, absolute positions swap, and the scroll view leading edge swaps. This is
   a process-level flag and requires an **app restart** to take effect.

2. **`StyleSheet` start/end properties** — React Native added logical style properties
   (`marginStart`, `marginEnd`, `paddingStart`, `paddingEnd`, `start`, `end`,
   `borderStartWidth`, `borderEndWidth`, etc.) that resolve relative to `I18nManager.isRTL`.
   These are the RN equivalent of CSS `inline-start`/`inline-end`.

Neither mechanism exists in web CSS. A shared component library for example project must therefore
bifurcate: the web export uses CSS logical properties, the native export uses RN logical styles.
This article covers the native side.

## The I18nManager Bootstrap

```ts
// app/i18n/rtl-bootstrap.ts
import { I18nManager, Platform } from 'react-native';
import * as Updates from 'expo-updates'; // or React Native's own reload

/**
 * Call once at startup, BEFORE the root component renders.
 * Reads the stored locale from AsyncStorage / MMKV and syncs the
 * native RTL flag. Triggers a reload if the flag has changed.
 */
export async function bootstrapRTL(locale: string): Promise<void> {
  if (Platform.OS === 'web') return; // CSS handles web RTL

  const rtlLocales = new Set([
    'ar', 'he', 'fa', 'ur', 'yi', 'dv', 'ug', 'ku',
  ]);
  const lang = new Intl.Locale(locale).language;
  const shouldBeRTL = rtlLocales.has(lang);

  if (I18nManager.isRTL !== shouldBeRTL) {
    I18nManager.allowRTL(shouldBeRTL);
    I18nManager.forceRTL(shouldBeRTL);
    // Reload is required for the flag to take effect in the native layer
    await Updates.reloadAsync();
  }
}
```

`I18nManager.forceRTL(true)` without `I18nManager.allowRTL(true)` is insufficient on some
Android OEM builds. Always call both. The reload is mandatory—changing the flag mid-session
corrupts layout until the next render tree rebuild at the native level.

## Logical Style Properties Reference

| CSS logical property       | React Native equivalent  | Notes                              |
|----------------------------|--------------------------|------------------------------------|
| `margin-inline-start`      | `marginStart`            | Resolves relative to `isRTL`       |
| `margin-inline-end`        | `marginEnd`              | Resolves relative to `isRTL`       |
| `padding-inline-start`     | `paddingStart`           | —                                  |
| `padding-inline-end`       | `paddingEnd`             | —                                  |
| `inset-inline-start`       | `start`                  | For `position: absolute` elements  |
| `inset-inline-end`         | `end`                    | For `position: absolute` elements  |
| `border-inline-start-width`| `borderStartWidth`       | —                                  |
| `border-inline-end-width`  | `borderEndWidth`         | —                                  |
| `text-align: start`        | `textAlign: 'left'` + manual swap | RN lacks `text-align: start` — see below |
| `flex-direction: row`      | `flexDirection: 'row'`   | Automatically mirrors when `isRTL` |

> **`textAlign` has no `'start'` value in React Native.** Use the `writingDirection` prop on
> `<Text>` or derive dynamically: `textAlign: I18nManager.isRTL ? 'right' : 'left'`. This is the
> one place where a conditional is unavoidable.

## Component Pattern: Logical Style Hook

```ts
// hooks/useLogicalStyles.ts
import { I18nManager, StyleSheet } from 'react-native';
import { useMemo } from 'react';

interface LogicalSpacing {
  marginStart?: number;
  marginEnd?: number;
  paddingStart?: number;
  paddingEnd?: number;
}

export function useLogicalStyles() {
  const isRTL = I18nManager.isRTL;

  return useMemo(() => ({
    isRTL,
    textStart: isRTL ? 'right' as const : 'left' as const,
    textEnd:   isRTL ? 'left'  as const : 'right' as const,
    /** Logical row: children flow end→start in RTL, start→end in LTR */
    rowReverse: isRTL
      ? StyleSheet.create({ row: { flexDirection: 'row-reverse' } }).row
      : StyleSheet.create({ row: { flexDirection: 'row' } }).row,
  }), [isRTL]);
}
```

For static styles prefer the built-in logical properties (`marginStart`, `marginEnd`); reserve
the hook for properties where RN has no logical equivalent (primarily `textAlign`).

## Shared Component: Card with Leading Icon

```tsx
// components/IconCard.tsx
import React from 'react';
import { View, Text, StyleSheet, I18nManager } from 'react-native';
import { useLogicalStyles } from '../hooks/useLogicalStyles';

interface IconCardProps {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
}

export function IconCard({ icon, title, subtitle }: IconCardProps) {
  const { textStart } = useLogicalStyles();

  return (
    <View style={styles.card}>
      {/* marginEnd = margin toward the text block, resolves to marginRight in LTR,
          marginLeft in RTL automatically */}
      <View style={styles.iconWrap}>{icon}</View>
      <View style={styles.textBlock}>
        <Text style={[styles.title, { textAlign: textStart }]}>{title}</Text>
        {subtitle && (
          <Text style={[styles.subtitle, { textAlign: textStart }]}>{subtitle}</Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',   // ← automatically mirrors in RTL
    alignItems: 'center',
    padding: 16,
  },
  iconWrap: {
    marginEnd: 12,          // ← logical: gap between icon and text, direction-aware
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  textBlock: {
    flex: 1,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
  },
  subtitle: {
    fontSize: 13,
    marginTop: 2,
  },
});
```

## Expo / EAS Build Consideration

EAS Build caches the JS bundle. After a `forceRTL` toggle the OTA update must deliver a fresh
bundle **and** restart the app. Using `expo-updates`:

```ts
// Always reload after RTL flag change, never just re-render
import * as Updates from 'expo-updates';
await Updates.reloadAsync();
```

In development (`expo start --dev-client`) reloads happen via `DevSettings.reload()`. Gate:

```ts
import { __DEV__ } from 'react-native';
if (__DEV__) {
  const { DevSettings } = await import('react-native');
  DevSettings.reload();
} else {
  await Updates.reloadAsync();
}
```

## Animated Components and RTL

`Animated.Value` driving a horizontal translate does **not** mirror automatically. A slide-in
animation defined as `translateX: 300 → 0` (element entering from the right) is wrong in RTL—the
element should enter from the left (`translateX: -300 → 0`).

```ts
import { I18nManager, Animated } from 'react-native';

const slideAnim = useRef(new Animated.Value(0)).current;
const direction = I18nManager.isRTL ? -1 : 1;

// Entry animation: slide in from the leading edge
slideAnim.setValue(direction * 300);
Animated.spring(slideAnim, { toValue: 0, useNativeDriver: true }).start();

// Apply
<Animated.View style={{ transform: [{ translateX: slideAnim }] }} />
```

Reanimated v3 users: the same principle applies—multiply horizontal offsets by
`I18nManager.isRTL ? -1 : 1` or use `useDerivedValue` to derive `rtlAwareOffset`.

## Icons and Images

Directional icons (arrows, chevrons, back buttons, play/pause glyphs that imply direction) need
mirroring. Non-directional icons (star, heart, user avatar) must **not** be mirrored.

```tsx
// Flip directional SVG/image icons in RTL
import { I18nManager, Image, StyleSheet } from 'react-native';

const styles = StyleSheet.create({
  directionIcon: {
    transform: I18nManager.isRTL ? [{ scaleX: -1 }] : [],
  },
});

<Image source={require('./arrow-right.png')} style={styles.directionIcon} />
```

Maintain an explicit allowlist (or block list) of icon names that require mirroring. Automate
the check in your icon component factory to avoid per-callsite decisions.

## Anti-patterns

- **Inline `if (isRTL)` in styles.** Use `marginStart`/`marginEnd` and `start`/`end` for
  position. Reserve runtime conditionals for `textAlign` and animation offsets only.
- **Calling `I18nManager.forceRTL` inside a component render.** It must be called once at app
  startup, before the component tree mounts. Mid-session calls corrupt the layout tree.
- **Skipping `allowRTL(true)` on Android.** Without it `forceRTL` is silently ignored on some
  Samsung and Xiaomi builds (MIUI in particular).
- **Using `flexDirection: 'row-reverse'` as a manual RTL hack.** This overrides the automatic
  mirroring and produces double-reversed layout when `I18nManager.isRTL` is already true. Use
  `flexDirection: 'row'` and let the native engine mirror.
- **Mirroring the status bar icon layout manually.** React Native's `<StatusBar>` handles this
  automatically once `I18nManager.isRTL` is set.
- **Forgetting that `position: 'absolute'` elements ignore flex mirroring.** Use `start`/`end`
  instead of `left`/`right` for absolutely positioned overlays.

## Gotchas

- **Hermes engine limitation**: Hermes (the default RN JS engine since RN 0.70) evaluates
  `I18nManager.isRTL` at module parse time for static `StyleSheet.create` calls. Dynamic
  re-evaluation after a reload is correct, but a stale module cache in development fast refresh
  can show the old direction until a full reload.
- **Navigation header back button**: React Navigation's native stack header mirrors the back
  chevron automatically. React Navigation JS stack does not. Use the native stack for RTL locales.
- **Keyboard avoiding view**: `KeyboardAvoidingView` with `behavior='padding'` is not
  direction-aware. It pads from the bottom regardless of RTL. Safe area insets must be applied
  separately with `react-native-safe-area-context`.
- **`textAlign` on `<TextInput>`**: Unlike `<Text>`, `<TextInput>` does not inherit `textAlign`
  from a parent. Set it explicitly on every input. On Android, `textAlign: 'right'` with
  `keyboardType='numeric'` can misplace the cursor—test on device.

## Verification

```bash
# Automated RTL snapshot tests with Jest + react-native-testing-library
# Force RTL before each test run:
# jest.setup.ts:
import { I18nManager } from 'react-native';
I18nManager.isRTL = true;

# Run snapshot suite with RTL flag forced
RN_RTL=true npx jest --testPathPattern='components/' --updateSnapshot

# Visual regression: use Maestro or Detox to take screenshots on device with Arabic locale
maestro test flows/rtl-smoke.yaml
```

```yaml
# flows/rtl-smoke.yaml (Maestro)
appId: com.orchords.example project
---
- launchApp:
    arguments:
      locale: ar-SA
- assertVisible: "الرئيسية"   # Home tab in Arabic
- takeScreenshot: rtl-home
- tapOn: "الإعدادات"           # Settings
- takeScreenshot: rtl-settings
```

## Related

- `css-logical-properties-2026.md` (web counterpart)
- `rtl-layout-cloudflare-pages-mobile.md`
- `hebrew-rtl-react.md`
- `arabic-persian-text-rendering.md`
- `i18n-rtl-testing-2026.md`

## Sources

- React Native I18nManager docs: https://reactnative.dev/docs/i18nmanager
- React Native RTL guide: https://reactnative.dev/blog/2016/08/19/right-to-left-support-for-react-native-apps
- React Navigation RTL: https://reactnavigation.org/docs/en/rtl-support
- Expo Updates API: https://docs.expo.dev/versions/latest/sdk/updates/
- Unicode RTL script list: https://www.unicode.org/iso15924/iso15924-codes.html
