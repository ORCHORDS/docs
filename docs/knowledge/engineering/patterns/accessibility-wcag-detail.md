# accessibility-wcag-detail

**Issue:** WCAG 2.2 AA implementation patterns
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app has buttons that don't work with keyboard. Forms
without labels. Colors with insufficient contrast. A
blind user uses a screen reader; they can't navigate. A
lawsuit lands. You scramble to add accessibility.

## Root cause
**Accessibility is an afterthought.** It's a checklist at
the end of development, not a design consideration.

**Source:** WCAG 2.2:
https://www.w3.org/TR/WCAG22/

> "Web Content Accessibility Guidelines (WCAG) 2.2 covers
> a wide range of recommendations for making web content
> more accessible."

## The "POUR" principles

WCAG is built on 4 principles:

### Perceivable
- Users can perceive the content (see, hear, feel)
- Examples: text alternatives for images, captions for
  video, sufficient contrast

### Operable
- Users can operate the UI (click, type, navigate)
- Examples: keyboard navigation, no seizures (no flashing),
  enough time to read

### Understandable
- Users can understand the content and the UI
- Examples: readable text, predictable behavior, error
  messages

### Robust
- Content works with assistive technologies
- Examples: valid HTML, ARIA labels

## The 4 conformance levels

- **A:** Minimum; basic accessibility
- **AA:** Standard; the legal requirement in many places
- **AAA:** Highest; often aspirational

For most apps, **AA** is the target. Some industries
(government, education) require AA or higher.

## The "keyboard navigation" pattern

Every interactive element must be keyboard-accessible:
```html
<!-- ❌ Bad: div is not keyboard accessible -->
<div onclick="submit()">Submit</div>

<!-- ✅ Good: button is keyboard accessible -->
<button type="submit">Submit</button>
```

For custom widgets (e.g. a dropdown), use ARIA:
```html
<div role="combobox" aria-expanded="false" aria-haspopup="listbox">
  <input type="text" aria-autocomplete="list" aria-controls="listbox-1" />
  <ul role="listbox" id="listbox-1">
    <li role="option" aria-selected="true">Option 1</li>
    <li role="option" aria-selected="false">Option 2</li>
  </ul>
</div>
```

## The "focus management" pattern

For modals, traps the focus:
```ts
// On open: focus the first focusable element in the modal
// On close: return focus to the trigger
// Inside the modal: Tab cycles through the modal's focusable
// elements (not the page)
```

For SPAs, manage focus on route change:
```ts
// After route change: focus the main heading
const main = document.querySelector('main');
main.setAttribute('tabindex', '-1');
main.focus();
```

## The "alt text" pattern

For every image, provide alt text:
```html
<!-- ❌ Bad: missing alt -->
<img  />

<!-- ✅ Good: descriptive alt -->
<img  alt="A fluffy orange cat sleeping on a couch" />

<!-- ✅ Decorative: empty alt -->
<img  alt="" role="presentation" />

<!-- ✅ Complex image: long description -->
<figure>
  <img  alt="Sales growth chart" aria-describedby="chart-desc" />
  <figcaption id="chart-desc">Sales grew from $1M in Q1 to $2M in Q4, with a peak in Q3 at $2.5M.</figcaption>
</figure>
```

## The "form labels" pattern

Every form field needs a label:
```html
<!-- ❌ Bad: placeholder is not a label -->
<input type="email" placeholder="Email" />

<!-- ✅ Good: explicit label -->
<label for="email">Email</label>
<input type="email" id="email" name="email" />
```

For error messages, link to the field:
```html
<label for="email">Email</label>
<input type="email" id="email" name="email" aria-invalid="true" aria-describedby="email-error" />
<span id="email-error" role="alert">Please enter a valid email</span>
```

## The "color contrast" pattern

WCAG AA requires:
- **Normal text:** 4.5:1 contrast ratio
- **Large text (18pt+):** 3:1
- **UI components:** 3:1

```css
/* ❌ Bad: low contrast */
.button {
  background: #fff;
  color: #ccc;  /* 1.6:1 — fails */
}

/* ✅ Good: high contrast */
.button {
  background: #fff;
  color: #595959;  /* 7:1 — passes */
}
```

Use a tool like WebAIM's contrast checker.

## The "screen reader" pattern

