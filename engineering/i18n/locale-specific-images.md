# locale-specific-images

**Issue:** Serving locale-appropriate images (text in images, culturally specific visuals)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Images containing text cannot be automatically translated. Culturally inappropriate images create user experience problems in target markets.

## Pattern / Solution
Avoid text in images -- use CSS overlays:
```html
<!-- Good: locale-agnostic image + CSS text -->
<div class="hero" style="background-image: url('/hero.jpg')">
  <h1>{t('hero.headline')}</h1>
</div>
```
Locale-specific image convention:
```
/images/hero.jpg        # default (en)
/images/hero.fr.jpg     # French override
/images/hero.ar.jpg     # Arabic (RTL composition)
```
React component with fallback:
```tsx
function LocaleImage({ name, locale, alt, ...props }) {
  const [src, setSrc] = useState(`/images/${name}.${locale}.jpg`);
  return (
    <img
      src={src}
      onError={() => setSrc(`/images/${name}.jpg`)}
      alt={alt}
      {...props}
    />
  );
}
```

## Gotchas
- Alt text must also be localized; do not reuse English alt text
- White = mourning in some East Asian cultures; green has religious significance in Islam
- RTL languages may need mirrored versions of directional illustrations

## Related
- `bidi-rtl-layout-css.md`
- `translation-context-notes.md`
