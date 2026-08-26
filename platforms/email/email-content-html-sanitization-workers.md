# User-Generated HTML Sanitization Before Email Dispatch in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Applications that embed user-supplied content in transactional emails (e.g., invoice notes, personalised messages, support ticket replies) are vulnerable to HTML injection, CSS exfiltration, and malicious link injection unless the content is sanitised server-side before rendering.

## Context
Cloudflare Workers run in a V8 isolate without DOM APIs, so browser-oriented sanitisers like DOMPurify cannot be used directly. A lightweight denylist sanitiser targeting the subset of HTML safe for email (no scripts, no external resources, no event handlers) can be implemented in pure TypeScript and tested with `wrangler dev`. The sanitised output is then safe to interpolate into the email template before dispatch.

## Threat Model for Email HTML

Email clients parse HTML in a permissive environment. The threat vectors specific to email (distinct from web XSS) include:

- `<script>` injection (rare but possible in older clients)
- `onerror`, `onload`, and other event handler attributes on any tag
- CSS `url()` references that cause external image loads (tracking/deanonymisation)
- `<a href="javascript:…">` phishing links
- `<meta http-equiv>` redirects and header injection
- `<form>` elements that submit credentials from within the email client

## Allowlist-Based Tag Filtering

Maintain a strict allowlist of tags safe for email HTML rather than trying to enumerate every dangerous tag.

```typescript
const ALLOWED_TAGS = new Set([
  "p", "br", "b", "i", "strong", "em", "u", "s",
  "ul", "ol", "li",
  "a", "span", "div",
  "h1", "h2", "h3", "h4", "h5", "h6",
  "blockquote", "pre", "code",
  "table", "thead", "tbody", "tr", "th", "td",
  "hr", "small",
]);

const ALLOWED_ATTRIBUTES: Record<string, Set<string>> = {
  a: new Set(["href", "title", "target"]),
  span: new Set(["style"]),
  div: new Set(["style"]),
  p: new Set(["style"]),
  td: new Set(["colspan", "rowspan", "align", "valign", "style"]),
  th: new Set(["colspan", "rowspan", "align", "valign", "style"]),
  table: new Set(["cellpadding", "cellspacing", "border", "width", "style"]),
  img: new Set(["src", "alt", "width", "height", "style"]), // src validated separately
};
```

## Tag and Attribute Stripping with Regex

Workers have no DOM; use a two-pass regex approach: first strip disallowed tags entirely, then strip disallowed attributes from allowed tags.

```typescript
function stripDisallowedTags(html: string): string {
  // Remove script/style/meta/link/form blocks and their content
  const blockTags = ["script", "style", "meta", "link", "form", "iframe", "object", "embed", "base"];
  for (const tag of blockTags) {
    const re = new RegExp(`<${tag}[^>]*>[\\s\\S]*?<\\/${tag}>`, "gi");
    html = html.replace(re, "");
    // Also remove self-closing variants
    html = html.replace(new RegExp(`<${tag}[^>]*/?>`, "gi"), "");
  }

  // Remove all tags not in the allowlist
  html = html.replace(/<\/?([a-zA-Z][a-zA-Z0-9]*)[^>]*>/g, (match, tag: string) => {
    if (ALLOWED_TAGS.has(tag.toLowerCase())) return match;
    return ""; // Strip disallowed tag entirely
  });

  return html;
}
```

## Attribute Sanitisation

Strip event handler attributes and validate `href` values on anchor tags.

```typescript
const SAFE_HREF = /^(https?:\/\/|mailto:)/i;
const EVENT_HANDLER_ATTR = /\bon\w+\s*=/i;

function sanitiseAttributes(html: string): string {
  // Remove all event handler attributes globally
  html = html.replace(/\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]*)/gi, "");

  // Validate href values — strip javascript: and other unsafe schemes
  html = html.replace(
    /<a\s([^>]*)>/gi,
    (_match, attrs: string) => {
      const sanitisedAttrs = attrs.replace(
        /href\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+))/i,
        (_a, dq: string, sq: string, bare: string) => {
          const href = (dq ?? sq ?? bare ?? "").trim();
          return SAFE_HREF.test(href) ? `` : 'href="#"';
        }
      );
      return `<a ${sanitisedAttrs}>`;
    }
  );

  return html;
}
```

