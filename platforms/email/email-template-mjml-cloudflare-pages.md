# email-template-mjml-cloudflare-pages

**Issue:** Email templates compiled with MJML at build time are not
           dark-mode-aware, break in Outlook, and lack localization
           hooks when deployed via Cloudflare Pages + Workers
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Designers report that emails look correct in Litmus previews but
render with misaligned columns in Outlook 2019, white backgrounds
in iOS dark mode, and untranslated strings when the user's locale
is `fr-FR`.  Build pipelines fail when developers try to require
MJML in a Worker because MJML depends on Node.js modules unavailable
in the Workers runtime.

## Context

MJML is a React-inspired XML language that compiles to email-safe
HTML.  The compilation step must happen at build time (in a Node.js
environment such as a Cloudflare Pages build container), not at
request time in a Worker.  The compiled HTML is stored as a Pages
asset or in R2 and fetched by a Worker at send time.  Localization
and personalisation are applied at send time via a lightweight
template substitution layer, not by re-running MJML.

## MJML project structure

```
templates/
  src/
    welcome.mjml
    otp.mjml
    digest.mjml
  compiled/        ← git-ignored, produced at build time
    welcome.html
    otp.html
    digest.html
  partials/
    header.mjml
    footer.mjml
  i18n/
    en.json
    fr.json
    ja.json
  build.js         ← Node.js build script
```

`build.js` compiles all `.mjml` files and writes HTML to `compiled/`:

```js
import { readFileSync, writeFileSync, readdirSync } from 'fs';
import mjml2html from 'mjml';

const SRC = './src';
const OUT = './compiled';

for (const file of readdirSync(SRC).filter(f => f.endsWith('.mjml'))) {
  const mjml = readFileSync(`${SRC}/${file}`, 'utf8');
  const { html, errors } = mjml2html(mjml, {
    beautify: false, minify: true,
    validationLevel: 'strict',
  });
  if (errors.length) { console.error(errors); process.exit(1); }
  writeFileSync(`${OUT}/${file.replace('.mjml', '.html')}`, html);
}
```

Add to `package.json` scripts and run in the Pages build command:

```json
{
  "scripts": {
    "build:email": "node templates/build.js",
    "build": "npm run build:email && next build"
  }
}
```

## Dark mode email support

MJML does not generate dark mode styles automatically.  Add them
via `<mj-style>` with a `prefers-color-scheme` media query inside
the MJML source:

```xml
<mjml>
  <mj-head>
    <mj-style>
      @media (prefers-color-scheme: dark) {
        .email-body { background-color: #1a1a1a !important; }
        .email-text { color: #e8e8e8 !important; }
        .email-link { color: #7eb8f7 !important; }
      }
      /* Force override for clients that support [data-ogsc] */
      [data-ogsc] .email-body { background-color: #1a1a1a !important; }
      [data-ogsc] .email-text { color: #e8e8e8 !important; }
    </mj-style>
    <mj-all css-class="email-body" />
  </mj-head>
  <mj-body css-class="email-body" background-color="#ffffff">
    …
  </mj-body>
</mjml>
```

Outlook uses its own dark mode pass via the `[data-ogsc]` attribute
selector; iOS Mail uses `prefers-color-scheme`; Gmail does neither
reliably—use full-dark colour choices that look acceptable on both
backgrounds.

## Mobile rendering matrix

```
┌──────────────────┬─────────┬──────────┬───────────┬──────────┐
│ Feature          │ Gmail   │ Outlook  │ Apple     │ Samsung  │
│                  │ Android │ 2019/M365│ Mail iOS  │ Mail     │
├──────────────────┼─────────┼──────────┼───────────┼──────────┤
│ CSS media query  │ No      │ No       │ Yes       │ Partial  │
│ Dark mode CSS    │ No *    │ Via ogsc │ Yes       │ No       │
│ Web fonts        │ No      │ No       │ Yes       │ No       │
│ SVG in <img>     │ Yes     │ No       │ Yes       │ Yes      │
│ Flexbox          │ No      │ No       │ No        │ No       │
│ CSS Grid         │ No      │ No       │ No        │ No       │
│ <video>          │ No      │ No       │ Yes       │ Partial  │
└──────────────────┴─────────┴──────────┴───────────┴──────────┘
* Gmail Android applies auto-dark on some accounts since 2024
```

