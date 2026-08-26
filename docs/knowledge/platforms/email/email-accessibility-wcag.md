# email-accessibility-wcag

**Issue:** HTML emails are digital content delivered through browsers-in-mail-cllients, so WCAG 2.2 accessibility requirements (and laws like the ADA and European Accessibility Act) apply to them just like web pages — yet the Email Markup Consortium's 2025 accessibility report found systemic failures across the ecosystem: missing alt text, non-semantic markup, and contrast violations on the majority of commercial email. Teams shipping email campaigns with React Email / MJML templates have no checklist for making output screen-reader friendly and routinely exclude disabled users (roughly 1 in 4 adults in the US reports a disability) from notices, invoices, and account emails that have no alternative channel.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why WCAG applies to email

1. **Email is HTML content in a web view.** Every major client (Apple Mail, Gmail, Outlook) renders campaign HTML in a WebKit/Blink/Word-engine view, and WCAG 2.2 A/AA criteria (contrast, alt text, semantic structure, target size) are testable against that rendered output the same way as a web page.
2. **Legal exposure is real.** ADA lawsuits and EAA (enforced from June 2025) cover digital communications, and inaccessible transactional email (password reset, invoice, legal notice) is the riskiest category because there is no alternative access to the information.
3. **Accessibility overlaps deliverability.** Alt text, real text instead of image-only bodies, and logical structure also improve spam-filter scoring and plain-text fallbacks — one effort, two benefits.
4. **Screen readers are the primary consumer.** VoiceOver (Apple), TalkBack (Android), and NVDA/JAWS (desktop) read email top-down; anything communicated only by color, images, or visual layout is invisible to these users.

## Structure and semantics

1. **Use real heading tags (`<h1>`–`<h3>`) in reading order.** Screen-reader users navigate by headings; a template built purely from styled `<div>`/`<td>` elements gives them no way to skim. Keep exactly one `h1` per email.
2. **Set `role="presentation"` on layout tables.** Table-based email layout without this makes screen readers announce a meaningless grid ("table, row 1, column 2") before any content. Apply it to every `<table>` used purely for layout.
3. **Declare `lang` on the root element.** `<html lang="en">` (or the correct locale) lets screen readers pick the right pronunciation engine; a mismatch causes unintelligible synthesis for multilingual lists.
4. **Use semantic HTML where clients allow it.** `<p>`, `<ul>`/`<li>`, `<strong>`, and `<a>` are widely supported; avoid simulating lists with `&#8226;` characters inside table cells.
5. **Add ARIA landmarks sparingly.** `role="article"` on the body wrapper and `<role="navigation">` on menu bars help navigation; do not stack landmark roles on layout tables.

## Visual design requirements

1. **Contrast ratio 4.5:1 for body text, 3:1 for large text (WCAG 1.4.3).** Gray-on-gray "elegant" body copy is the single most common email accessibility failure; verify with a contrast checker, including text over background images.
2. **Minimum readable font size of 16px for body copy.** Tiny preview text and 12px legal footers fail low-vision users; keep disclaimers at least 13-14px.
3. **Never use color alone to convey meaning.** Pair red error states with icons or text labels ("Error:"), underline links inside body text rather than distinguishing them by color only.
4. **Tap targets at least 24x24 CSS px, ideally 44x44.** Stacked text links in footers are unusable with motor impairments on touch devices; pad buttons and space footer links.
5. **Left-align body text for LTR languages.** Justified text creates uneven "rivers" of white space that impair dyslexic readers.
6. **Respect `prefers-color-scheme` for dark mode.** Forced white backgrounds with light text (or vice versa) in dark mode create contrast inversions; test both schemes.

## Images, links, and content

1. **Descriptive `alt` text on every content image.** Describe function, not appearance: "Chat with support" not "picture of a person with a headset". Decorative images get empty `alt=""` so they are skipped.
2. **Never put critical content only in an image.** Voucher codes, event dates, and headlines baked into hero images are lost when images are blocked (Gmail clips, Outlook blocks by default for new senders) and to screen readers alike.
3. **Descriptive link text, never "click here".** Screen-reader users pull up a link list out of context; "View invoice INV-2041" survives that, "click here" does not. Avoid full URLs as link text.
4. **Plain-language copy at roughly grade 8 reading level.** Short sentences, active voice, and one idea per paragraph serve cognitive disabilities and skim-readers equally.
5. **Meaningful subject and preheader.** Front-load purpose ("Invoice INV-2041 from Acme, due Sep 1") so screen-reader users get context from the inbox list without opening the message.
6. **Animated GIFs need a pause or stay under 5 seconds.** Rapid flashing (more than 3 flashes/second) risks seizures (WCAG 2.3.1); looping GIFs are disorienting — prefer static frames for critical steps.

## Testing and program practices

1. **Automated checks per template.** Run every template through an email accessibility checker (e.g., Litmus or Email on Acid accessibility checks) plus a WAVE/axe pass on the hosted version; treat missing alt text as a build failure in template CI.
2. **Manual screen-reader passes quarterly.** VoiceOver (Cmd+F5 on macOS/iOS) and NVDA (free, Windows) on the top three templates; this catches table-reading order issues automated tools miss.
3. **Keyboard-only navigation test.** Tab through the email in a webmail client; link focus order must match visual order and focus must be visible.
4. **Track accessibility as a launch gate, not a retrofit.** Add an "accessibility checklist" item to campaign review; the EMC 2025 report shows the industry fails mainly because nobody owns this step, not because fixes are hard.
5. **Prefer framework components that bake this in.** React Email and MJML components with semantic defaults (e.g., `<Heading>`, `<Button>` with real anchors) reduce per-campaign effort versus hand-rolled table templates.
