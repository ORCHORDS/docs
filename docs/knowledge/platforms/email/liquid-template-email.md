# liquid-template-email

**Issue:** Using Liquid templating for email personalization and dynamic content
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Liquid is the native template language for Shopify and many ESPs; it provides safe sandboxed rendering for user-facing content.

## Pattern / Solution
1. Install: `npm install liquidjs`
2. Render template:
```js
import { Liquid } from 'liquidjs';
const engine = new Liquid();
const html = await engine.parseAndRender(
  '<h1>Hello, {{ user.name | capitalize }}!</h1>{% if user.vip %}VIP Member{% endif %}',
  { user: { name: 'alice', vip: true } }
);
```
3. Use filters for formatting: `| date: "%B %d, %Y"`, `| truncate: 100`.
4. Load templates from files: `engine.renderFile('emails/welcome', data)`.
5. Liquid is sandboxed: no arbitrary code execution; safe for user-generated template logic.

## Gotchas
- Liquid's `date` filter uses Ruby strftime format, not JavaScript format strings.
- Whitespace control: use `{%- -%}` to strip surrounding whitespace.
- Custom filters must be registered before rendering.
- LiquidJS is not 100% Liquid-spec compatible; check docs for edge cases.

## Related
- handlebars-email-templates, email-personalization-patterns, email-dynamic-content