MJML's table-based layout handles most of these constraints.  Use
`mj-image` with explicit `width` and `height` (no SVG); fall back to
system fonts (`font-family: Arial, Helvetica, sans-serif`).

## Localization integration

Apply i18n at send time inside the Worker using string interpolation
over the compiled HTML.  Keep keys as `{{key}}` placeholders in MJML:

```xml
<mj-text>{{greeting}}, {{user_name}}!</mj-text>
<mj-text>{{otp_instruction}}</mj-text>
```

Worker-side substitution:

```js
async function renderTemplate(templateName, locale, vars, env) {
  // Fetch compiled HTML from R2
  const obj = await env.TEMPLATES.get(`${templateName}.html`);
  if (!obj) throw new Error(`Template not found: ${templateName}`);
  let html = await obj.text();

  // Load locale strings from KV (cached per locale per deploy)
  const i18nKey = `i18n:${locale}:${templateName}`;
  let strings = JSON.parse(await env.CACHE_KV.get(i18nKey) ?? 'null');
  if (!strings) {
    const strObj = await env.TEMPLATES.get(`i18n/${locale}.json`);
    strings = await strObj.json();
    await env.CACHE_KV.put(i18nKey, JSON.stringify(strings),
      { expirationTtl: 3600 });
  }

  // Merge locale strings with per-send variables (vars take priority)
  const ctx = { ...strings, ...vars };
  return html.replace(/\{\{(\w+)\}\}/g,
    (_, k) => ctx[k] ?? `{{${k}}}`);
}
```

Fall back to `en` when a requested locale file does not exist in R2.

## Anti-patterns

- Running `mjml2html()` inside a Worker on every send—MJML's parser
  is a Node.js module; the Workers runtime will throw at import time.
- Storing compiled HTML in Git—binary-like blobs in Git bloat the
  repo; treat `compiled/` as a build artefact and upload to R2.
- Using CSS variables (`--color-bg`) in email templates—no email
  client supports CSS custom properties; hard-code fallback values.
- Applying personalisation (name, OTP) inside MJML before
  compilation—the compiled asset becomes single-use and cannot be
  cached; always substitute at send time.
- Forgetting `!important` on dark mode overrides—email clients apply
  their own inline styles that override standard CSS specificity rules.

## Gotchas

- MJML's `<mj-include>` resolves paths relative to the build script's
  working directory, not the MJML file's location; run the build
  script from the `templates/` root directory.
- Outlook ignores `max-width` on `<table>` but respects `width`.
  MJML handles this via inline `width` attributes; do not override
  via CSS.
- Gmail strips `<style>` tags in non-GSuite inboxes (consumer Gmail
  on web); always inline critical styles.  MJML inlines styles by
  default—do not disable `inlineStyle`.
- R2 `get()` returns `null` for missing objects; handle this before
  calling `.text()` to avoid a TypeError in the Worker.

## Verification

```bash
# Build and inspect compiled output
npm run build:email
wc -l templates/compiled/welcome.html  # should be 1 (minified)

# Upload to R2 staging bucket
wrangler r2 object put "email-templates-staging/welcome.html" \
  --file templates/compiled/welcome.html

# Send test email via Worker
curl -X POST https://api.example.com/email/test \
  -H 'Content-Type: application/json' \
  -d '{"template":"welcome","locale":"fr","to":"test@example.com",
       "vars":{"user_name":"Alice"}}'

# Validate rendered output in Litmus or Email on Acid
# Check Outlook 2019 and Apple Mail iOS dark mode previews
```

## Related

- `documentation/categories/email/mjml-template-framework.md`
- `documentation/categories/email/email-dark-mode-support.md`
- `documentation/categories/email/email-html-css-rendering-matrix.md`
- `documentation/categories/email/react-email-template-system.md`
- `documentation/categories/i18n/cloudflare-workers-i18n.md`

## Source URLs

- https://documentation.mjml.io/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/pages/configuration/build-configuration/
- https://www.caniemail.com/
- https://www.litmus.com/blog/the-ultimate-guide-to-dark-mode-for-email-marketers/
