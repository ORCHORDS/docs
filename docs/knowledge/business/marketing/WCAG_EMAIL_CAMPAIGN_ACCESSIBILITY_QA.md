# WCAG Email Campaign Accessibility QA

## Scope

This control applies to promotional, lifecycle, transactional-with-promotional-content, newsletter, fundraising, event, product-launch, winback, loyalty, and account-marketing emails. It covers copy, design, HTML, plain-text alternatives, images, links, buttons, templates, personalization, localization, testing, evidence, and post-send correction.

The purpose is to make email campaigns more usable for people who rely on assistive technologies, keyboard navigation, zoom, high contrast, readable structure, and clear language. This document does not claim that a campaign conforms to WCAG at any level. Email clients vary widely, and WCAG conformance is defined for web content under specific testable success criteria. The canonical primary sources for this control are the W3C Web Content Accessibility Guidelines [WCAG 2.2 Recommendation](https://www.w3.org/TR/WCAG22/) and W3C WAI guidance on [making content usable for people with cognitive and learning disabilities](https://www.w3.org/TR/coga-usable/). Teams may also use W3C WAI resources such as the [WCAG quick reference](https://www.w3.org/WAI/WCAG22/quickref/) for testing support.

## Requirements Versus Recommendations

Required controls:

- Provide meaningful text alternatives for informative images and empty alt text for decorative images.
- Maintain logical reading order in the HTML and plain-text version.
- Use descriptive link and button text that makes sense out of context.
- Avoid conveying essential information by color alone.
- Provide sufficient text contrast under the organization’s adopted threshold.
- Ensure the email remains understandable when images are blocked.
- Avoid flashing or rapidly animated content that could create accessibility risk.
- Test templates with keyboard navigation, screen-reader review, image blocking, and dark-mode or high-contrast settings where supported.

Recommended controls:

- Use a single-column layout for most marketing emails.
- Keep copy concise and use clear headings.
- Use live HTML text instead of image-only text whenever feasible.
- Set language attributes for localized templates.
- Keep touch targets large enough for mobile users.
- Include a plain-text version for all campaigns.

## Workflow

Accessibility QA begins at brief intake, not after final design. The campaign owner identifies audience, languages, email type, core action, legal footer needs, images containing text, dynamic modules, personalization fields, and any countdown, animation, video thumbnail, or interactive element. Design then creates a layout using an approved accessible template or requests a new-template review.

Copy review checks subject line, preheader, headings, link language, offer clarity, time-sensitive language, and unsubscribe wording. Design review checks hierarchy, contrast, image reliance, mobile scaling, and focus on the primary action. Development review checks semantic structure, table layout behavior, alt attributes, role usage, language tags, fallback content, and whether hidden preheader text interferes with screen readers.

Before send, QA tests the compiled email, not only the template. The test must include final personalization values, final URLs, tracking parameters, dynamic content rules, and suppressed modules. A reviewer must inspect both HTML and plain-text output. If a campaign uses audience segmentation with materially different modules, at least one sample per segment must be tested.

Post-send, the owner monitors complaints, replies, unsubscribe spikes, click anomalies, rendering issues, and accessibility feedback. Corrections may include resending only when necessary, updating linked landing pages, changing templates, or suppressing inaccessible modules from future campaigns.

## Concrete Fields And Controls

Campaign accessibility fields:

- `campaign_id`: stable campaign identifier.
- `template_id`: approved email template.
- `email_type`: promotional, lifecycle, newsletter, event, fundraising, or transactional with marketing.
- `primary_language`: language code.
- `localized_versions`: list of language variants.
- `primary_cta_text`: visible call-to-action text.
- `plain_text_generated`: yes or no.
- `plain_text_reviewed`: reviewer and timestamp.
- `image_text_present`: yes or no.
- `alt_text_owner`: copy, design, or development owner.
- `contrast_review_status`: pass, exception, or corrected.
- `screen_reader_review_status`: pass, exception, or corrected.
- `keyboard_review_status`: pass, exception, or corrected.
- `image_blocking_review_status`: pass, exception, or corrected.
- `approved_exceptions`: documented deviations with owner and expiry.

Template controls must require a clear heading order, body text as live text, descriptive CTA labels, visible unsubscribe links, and footer content that remains readable on mobile. Images must have alt text decisions recorded as informative, functional, decorative, complex, or redundant. Functional images used as links require alt text that describes the action, not the visual appearance.

Link controls must reject vague labels such as “click here,” “learn more,” or “read more” when multiple links appear and context is lost. A link label may be short, but it must identify the destination or action, such as “View renewal options” or “Register for the webinar.” Color controls must ensure that error states, required fields in linked preference centers, price changes, or expiration notices are not indicated by color alone.

## Validation Evidence And Tests

Validation evidence includes the final rendered HTML, plain-text version, screenshots with images enabled and blocked, mobile screenshots, contrast calculations for key text, screen-reader notes, keyboard navigation notes, link-check report, and approved exceptions. Evidence should identify the email client or testing tool, date, template version, and campaign version.

Tests must include:

- Alt text test: verify every image has appropriate alt text or intentionally empty alt text.
- Image blocking test: disable images and confirm offer, sender, primary action, legal disclosures, and unsubscribe remain understandable.
- Reading order test: inspect source and screen-reader output for a logical sequence.
- Link purpose test: review links out of context and verify each label is descriptive.
- Contrast test: measure text, CTA, footer, and disclaimer contrast against the adopted threshold.
- Keyboard test: tab through links and controls in supported clients or browser-rendered previews.
- Mobile zoom test: verify text does not overlap or truncate at common mobile widths.
- Plain-text test: confirm the text version includes core message, links, required notices, and unsubscribe path.
- Personalization test: use longest expected names, prices, locations, and dates to catch wrapping failures.

The QA checklist should cite the W3C [WCAG 2.2 Recommendation](https://www.w3.org/TR/WCAG22/) and the W3C [WCAG 2.2 Quick Reference](https://www.w3.org/WAI/WCAG22/quickref/) as primary technical references. Where cognitive accessibility is material, include the W3C WAI [COGA usable content guidance](https://www.w3.org/TR/coga-usable/).

## Failures And Corrections

Common failures include image-only emails, missing alt text for product images, decorative images read aloud because they have filenames as alt text, low-contrast footer text, multiple identical “learn more” links, table order that differs from visual order, dark-mode inversions that hide logos or buttons, and unsubscribe links that are too small or too low contrast.

Corrections must preserve the campaign’s business purpose while reducing barriers. Replace image-only copy with live text. Rewrite link labels so they describe the destination. Add alt text for informative images and empty alt text for decorative dividers. Increase contrast by changing foreground and background colors rather than relying on bold weight alone. Simplify multi-column layouts that read out of order. Remove animated elements if flashing, speed, or client behavior cannot be confidently controlled.

If a defect is discovered after send, the owner must decide whether correction is needed in linked landing pages, preference centers, future sends, or a corrected resend. Resends can increase fatigue and complaints, so they should be reserved for material errors affecting comprehension, access, price, safety, deadline, or required notices. Every post-send defect must update the template backlog if the same issue could recur.

## Limitations

Email accessibility testing is constrained by inconsistent support across clients such as Outlook, Gmail, Apple Mail, webmail, and mobile apps. A screen-reader result in one environment does not guarantee identical behavior everywhere. Automated accessibility tools can find some defects, but they cannot reliably judge whether alternative text is meaningful, whether copy is understandable, or whether link purpose is clear.

This control therefore avoids broad claims such as “WCAG compliant email.” The approved internal statement is narrower: the campaign was reviewed against the organization’s email accessibility QA controls using WCAG-informed criteria and retained evidence for the tested clients and versions.

## Canonical sources

- **Primary authority 1 — WCAG 2.2 Recommendation:** [https://www.w3.org/TR/WCAG22/](https://www.w3.org/TR/WCAG22/)
- **Primary authority 2 — making content usable for people with cognitive and learning disabilities:** [https://www.w3.org/TR/coga-usable/](https://www.w3.org/TR/coga-usable/)
- **Primary authority 3 — WCAG quick reference:** [https://www.w3.org/WAI/WCAG22/quickref/](https://www.w3.org/WAI/WCAG22/quickref/)
