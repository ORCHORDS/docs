# CSS Subgrid and :has() Selector: Modern Layout and State Management

## Overview

CSS subgrid and the `:has()` selector represent powerful modern CSS features that significantly enhance layout control and state management without JavaScript dependencies.

## Symptom

Developers often struggle with complex nested layouts and need to style elements based on their parent or sibling relationships. Traditional CSS approaches require complex workarounds or JavaScript for dynamic styling.

## Solution

### Subgrid for Nested Alignment

Subgrid allows nested grid containers to inherit their parent's grid definition, enabling precise alignment across multiple levels:

```css
.parent {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
}

.child {
  display: subgrid;
  grid-column: span 2;
}
```

This creates a clean nested grid structure where child elements align with parent columns automatically.

### :has() Parent Selector

The `:has()` selector enables styling based on parent-child relationships:

```css
/* Style list items that contain links */
li:has(a) {
  background-color: #f0f0f0;
}

/* Style containers with active children */
.container:has(.active) {
  border: 2px solid blue;
}
```

### Stateful Styling Without JavaScript

Combine `:has()` with other pseudo-selectors for dynamic styling:

```css
/* Show/hide content based on input state */
form:has(input:focus) .help-text {
  opacity: 1;
}

/* Style cards when hovered */
.card:hover:has(.expanded) {
  transform: scale(1.02);
}
```

## Gotchas

### Browser Support Limitations

- Subgrid requires Chrome 89+, Edge 89+, and Firefox 73+
- `:has()` selector has limited support in older browsers
- Always provide fallback styles for unsupported browsers

### Performance Considerations

The `:has()` selector can cause layout thrashing if overused:
```css
/* Avoid expensive selectors */
.container:has(.item:hover) .other-item {
  /* This may trigger reflows frequently */
}
```

### Layout Impact

Subgrid can create unexpected spacing issues when mixed with flexbox or other layout methods. Test thoroughly across different content lengths.

## Practical Implementation

Start with simple use cases like:
1. Creating nested grid layouts
2. Conditional styling based on content presence
3. Building interactive components without JavaScript

These features significantly
