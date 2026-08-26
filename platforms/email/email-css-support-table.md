# email-css-support-table

**Issue:** Quick reference for CSS property support across major email clients
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers need to know which CSS properties are safe to use before writing email templates.

## Pattern / Solution
| Property | Apple Mail | Gmail | Outlook 2019 | Yahoo |
|---|---|---|---|---|
| Flexbox | Yes | Yes | No | Partial |
| CSS Grid | Yes | Yes | No | No |
| `position` | Yes | No | No | No |
| `background-image` | Yes | Yes | No (use VML) | Yes |
| Web fonts (`@font-face`) | Yes | No | No | No |
| Media queries | Yes | Yes | Yes | Yes |
| `border-radius` | Yes | Yes | No | Yes |
| `box-shadow` | Yes | Yes | No | Yes |
| CSS animations | Yes | No | No | No |
| `calc()` | Yes | No | No | No |

Safe universally: `width`, `height`, `margin`, `padding`, `border`, `color`, `background-color`, `font-family`, `font-size`, `text-align`, inline `style`.

## Gotchas
- Use Can I Email (caniemail.com) for authoritative, regularly updated support data.
- Always provide table-based fallback layouts for Outlook.
- Test using Litmus or Email on Acid before sending to large lists.

## Related
- email-html-rendering-clients, email-responsive-design, mjml-template-framework
