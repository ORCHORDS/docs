# Font Loading: FOUT vs FOIT

## Understanding Font Loading Strategies

Font loading significantly impacts web performance and user experience. Two primary strategies exist: Flash of Unstyled Text (FOUT) and Flash of Invisible Text (FOIT).

**FOUT** occurs when a fallback font displays immediately while the custom font loads, causing a brief text reflow. **FOIT** happens when text remains invisible until the custom font loads completely.

## Font Display Property

The `font-display` CSS property controls how fonts are displayed during loading:

```css
@font-face {
  font-family: 'CustomFont';
  src: url('font.woff2') format('woff2');
  font-display: swap; /* Recommended for most cases */
}
```

### Font Display Values

- `swap`: Show fallback font immediately, swap to custom font when loaded
- `optional`: Load font optionally, fall back if not ready quickly
- `fallback`: Show fallback briefly, then swap (similar to swap but with shorter timeout)
- `block`: Keep fallback font for 3 seconds, then swap

## Practical Implementation

### Preloading Fonts

```html
<link rel="preload"  as="font" type="font/woff2" crossorigin>
```

### Subset Fonts

```css
/* Load only latin characters */
@font-face {
  font-family: 'Roboto';
  src: url('roboto-latin.woff2') format('woff2');
  font-display: swap;
}
```

### Variable Fonts

```css
@font-face {
  font-family: 'VariableFont';
  src: url('variable-font.woff2') format('woff2-variations');
  font-weight: 300 700;
  font-stretch: 80% 120%;
  font-display: swap;
}

body {
  font-family: 'VariableFont', sans-serif;
  font-variation-settings: "wght" 400, "wdth" 100;
}
```

## Critical Rendering Path

Proper font loading prevents Cumulative Layout Shift (CLS) issues:

```css
/* Avoid layout shifts */
@font-face {
  font-family: 'HeadingFont';
  src: url('heading.woff2') format('woff2');
  font-display: swap;
}

h1 {
  font-family: 'HeadingFont', serif;
  /* Ensure minimum height to prevent layout shift */
  min-height: 1.2em;
}
```

## Common Pitfalls

### 1. Incorrect Font Display Usage
```css
/* ❌ Wrong - causes FOIT */
@font-face {
  font-family: 'MyFont';
  src: url('font.woff2');
  font-display: auto; /* Default, may cause FOIT */
}

/* ✅ Correct */
@font-face {
  font-family: 'My