## CSS Property Filtering for Inline Styles

Allow only a small set of cosmetic CSS properties to prevent `url()` exfiltration.

```typescript
const ALLOWED_CSS_PROPS = new Set([
  "color", "background-color", "font-size", "font-weight",
  "font-style", "text-align", "text-decoration", "line-height",
  "padding", "margin", "border", "border-radius",
  "width", "max-width", "display",
]);

function sanitiseInlineStyle(style: string): string {
  return style
    .split(";")
    .map((decl) => decl.trim())
    .filter((decl) => {
      const [prop] = decl.split(":").map((s) => s.trim().toLowerCase());
      return ALLOWED_CSS_PROPS.has(prop);
    })
    .filter((decl) => !decl.toLowerCase().includes("url(")) // block external loads
    .join("; ");
}

function sanitiseAllInlineStyles(html: string): string {
  return html.replace(
    /style\s*=\s*"([^"]*)"/gi,
    (_match, style: string) => `style="${sanitiseInlineStyle(style)}"`
  );
}
```

## Composing the Full Sanitiser

```typescript
export function sanitiseEmailHTML(rawHtml: string): string {
  let html = rawHtml;
  html = stripDisallowedTags(html);
  html = sanitiseAttributes(html);
  html = sanitiseAllInlineStyles(html);
  // Final pass: remove any remaining event handlers that slipped through nesting
  html = html.replace(EVENT_HANDLER_ATTR, "");
  return html;
}

// Worker usage
export default {
  async fetch(request: Request): Promise<Response> {
    const { userContent, template } = await request.json<{
      userContent: string;
      template: string;
    }>();

    const safe = sanitiseEmailHTML(userContent);
    const emailBody = template.replace("{{USER_CONTENT}}", safe);

    // emailBody is now safe to send
    return Response.json({ html: emailBody });
  },
};
```

## Anti-patterns
- Denylist-only approaches — new HTML tags (e.g., `<portal>`, `<fencedframe>`) are added without updating the denylist
- Sanitising in the frontend/client before sending to the API — always re-sanitise server-side
- Allowing `<style>` blocks even with property filtering — CSS rules can target mail client UI elements
- Skipping plain-text path sanitisation — injected newlines in plain-text templates can manipulate MIME headers

## Gotchas
- Regex-based HTML parsing is not a real parser; deeply nested or malformed HTML may evade filters — treat sanitised output as untrusted for high-assurance flows
- `<img src>` pointing to internal infrastructure can leak server-side request data; always validate or block `src` for images
- Some email clients re-parse sanitised HTML with their own rules; test in Litmus or Email on Acid after sanitising
- URL-encoded `javascript:` (`javascript%3A`) must also be rejected in href validation

## Verification
1. Pass `<script>alert(1)</script>` — confirm output is an empty string
2. Pass `<a href="javascript:void(0)">click</a>` — confirm href is replaced with `#`
3. Pass `<p style="background: url(https://evil.com/track.png)">` — confirm the `url()` is stripped
4. Pass `<p onmouseover="steal()">text</p>` — confirm event handler attribute is removed
5. Send a sanitised message through Litmus and verify rendering is unbroken

## Related
- `/documentation/categories/email/email-header-injection-security.md`
- `/documentation/categories/email/email-attachment-scanning-r2-workers-ai.md`
- `/documentation/categories/email/email-spam-score-preflight-workers.md`
- `/documentation/categories/email/transactional-email-best-practices.md`

## Sources
- OWASP XSS Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- HTML Living Standard — Dangerous content rules: https://html.spec.whatwg.org/multipage/parsing.html
- Cloudflare Workers Runtime APIs: https://developers.cloudflare.com/workers/runtime-apis/
- Email Client CSS Support Table: https://www.caniemail.com/
