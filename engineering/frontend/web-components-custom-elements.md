# web-components-custom-elements

**Issue:** Framework-agnostic reusable components that work across React, Vue, and vanilla HTML
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A design system needs to ship components usable by teams on different frameworks without duplication.

## Pattern / Solution
```ts
class MyButton extends HTMLElement {
  static observedAttributes = ['variant', 'disabled'];

  connectedCallback() {
    this.render();
  }

  attributeChangedCallback() {
    this.render();
  }

  render() {
    const variant = this.getAttribute('variant') ?? 'primary';
    this.innerHTML = `<button class="btn btn--${variant}"><slot></slot></button>`;
  }
}

customElements.define('my-button', MyButton);
```

```html
<my-button variant="primary">Click me</my-button>
```

## Gotchas
- innerHTML in connectedCallback overwrites slot content; use Shadow DOM for proper slot support
- React 18 does not forward events from custom elements well; React 19 improves this
- Lit framework simplifies authoring significantly over raw custom elements

## Related
- `shadow-dom-patterns.md`
- `react-server-components.md`
