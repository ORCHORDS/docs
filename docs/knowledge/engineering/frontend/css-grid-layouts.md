# css-grid-layouts

**Issue:** Complex two-dimensional layouts are difficult with flexbox alone
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A dashboard with headers, sidebars, and main content areas requires nested flexbox hacks to align correctly.

## Pattern / Solution
```css
/* Named template areas */
.layout {
  display: grid;
  grid-template-areas:
    "header header"
    "sidebar main"
    "footer footer";
  grid-template-columns: 250px 1fr;
  grid-template-rows: 60px 1fr 40px;
  min-height: 100vh;
}

.header  { grid-area: header; }
.sidebar { grid-area: sidebar; }
.main    { grid-area: main; }
.footer  { grid-area: footer; }

/* Auto-fill responsive grid */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.5rem;
}
```

## Gotchas
- auto-fill vs auto-fit: auto-fit collapses empty tracks; auto-fill keeps them
- subgrid (Chrome 117+) allows children to align to the parent grid
- grid-area names must match template-area strings exactly

## Related
- `css-flexbox-patterns.md`
- `css-container-queries.md`
