# W3C WCAG 2.2 AA Conformance Report Template Governance

## Purpose

W3C Web Content Accessibility Guidelines (WCAG) 2.2 (W3C Recommendation, October 2023) define four levels of conformance (A, AA, AAA) for web content, with AA being the most commonly cited regulatory baseline. A reusable WCAG 2.2 AA conformance report template records, for each WCAG success criterion in the A and AA levels, the conformance status (supports, partially supports, does not support, not applicable), the assessment method (automated tool, manual review, user testing), the evidence observed, the population (the set of web pages or content types evaluated), and any exceptions with rationale. The template converts an accessibility posture from an ad-hoc design assertion into an auditable artifact suitable for ADA / EAA / Section 508 conformance claims and procurement diligence.

The template must remain generic: it MUST NOT embed real URLs, screen-reader testing transcripts, or specific finding descriptions that identify individual customer sites.

## Scope

This template applies to WCAG 2.2 Level A and AA conformance evaluations of web content, including web applications, marketing sites, documentation sites, and native mobile applications evaluated through the W3C Mobile Accessibility Mapping. It does not address WCAG 2.1 or earlier versions (which lack the 2.2 success criteria); a separate template is required for legacy evaluations. The template does not address AAA conformance (which is rarely required and has its own evaluation methodology).

## Workflow

1. Open the template and complete the header with the assessment identifier, the WCAG version (2.2), the target level (AA), the assessment date, the assessment scope (URLs, page templates, content types), the assessor, and the assessment method.
2. For each WCAG 2.2 success criterion (for example 1.1.1 Non-text Content, 1.4.3 Contrast Minimum, 2.4.7 Focus Visible, 2.5.8 Target Size Minimum), populate:
   - Success criterion reference and title.
   - Level (A or AA).
   - Conformance status: supports, partially supports, does not support, or not applicable.
   - Population: the set of pages or content where the criterion was evaluated.
   - Assessment method: automated (axe-core, WAVE, Lighthouse, Pa11y), manual review, user testing with assistive technology.
   - Evidence observed: code snippet, screenshot, automated tool report excerpt, testing notes.
   - Exception or finding description if status is not "supports".
3. Document the sampling method used to select representative pages from the population.
4. Document the assistive technologies used for manual testing (for example NVDA on Windows + Firefox, VoiceOver on macOS + Safari, JAWS on Windows + Chrome).
5. Document any third-party content (embedded videos, third-party widgets) and the conformance status of that content.
6. Save the completed template alongside the accessibility statement, with public link in the site's accessibility statement.

## Controls and evidence

- Header records assessment identifier, WCAG version, target level, scope, date, assessor, and method.
- Per-success-criterion rows record level, status, population, method, evidence, and exception.
- Sampling rationale documented.
- Assistive technology matrix documented.
- Third-party content register documented with conformance status.

## Validation

- Every WCAG 2.2 A and AA success criterion is addressed; no criterion is left blank without a documented justification.
- Sampling rationale is documented and consistent with the population.
- The assistive technology matrix includes at least one screen reader per major platform.
- Findings are reproducible against the same population and method.
- The accessibility statement links to the public report.

## Failure correction

Common defects include evaluating only a subset of pages without documenting the sampling rationale, mixing 2.1 and 2.2 criteria, and recording "supports" without evidence citations. Corrective actions include requiring sampling rationale in the assessment plan, restricting the assessment to the declared WCAG version, and requiring evidence citations for every status.

## Limitations

- The template does not substitute for an automated accessibility scanner; it captures the assessment output.
- It does not address WCAG 2.2 AAA conformance; a separate template is required.
- It does not address Authoring Tool Accessibility Guidelines (ATAG) for content-authoring tools.
- It does not cover non-web content (PDF/UA, EPUB); a separate template is required.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **standards** (W3C accessibility standards), **engineering** (front-end accessibility testing), **business** (procurement and regulatory conformance claims), and **operations** (third-party content register). The template should be used together with those sibling-leaf articles.

## Canonical sources

- W3C Web Content Accessibility Guidelines (WCAG) 2.2 (W3C Recommendation, October 2023): https://www.w3.org/TR/WCAG22/
- W3C Accessibility Conformance Testing (ACT) Rules Format (W3C): https://www.w3.org/WAI/standards-guidelines/act/
- W3C Mobile Accessibility: How WCAG 2.2 and Other W3C/WAI Guidelines Apply to Mobile (W3C/WAI): https://www.w3.org/WAI/standards-guidelines/mobile/

Sources were verified on September 1, 2026.
