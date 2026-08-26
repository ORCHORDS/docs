# accessibility-components

**Issue:** Accessible component patterns — buttons, forms, modals
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your modal traps focus incorrectly. The "close" button
isn't reachable by keyboard. The form doesn't announce
errors to screen readers. A blind user can't use your
app.

## Root cause
**Accessible components require intentional design.**
Copy-paste from a CSS framework doesn't work.

**Source:** WAI-ARIA Authoring Practices:
https://www.w3.org/WAI/ARIA/apg/

## The "button" pattern

A native button is best:
```html
<button type="button" onclick="handleClick()">Click me</button>
```

For a custom-styled button:
```html
<!-- ❌ Bad: div -->
<div onclick="handleClick()">Click me</div>

<!-- ✅ Good: button -->
<button type="button" class="custom-style">Click me</button>
```

If you must use a non-button element (e.g. for styling), add
ARIA:
```html
<div role="button" tabindex="0" onclick="handleClick()" onkeydown="handleKey(event)">
  Click me
</div>
```

The `role="button"`, `tabindex="0"`, and `onkeydown` make it
keyboard-accessible.

## The "form" pattern

```html
<form>
  <div>
    <label for="email">Email</label>
    <input type="email" id="email" name="email" required aria-describedby="email-help email-error" />
    <div id="email-help">We'll never share your email</div>
    <div id="email-error" role="alert" hidden>Please enter a valid email</div>
  </div>

  <button type="submit">Submit</button>
</form>
```

Key points:
- `<label for="email">` linked to `<input id="email">`
- `aria-describedby` for help text
- `aria-describedby` for error text
- `role="alert"` for error announcement

## The "modal" pattern

```html
<div role="dialog" aria-modal="true" aria-labelledby="modal-title" aria-describedby="modal-desc">
  <h2 id="modal-title">Confirm deletion</h2>
  <p id="modal-desc">Are you sure you want to delete this item?</p>
  <button type="button" onclick="cancel()">Cancel</button>
  <button type="button" onclick="confirm()">Delete</button>
</div>
```

In the JS:
1. **On open:** Save the previously focused element; focus
   the first focusable in the modal
2. **During open:** Trap focus (Tab cycles within the modal)
3. **On close:** Return focus to the saved element

```ts
function openModal(modal: HTMLElement): void {
  const previouslyFocused = document.activeElement as HTMLElement;
  modal.setAttribute('data-previously-focused', previouslyFocused.id);

  const firstFocusable = modal.querySelector<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  firstFocusable?.focus();

  modal.addEventListener('keydown', trapFocus);
}

function trapFocus(event: KeyboardEvent): void {
  if (event.key !== 'Tab') return;

  const modal = event.currentTarget as HTMLElement;
  const focusables = Array.from(modal.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"]):not([disabled])'));
  const first = focusables[0];
  const last = focusables[focusables.length - 1];

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function closeModal(modal: HTMLElement): void {
  const prevId = modal.getAttribute('data-previously-focused');
  if (prevId) {
    document.getElementById(prevId)?.focus();
  }
  modal.removeEventListener('keydown', trapFocus);
}
```

## The "dropdown" pattern

A native `<select>` is best:
```html
<label for="country">Country</label>
<select id="country" name="country">
  <option value="us">United States</option>
  <option value="ca">Canada</option>
</select>
```

For a custom dropdown (e.g. for styling or async options):
```html
<div role="combobox" aria-expanded="false" aria-haspopup="listbox" aria-owns="listbox-1">
  <input type="text" aria-autocomplete="list" aria-controls="listbox-1" />
  <ul role="listbox" id="listbox-1" hidden>
    <li role="option" aria-selected="false">Option 1</li>
    <li role="option" aria-selected="true">Option 2</li>
  </ul>
</div>
```

Implement:
- Arrow keys to navigate
- Enter to select
- Escape to close
- Type-ahead to filter

## The "tab" pattern

```html
<div role="tablist" aria-label="Settings">
  <button role="tab" aria-selected="true" aria-controls="panel-1" id="tab-1">Profile</button>
  <button role="tab" aria-selected="false" aria-controls="panel-2" id="tab-2">Account</button>
</div>
<div role="tabpanel" id="panel-1" aria-labelledby="tab-1">Profile content</div>
<div role="tabpanel" id="panel-2" aria-labelledby="tab-2" hidden>Account content</div>
```

