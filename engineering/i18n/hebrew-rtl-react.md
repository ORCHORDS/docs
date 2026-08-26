# hebrew-rtl-react

**Issue:** Supporting Hebrew (RTL) in a React application
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
React components built for LTR need structural and CSS changes for Hebrew. Text alignment, icon direction, and input caret all need adjustment.

## Pattern / Solution
```tsx
const RTLProvider = ({ locale, children }) => {
  const isRTL = ['he', 'ar', 'fa', 'ur'].includes(locale.split('-')[0]);
  useEffect(() => {
    document.documentElement.dir = isRTL ? 'rtl' : 'ltr';
    document.documentElement.lang = locale;
  }, [locale, isRTL]);
  return <>{children}</>;
};
```
MUI RTL setup:
```tsx
import rtlPlugin from 'stylis-plugin-rtl';
import createCache from '@emotion/cache';
const cacheRTL = createCache({ key: 'muirtl', stylisPlugins: [rtlPlugin] });
const theme = createTheme({ direction: 'rtl' });
```
Hebrew font:
```css
:lang(he) { font-family: 'Noto Sans Hebrew', 'David Libre', sans-serif; }
```

## Gotchas
- Input placeholder alignment follows `dir` automatically in modern browsers
- `text-align: right` in RTL mode often needs `text-align: start` for consistency
- Drag-and-drop coordinates must account for `dir` RTL when calculating offsets

## Related
- `bidi-rtl-layout-css.md`
- `arabic-persian-text-rendering.md`
