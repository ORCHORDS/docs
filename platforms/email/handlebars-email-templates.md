# handlebars-email-templates

**Issue:** Using Handlebars for dynamic email template rendering on the server
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Backend applications need to render personalized email HTML with dynamic data without a React/JSX build step.

## Pattern / Solution
1. Install: `npm install handlebars`
2. Create template file `welcome.hbs`:
```html
<h1>Hello, {{name}}!</h1>
<p>Your plan: {{plan}}</p>
{{#if trialDays}}<p>Trial ends in {{trialDays}} days.</p>{{/if}}
```
3. Compile and render:
```js
import Handlebars from 'handlebars';
import fs from 'fs';
const template = Handlebars.compile(fs.readFileSync('welcome.hbs', 'utf8'));
const html = template({ name: 'Alice', plan: 'Pro', trialDays: 7 });
```
4. Register partials for reusable components (header, footer, button).
5. Precompile templates for production performance.

## Gotchas
- Handlebars escapes HTML by default; use triple braces `{{{html}}}` only for trusted content.
- Nested data access uses dot notation: `{{user.firstName}}`.
- Missing variables render as empty string, not error; validate data before rendering.
- Precompiled templates cannot access new helpers registered after compilation.

## Related
- liquid-template-email, mjml-template-framework, email-personalization-patterns, email-template-versioning
