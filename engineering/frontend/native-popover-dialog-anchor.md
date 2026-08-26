# Native Popover, Dialog, and Anchor Positioning (2026)

## Symptom

You pull in a library (Radix, Floating UI, Headless UI) just to render a
tooltip, a menu, or a centered modal. The bundle grows 20-40 KB, you fight
z-index stacking contexts, and focus trapping requires hand-rolled event
listeners. In 2026 all major browsers (Baseline widely available) ship
native equivalents: the `popover` attribute, `<dialog>`, and CSS Anchor
Positioning. You can delete the library for many common cases.

## The three primitives

### `popover` — lightweight overlays (tooltips, menus)

```html
<button popovertarget="my-menu">Open menu</button>

<div id="my-menu" popover>
  <p>Menu content here</p>
  <button popovertarget="my-menu" popovertargetaction="close">Close</button>
</div>
```

- Browser handles the top layer (no z-index wars).
- Click-outside-to-dismiss and Esc-to-close are built in.
- Light-dismiss (`popover="auto`, the default) vs manual (`popover="manual"`).

### `<dialog>` — true modals with focus trapping

```js
const dialog = document.querySelector('dialog');
dialog.showModal();        // modal: blocks rest of page, traps focus
dialog.show();             // non-modal: no focus trap
dialog.close();            // closes, fires 'close' event
```

```css
dialog::backdrop {
  background: rgba(0, 0, 0, 0.5);
}
```

`showModal()` gives you focus trapping, inert background, and Esc-to-close
for free. No JavaScript focus management needed.

### CSS Anchor Positioning — pin an element to another

```css
.anchor-button { anchor-name: --my-anchor; }

.tooltip {
  position-anchor: --my-anchor;
  position-area: top span-left;  /* place above, allow horizontal shift */
  margin-bottom: 8px;
}
```

The tooltip stays glued to the button through scroll, resize, and reflow
without any JS `getBoundingClientRect` math.

## Gotchas

### `popover` is not a modal

`popover="auto"` does NOT trap focus and does NOT make the rest of the page
inert. For a blocking modal that captures all input, use `<dialog showModal>`.
Reaching for `popover` for a confirmation dialog is a common mistake that
leaves keyboard users able to tab to background elements.

### `position-area` syntax changed during the spec evolution

Early blog posts show `position-try-fallbacks` and `inset-area`. The final
Baseline names (2026) are `position-area` and `position-try`. If your
positioning CSS silently does nothing, check you are on the current syntax
and a supporting browser (Chrome 125+, Safari 26+, Firefox 131+).

### Safari historically lagged on `<dialog>`

`showModal()` and `::backdrop` work in Safari 15.4+, but older Safari versions
(used by some iOS users in 2026) ignore the modal behavior. Feature-detect:

```js
const supportsModal = typeof HTMLDialogElement !== 'undefined'
  && typeof HTMLDialogElement.prototype.showModal === 'function';
```

### Light-dismiss closes nested popovers unexpectedly

A popover opened from inside another popover with `popover="auto"` will close
both when the user clicks outside. Use `popover="manual"` for nested menus
and manage closing yourself, or structure the DOM so the child is a true
descendant of the parent's logical tree.

### `<dialog>` open by default needs `showModal`, not the `open` attribute

```html
<!-- WRONG: non-modal, no focus trap, no backdrop -->
<dialog open>...</dialog>

<!-- RIGHT: trigger via JS for modal behavior -->
<script>
  document.getElementById('d').showModal();
</script>
```

### Anchor positioning falls back with no plan by default

If the anchored element would overflow the viewport, the browser may render
it off-screen. Define fallbacks:

```css
.tooltip {
  position-area: top;
  position-try: flip-block, --custom-left-fallback;
}
```

## When to still use a library

- Complex combobox/autocomplete with filtering and virtualization.
- Date pickers with calendar grid logic.
- Animations that require JS-driven FLIP or spring physics.
- Legacy browser support (the native APIs need polyfills below Safari 15.4
  or for anchor positioning in older Firefox).
