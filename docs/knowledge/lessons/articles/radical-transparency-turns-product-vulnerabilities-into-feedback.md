# Radical Transparency Turns Product Vulnerabilities Into Feedback

**Issue:** Product teams treat vulnerability disclosure as reputational damage to minimize, so customers receive incomplete advisories and engineering loses the chance to learn from recurring defect classes.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's Secure by Design principles include “Embrace Radical Transparency and Accountability.” CISA describes transparency as sharing security lessons and customer-security outcomes and maintaining complete, accurate vulnerability advisories and CVE information. The principle also cautions against using raw CVE counts as a simplistic negative metric: more discovered and disclosed vulnerabilities can reflect healthy testing and research rather than poorer security by itself.

## Engineering rule

- Publish vulnerability advisories that are complete enough for customers to understand affected products, impact, remediation, and status without exposing unnecessary sensitive detail.
- Keep CVE and weakness classification information accurate and timely where the product participates in those disclosure ecosystems.
- Feed disclosed vulnerabilities into root-cause and vulnerability-class analysis rather than closing each case as an isolated ticket.
- Measure customer security outcomes, remediation speed, recurrence, and eliminated defect classes in addition to raw vulnerability counts.
- Share lessons learned internally and, where appropriate, publicly so security improvement becomes visible and repeatable.
- Do not create incentives that suppress valid vulnerability discovery merely to make counts look lower.

## Verification

- Sample recent vulnerability advisories and check affected-version, impact, remediation, and status accuracy against internal evidence.
- Trace disclosed vulnerabilities to root-cause or recurring-class analysis and confirm corrective actions extend beyond the single instance where appropriate.
- Review executive/product security metrics for incentives that could discourage vulnerability reporting.
- Confirm materially corrected vulnerability information is updated in public advisories rather than left stale.

## Official sources

- CISA, Applying “Secure By Design” Thinking to Events in the News: https://www.cisa.gov/news-events/news/applying-secure-design-thinking-events-news
- CISA, Secure by Design Blogs and principles: https://www.cisa.gov/securebydesign/blogs
