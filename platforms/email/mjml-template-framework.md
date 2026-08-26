# mjml-template-framework

**Issue:** Using MJML to write responsive, cross-client email templates efficiently
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Writing table-based responsive email HTML is tedious and error-prone; MJML compiles modern markup to email-safe HTML.

## Pattern / Solution
1. Install: `npm install mjml`
2. Write MJML template:
```xml
<mjml>
  <mj-body>
    <mj-section><mj-column>
      <mj-text font-size="16px" color="#333">Hello World</mj-text>
      <mj-button href="https://example.com">Click Me</mj-button>
    </mj-column></mj-section>
  </mj-body>
</mjml>
```
3. Compile: `mjml template.mjml -o output.html`
4. Or programmatically:
```js
import mjml2html from 'mjml';
const { html, errors } = mjml2html(mjmlString);
```
5. Use `mj-include` for reusable components (header, footer).

## Gotchas
- MJML produces verbose HTML; output can be large. Minify before sending.
- Custom components require MJML 4+ and are TypeScript-based.
- MJML does not handle handlebars/liquid template variables; inject before compiling.
- Dark mode support requires custom CSS in `<mj-style>` blocks.

## Related
- email-html-rendering-clients, react-email-components, email-responsive-design, handlebars-email-templates
