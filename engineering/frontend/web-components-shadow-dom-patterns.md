# Web Components — Shadow DOM, Custom Elements, and Declarative Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your design system components are tied to a specific framework (React,
Vue, Angular), making them unusable in other frameworks or plain HTML
pages. Your marketing site uses a different framework than your
application, so you maintain two versions of every component. Global CSS
leaks into components and components leak styles into the page, causing
unpredictable visual regressions. You want truly reusable, framework-
agnostic UI components with guaranteed style encapsulation.

## Context

Web Components are a set of browser-native APIs — Custom Elements,
Shadow DOM, HTML Templates, and (as of 2026) Declarative Shadow DOM —
that enable creating reusable, encapsulated HTML elements without a
framework. In 2026, all major browsers (Chrome, Firefox, Safari, Edge)
fully support Custom Elements v2, Declarative Shadow DOM, CSS `@layer`
with `:host` scoping, and the `ElementInternals` API for form
participation. Declarative Shadow DOM enables server-rendered web
components without client JavaScript for first paint. Web Components
are not a replacement for frameworks but complement them — React,
Vue, Svelte, and Angular all support consuming and wrapping web
components.

## Core APIs

```
Custom Elements API:
  → Define new HTML tags with custom behavior
  → Lifecycle callbacks: connectedCallback, disconnectedCallback,
    attributeChangedCallback, adoptedCallback
  → extends HTMLElement (autonomous) or built-in elements

Shadow DOM:
  → Encapsulated DOM subtree attached to an element
  → Styles scoped inside — no leak in or out
  → :host, :host(), ::slotted() selectors
  → open vs. closed mode

HTML Templates:
  → <template> element: parsed but not rendered
  → <slot> element: composition points for light DOM content
  → Named slots for targeted content projection

Declarative Shadow DOM (2026):
  → <template shadowrootmode="open"> in HTML
  → Server-renderable shadow roots without JavaScript
  → Eliminates FOUC (flash of unstyled content)
```

## Custom element example

```javascript
class UserCard extends HTMLElement {
  static observedAttributes = ['name', 'role', 'avatar'];

  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.render();
  }

  attributeChangedCallback(name, oldValue, newValue) {
    if (oldValue !== newValue) this.render();
  }

  render() {
    const name = this.getAttribute('name') || 'Unknown';
    const role = this.getAttribute('role') || '';
    const avatar = this.getAttribute('avatar') || '';

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 16px;
          border-radius: 8px;
          background: var(--card-bg, #fff);
          border: 1px solid var(--card-border, #e0e0e0);
          font-family: var(--font-family, system-ui);
        }
        :host([highlighted]) {
          border-color: var(--highlight-color, #3b82f6);
          box-shadow: 0 0 0 2px var(--highlight-color, #3b82f6);
        }
        .avatar {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          object-fit: cover;
        }
        .name { font-weight: 600; }
        .role { color: var(--text-muted, #666); font-size: 0.875rem; }
      </style>
      ${avatar ? `<img class="avatar"  alt="">` : ''}
      <div>
        <div class="name">${name}</div>
        ${role ? `<div class="role">${role}</div>` : ''}
        <slot></slot>
      </div>
    `;
  }
}

customElements.define('user-card', UserCard);
```

```html
<!-- Usage -->
<user-card name="Jane Doe" role="Engineer" highlighted>
  <span slot="default">Team Lead</span>