For screen readers (NVDA, JAWS, VoiceOver), use semantic
HTML:
```html
<!-- ❌ Bad: divs for everything -->
<div class="header">
  <div class="nav">
    <div class="link">Home</div>
    <div class="link">About</div>
  </div>
</div>

<!-- ✅ Good: semantic HTML -->
<header>
  <nav>
    <a >Home</a>
    <a >About</a>
  </nav>
</header>
```

A screen reader announces "navigation, list, 2 items:
Home, About" — meaningful.

## The "ARIA" pattern

For non-semantic widgets, use ARIA:
```html
<!-- A tab interface -->
<div role="tablist" aria-label="Sample Tabs">
  <button role="tab" aria-selected="true" aria-controls="panel-1" id="tab-1">First</button>
  <button role="tab" aria-selected="false" aria-controls="panel-2" id="tab-2">Second</button>
</div>
<div role="tabpanel" id="panel-1" aria-labelledby="tab-1">First panel</div>
<div role="tabpanel" id="panel-2" aria-labelledby="tab-2" hidden>Second panel</div>
```

ARIA is for widgets that don't have native HTML equivalents.

## The "skip link" pattern

For keyboard users, a "skip to main content" link:
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
}
.skip-link:focus {
  position: fixed;
  top: 1rem;
  left: 1rem;
  z-index: 1000;
}
```

The link is hidden by default; visible on focus.

## The "live region" pattern

For dynamic content updates, use `aria-live`:
```html
<div aria-live="polite" aria-atomic="true">
  <!-- Updated dynamically; screen reader announces -->
</div>

<div aria-live="assertive" role="alert">
  <!-- For urgent updates; interrupts the current announcement -->
</div>
```

Use `polite` for non-urgent (e.g. "3 new messages"). Use
`assertive` for urgent (e.g. "Session expired").

## The "media" pattern

For video, captions + transcripts:
```html
<video controls>
  <source  type="video/mp4" />
  <track kind="captions"  srclang="en" label="English" default />
  <track kind="subtitles"  srclang="es" label="Spanish" />
</video>
```

For audio, transcripts:
```html
<audio controls ></audio>
<details>
  <summary>Transcript</summary>
  <p>... full transcript ...</p>
</details>
```

## The "automated testing" pattern

Use automated tools for the mechanical checks:
- **axe-core** (linter, browser extension)
- **Lighthouse** (Chrome)
- **Pa11y** (CI)
- **WAVE** (browser extension)

```ts
// In CI
import { AxeBuilder } from '@axe-core/playwright';

test('homepage is accessible', async ({ page }) => {
  await page.goto('/');
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
```

Automated tests catch ~30% of issues. Manual testing
(screen readers, keyboard) is essential.

## The "manual testing" pattern

For full coverage, manual testing:
1. **Keyboard:** Tab through the page; every interactive
   element is reachable
2. **Screen reader:** Use NVDA (Windows) or VoiceOver
   (Mac); navigate by headings, landmarks, links
3. **Zoom:** 200% zoom; layout still works
4. **Color:** Grayscale; contrast still readable

## The "accessibility statement" pattern

For a public-facing app, an accessibility statement:
```markdown
# Accessibility Statement

We are committed to making our app accessible to all
users, including those with disabilities.

## Standards
We aim to conform to WCAG 2.2 Level AA.

## Known issues
[List of known accessibility issues]

## Feedback
If you encounter an accessibility issue, please contact
us at accessibility@example.com.
```

## Verification
- **Test:** Automated a11y tests pass
- **Live:** Manual testing with screen readers
- **Audit:** Annual accessibility audit (third-party)

## Gotchas
- **The "accessibility is just ARIA" anti-pattern.** Most
  accessibility is from semantic HTML, not ARIA. ARIA is
  a last resort.
- **The "automated tests are enough" anti-pattern.**
  Automated tests catch ~30% of issues. Manual testing is
  essential.
- **The "we'll add it later" anti-pattern.** Retrofitting
  accessibility is expensive. Build it in from the start.
- **The "screen reader users are the only users" anti-
  pattern.** Keyboard users, low-vision users, cognitive
  disabilities — many types of accessibility.
- **The "WCAG AAA is required" anti-pattern.** AAA is
  aspirational; AA is the standard.
- **The "color is the only signal" anti-pattern.** Don't
  rely on color alone; use icons + text + ARIA.

## Related
- `i18n/rtl-safe-component-patterns.md`
- `secure-defaults.md`
- `visual-regression-testing.md`
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- axe: https://www.deque.com/axe/
- WebAIM: https://webaim.org/
- A11y Project: https://www.a11yproject.com/
