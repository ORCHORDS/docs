# CSS custom highlight range lifecycle

**Issue:** Search hits and editor annotations are implemented by wrapping text in spans. DOM mutation breaks selection offsets, accessibility, diffing, and component ownership. A switch to the CSS Custom Highlight API then leaks stale ranges because the registry and document lifecycle are not managed.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## API boundary

The CSS Custom Highlight API styles ranges without inserting wrapper elements. Create `Range` or `StaticRange` objects, place them in a `Highlight`, register it by name in `CSS.highlights`, and style the named highlight with `::highlight(name)`.

`CSS.highlights` is a registry associated with the document. A registry entry is application state, not automatic component garbage collection. Ranges can overlap; the platform provides highlight priority and painting rules, so array order or DOM order must not be treated as the product's conflict policy.

## Lifecycle pattern

1. Convert model positions to DOM boundary points only after the target text nodes exist.
2. Keep one owner for each registry name. Namespace names by feature when independently mounted components could collide.
3. Rebuild or adjust ranges when text nodes are replaced, normalized, virtualized, or moved. A live `Range` can track some DOM mutation, but it cannot repair a lost model-to-DOM mapping.
4. Prefer `StaticRange` for immutable snapshots and `Range` when intentional live adjustment is required. State that choice in the owner.
5. Set a deterministic `Highlight.priority` when overlapping feature layers need precedence. Do not depend on registration timing.
6. On unmount, navigation, document replacement, or feature disable, call `CSS.highlights.delete(name)` (or clear only entries owned by the feature).
7. Treat highlight visuals as enhancement. Maintain separate semantic state and accessible descriptions for spelling, grammar, selection, comments, or search navigation.
8. Feature-detect `CSS.highlights` and retain a tested fallback.

## Example

```js
const range = new Range();
range.setStart(textNode, startOffset);
range.setEnd(textNode, endOffset);

const hits = new Highlight(range);
hits.priority = 10;
CSS.highlights.set("search-hits", hits);

// owner cleanup
CSS.highlights.delete("search-hits");
```

```css
::highlight(search-hits) {
  background: color-mix(in srgb, gold 65%, transparent);
  color: inherit;
}
```

## Verification

Test split text nodes, rerendered content, Unicode surrogate pairs, combining sequences, overlapping highlights, virtualized rows, page navigation, back/forward cache restoration, unmount/remount, forced colors, zoom, and unsupported browsers. Verify the registry contains exactly the active feature entries and no range refers to detached content.

## Gotchas

- UTF-16 DOM offsets are not grapheme-cluster indexes.
- Styling does not create focusable DOM nodes or an accessible annotation model.
- A global `clear()` can erase another component's highlights.
- Range creation against detached or wrong-document nodes should be rejected before registration.

## Sources

- [CSS Custom Highlight API Module Level 1](https://drafts.csswg.org/css-highlight-api-1/)
