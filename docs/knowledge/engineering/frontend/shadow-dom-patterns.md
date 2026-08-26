# shadow-dom-patterns

**Issue:** Custom element styles leak in and out without Shadow DOM encapsulation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A widget's internal styles are overridden by the host page's CSS; the widget also pollutes global styles.

## Pattern / Solution
```ts
class MyWidget extends HTMLElement {
  constructor() {
    super();
    const shadow = this.attachShadow({ mode: 'open' });

    const style = document.createElement('style');
    style.textContent = `
      :host { display: block; }
      :host([hidden]) { display: none; }
      .widget { padding: 1rem; background: white; }
    `;

    const wrapper = document.createElement('div');
    wrapper.classList.add('widget');
    wrapper.innerHTML = '<slot></slot>';

    shadow.append(style, wrapper);
  }
}
```

## Gotchas
- mode: 'open' allows JS access via element.shadowRoot; 'closed' blocks it
- CSS custom properties pierce the shadow boundary; use them for theming
- slot distribution is "flattened" for rendering but elements remain in the light DOM

## Related
- `web-components-custom-elements.md`
- `css-custom-properties-theming.md`