</user-card>
```

## Declarative Shadow DOM (server-rendered)

```html
<!-- No JavaScript required for first render -->
<user-card>
  <template shadowrootmode="open">
    <style>
      :host {
        display: block;
        padding: 16px;
        background: var(--card-bg, #fff);
      }
    </style>
    <div class="name"><slot name="name"></slot></div>
    <div class="role"><slot name="role"></slot></div>
  </template>
  <span slot="name">Jane Doe</span>
  <span slot="role">Engineer</span>
</user-card>
```

## Styling patterns

### CSS custom properties (theming)

```css
/* Consumer (light DOM) controls theming via CSS variables */
user-card {
  --card-bg: #f8f9fa;
  --card-border: #dee2e6;
  --highlight-color: #0d6efd;
  --font-family: 'Inter', sans-serif;
  --text-muted: #6c757d;
}

/* Inside shadow DOM — :host uses the variables */
:host {
  background: var(--card-bg, #fff);
  border: 1px solid var(--card-border, #e0e0e0);
}
```

### ::part() for targeted styling

```javascript
// Component exposes parts
this.shadowRoot.innerHTML = `
  <div part="header">...</div>
  <div part="body">...</div>
`;
```

```css
/* Consumer styles specific parts */
user-card::part(header) {
  background: navy;
  color: white;
}
```

### ::slotted() for light DOM content

```css
/* Inside shadow DOM — style slotted content */
::slotted(h2) {
  font-size: 1.5rem;
  margin: 0;
}

::slotted([slot="footer"]) {
  border-top: 1px solid #eee;
  padding-top: 8px;
}
```

## Form participation (ElementInternals)

```javascript
class EmailInput extends HTMLElement {
  static formAssociated = true;

  constructor() {
    super();
    this.internals = this.attachInternals();
    this.attachShadow({ mode: 'open' });
  }

  connectedCallback() {
    this.shadowRoot.innerHTML = `
      <input type="email" part="input">
    `;
    const input = this.shadowRoot.querySelector('input');
    input.addEventListener('input', () => {
      this.internals.setFormValue(input.value);
      if (!input.validity.valid) {
        this.internals.setValidity(
          { typeMismatch: true },
          'Please enter a valid email'
        );
      } else {
        this.internals.setValidity({});
      }
    });
  }
}

customElements.define('email-input', EmailInput);
```

```html
<form>
  <email-input name="email"></email-input>
  <button type="submit">Submit</button>
</form>
```

## Framework interop

```
React:
  → Use web components directly in JSX (React 19+ full support)
  → Properties vs attributes: use ref for complex data
  → Events: addEventListener for custom events

Vue:
  → Native support via compilerOptions.isCustomElement
  → v-bind works for attributes, .prop modifier for properties
  → v-on works for custom events

Angular:
  → CUSTOM_ELEMENTS_SCHEMA in module
  → Property binding with [prop], event binding with (event)

Svelte:
  → Web components work as regular HTML elements
  → Can compile Svelte components TO web components
```

## Anti-patterns

- **Closed shadow DOM for reusable components** — using
  `mode: 'closed'` prevents consumers from accessing the shadow root,
  making debugging, testing, and extension impossible. Use `open`
  mode for public components; `closed` is only for internal browser
  APIs.
- **Heavy innerHTML on every change** — re-rendering the entire
  shadow DOM on every attribute change is inefficient. Use targeted
  DOM updates or adopt a lightweight reactive library (Lit, Stencil)
  for complex components.
- **Avoiding CSS custom properties** — hardcoding colors and fonts
  inside the shadow DOM prevents theming. Always expose design tokens
  as CSS custom properties with sensible defaults.
- **Global state in constructors** — performing DOM operations or
  accessing attributes in the constructor. The element may not be in
  the document yet. Use `connectedCallback` for initialization that
  requires DOM access.

## Gotchas

- **No CSS cascade into shadow DOM** — global styles like
  `* { box-sizing: border-box }` do not apply inside shadow DOM.
  Each component must declare its own box-sizing and reset styles.
  Inherited properties (color, font-family) do cascade through.
- **Server-rendering requires Declarative Shadow DOM** — without DSD,
  web components render as empty shells until JavaScript loads and
  `attachShadow()` runs. For SSR, use `<template shadowrootmode>`
  in the server-rendered HTML.
- **Custom element names must contain a hyphen** — `mycard` is
  invalid; `my-card` is valid. This is a spec requirement to avoid
  conflicts with future HTML elements.
- **Slotted content styling limitations** — `::slotted()` only
  selects direct children of a slot, not nested descendants. For
  deep styling, use CSS custom properties or `::part()`.

## Verification

- Design system components are framework-agnostic web components.
- Shadow DOM encapsulates styles — no global CSS leaks.
- CSS custom properties are exposed for theming.
- Declarative Shadow DOM is used for server-rendered components.
- Form-participating components use `ElementInternals`.
- Components are tested in multiple frameworks (React, Vue, plain HTML).

## Related

- `documentation/categories/frontend/react-server-components-patterns.md`
- `documentation/categories/patterns/design-patterns.md`
- `documentation/categories/testing/visual-regression-testing-tools.md`

## Source URLs (verified 2026-08-16)

- Web Components in 2026: They're the Present — https://medium.com/@mernstackdevbykevin/web-components-in-2026-theyre-not-the-future-anymore-they-re-the-present-75ba9872a364
- Web Components: Working With Shadow DOM — https://www.smashingmagazine.com/2025/07/web-components-working-with-shadow-dom/
- Web Components: The Framework-Free Renaissance 2026 — https://www.caimito.net/en/blog/2026/02/17/web-components-the-framework-free-renaissance.html
- Shadow DOM: Building Perfectly Encapsulated Web Components — https://dev.to/mukhilpadmanabhan/shadow-dom-building-perfectly-encapsulated-web-components-441f
