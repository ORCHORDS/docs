# RTL Layout Guide

## Understanding RTL Direction

Right-to-left (RTL) layouts require special consideration when building web applications. The `dir="rtl"` attribute on HTML elements or CSS `direction` property controls text direction, but proper layout handling goes beyond simple text alignment.

```html
<html dir="rtl">
  <body>
    <div class="container">Content flows right-to-left</div>
  </body>
</html>
```

## CSS Logical Properties

CSS logical properties provide direction-agnostic styling that automatically adapts to RTL layouts. Instead of using fixed `left` and `right`, use `inline-start` and `inline-end`.

```css
/* Instead of */
.element {
  margin-left: 20px;
  padding-right: 15px;
}

/* Use logical properties */
.element {
  margin-inline-start: 20px;
  padding-inline-end: 15px;
}
```

## Flexbox vs Grid in RTL

Flexbox and Grid handle RTL differently. Flexbox automatically reverses the main axis direction, while Grid requires explicit handling.

```css
/* Flexbox RTL behavior */
.flex-container {
  display: flex;
  flex-direction: row; /* In RTL, this becomes right-to-left */
}

/* Grid requires explicit column ordering */
.grid-container {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  direction: rtl;
}
```

## Mirroring Strategies

Use CSS `transform: scaleX(-1)` for mirroring complex layouts, but be careful with text content and interactive elements.

```css
/* Simple mirroring */
.mirror-element {
  transform: scaleX(-1);
}

/* Better approach - reset inner elements */
.mirror-container {
  direction: rtl;
  text-align: right;
}
.mirror-container * {
  direction: ltr;
  text-align: left;
}
```

## Practical Implementation

```css
/* Complete RTL layout example */
.rtl-layout {
  direction: rtl;
  text-align: right;
}

.rtl-layout .button-group {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
}

.rtl-layout .card {
  margin-inline-start: 0;
  margin-inline-end: 1rem;
}
```

## Testing RTL Layouts

Test RTL layouts using browser developer tools, automated testing with Puppeteer, and real user testing. Create dedicated test environments.

```