Implement:
- Arrow keys to switch tabs
- Home/End to go to first/last
- Tab moves to the panel content

## The "tooltip" pattern

```html
<button aria-describedby="tooltip-1">Save</button>
<span role="tooltip" id="tooltip-1">Save your changes</span>
```

The tooltip is shown on hover/focus. The button has
`aria-describedby` so screen readers announce it.

## The "alert" pattern

```html
<div role="alert">
  Your changes have been saved.
</div>
```

Screen readers immediately announce `role="alert"` content.

For non-urgent announcements:
```html
<div role="status" aria-live="polite">
  Loading...
</div>
```

The `polite` announcement waits for a pause; `assertive`
interrupts.

## The "skip link" pattern

```html
<body>
  <a href="#main" class="skip-link">Skip to main content</a>
  <header>...</header>
  <main id="main" tabindex="-1">...</main>
</body>
```

```css
.skip-link {
  position: absolute;
  left: -9999px;
  top: 0;
  background: #000;
  color: #fff;
  padding: 0.5rem 1rem;
  z-index: 1000;
}
.skip-link:focus {
  left: 1rem;
  top: 1rem;
}
```

The link is hidden by default; visible on focus.

## The "focus" pattern

Make focus visible:
```css
/* ❌ Bad: removes the outline */
button:focus { outline: none; }

/* ✅ Good: custom focus indicator */
button:focus-visible {
  outline: 2px solid blue;
  outline-offset: 2px;
}
```

The `focus-visible` pseudo-class is for keyboard focus (not
mouse focus).

## The "live region" pattern

For dynamic content:
```html
<!-- Polite: doesn't interrupt -->
<div aria-live="polite" aria-atomic="true">
  <span id="cart-count">3 items</span>
</div>

<!-- Assertive: interrupts -->
<div role="alert" aria-live="assertive">
  Your session is about to expire.
</div>
```

The aria-live announces changes to screen readers.

## The "table" pattern

For data tables:
```html
<table>
  <caption>User list</caption>
  <thead>
    <tr>
      <th scope="col">Name</th>
      <th scope="col">Email</th>
      <th scope="col">Role</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th scope="row">Alice</th>
      <td>alice@example.com</td>
      <td>Admin</td>
    </tr>
  </tbody>
</table>
```

`<caption>`, `scope="col"`, `scope="row"` make the table
navigable for screen readers.

## The "image" pattern

```html
<!-- Informative: descriptive alt -->
<img  alt="Sales grew from $1M in Q1 to $2M in Q4" />

<!-- Decorative: empty alt -->
<img  alt="" />

<!-- Functional: describe the action -->
<button type="button">
  <img  alt="Delete" />
</button>

<!-- Complex: long description -->
<figure>
  <img  alt="Sales chart" aria-describedby="chart-desc" />
  <figcaption id="chart-desc">...</figcaption>
</figure>
```

The `alt` is required; it describes the image's purpose.

## Verification
- **Test:** Automated a11y tests (axe) pass
- **Live:** Manual testing with screen readers + keyboard
- **Audit:** Annual a11y audit (third-party)

## Gotchas
- **The "div soup" anti-pattern.** Use semantic HTML.
  Buttons are buttons, links are links.
- **The "outline: none" anti-pattern.** A focus indicator
  is essential. Customize, don't remove.
- **The "modal without focus trap" anti-pattern.** A modal
  without focus trap allows tabbing to the underlying
  page.
- **The "tooltip on hover only" anti-pattern.** Touch
  devices don't have hover. Tooltip on focus too.
- **The "color is the only signal" anti-pattern.** Use
  icons + text + ARIA, not color alone.
- **The "ARIA fixes everything" anti-pattern.** ARIA is
  the last resort. Use semantic HTML first.

## Related
- `accessibility-wcag-detail.md`
- `i18n/rtl-safe-component-patterns.md`
- WAI-ARIA APG: https://www.w3.org/WAI/ARIA/apg/
- WCAG: https://www.w3.org/TR/WCAG22/
- Inclusive Components: https://inclusive-components.design/
