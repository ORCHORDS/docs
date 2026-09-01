# W3C WCAG 2.2 Conformance Model for Engineering

## Purpose

The Web Content Accessibility Guidelines (WCAG) 2.2, published as a W3C Recommendation, define how to make web content more accessible to people with disabilities. The companion W3C document "WCAG 2.2 Conformance Requirements" specifies the formal conformance model: how conformance is claimed, what evidence (a "conformance claim") must accompany it, and the rules around which content a claim covers. For engineering teams, WCAG 2.2's conformance model is the authoritative reference for evaluating accessibility against the standard's success criteria, defining a level (A, AA, or AAA), and producing the documentation that supports an audit. This article summarizes project-neutral engineering use; it does not claim conformance, certification, or legal compliance outcomes for any specific product.

## Scope

The WCAG 2.2 conformance model applies to web content: pages, applications, documents, and media delivered over the web. It defines 86 success criteria organized under four principles (perceivable, operable, understandable, robust) at levels A, AA, and AAA. The conformance model specifies the conditions under which a page, set of pages, or site can claim conformance to a chosen level. It does not prescribe implementation, only behavior and outcome. It does not by itself guarantee legal compliance with regional accessibility laws, which vary by jurisdiction.

Within the engineering knowledge base, this article covers:

- the four principles and the level structure;
- the conformance model's rules for selecting the scope of a claim;
- the required elements of a valid conformance claim;
- validation approach using the W3C-recommended techniques and tests;
- failure modes and corrections; and
- limitations: a conformance model for content, not a design system or testing methodology.

## Workflow

A team claiming WCAG conformance should follow the formal conformance model rather than informal self-assessment. The generic workflow is:

1. Establish the scope of the conformance claim: a single page, a set of related pages, or a defined site. The conformance requirements specify that one of these three scopes must be chosen.
2. For each scope, establish the date of conformance: the snapshot at which the content was last verified, since content changes.
3. Select the target level (A, AA, or AAA) appropriate to regulatory, contractual, or organizational commitments; many regulated environments target AA.
4. Verify each applicable success criterion for the content in scope, using the W3C-documented sufficient techniques and, where available, advisory techniques.
6. For pages, perform the standard's full-page requirement: every page in scope must satisfy the criteria; a single non-conforming page disqualifies the claim at that level unless excluded by an explicit statement.
7. Where a third-party component cannot be made conforming, apply the standard's "Conformance Exceptions" or "Statement of Partial Conformance" rules rather than silently excluding it.
8. Produce a written conformance claim containing: title of the guideline and version, level claimed, scope and date of the claim, list of technologies relied upon, list of techniques used, and a list of any exceptions with justification.
9. Maintain the claim under change control: re-verify when content changes affect accessibility behavior.

## Controls and evidence

The conformance model is evidence-based. A defensible conformance claim is supported by:

- a written claim document conforming to the W3C template, with each required element explicitly addressed;
- per-page or per-template assessment records mapping each applicable success criterion to its evaluation result and supporting evidence (test output, screenshot, inspection record);
- a list of accessibility-supported technologies used, since the standard requires that a technology be used in an accessibility-supported way;
- records of testing methodology, including the test tools used and their known limitations;
- where Statement of Partial Conformance applies, the explicit identification of the content excluded and the reason (third-party content, user-generated content, or content outside the organization's control);
- periodic re-evaluation records, because WCAG conformance is a snapshot, not a permanent status;
- vendor and component accessibility statements for parts of the system provided by third parties.

## Validation

Validation that conformance claims are sound should include:

- confirming the claim document addresses every required element and is signed by a responsible authority;
- spot-checking pages in scope against the success criteria claimed at the chosen level, using both automated tools and manual review, since many criteria require human judgment;
- verifying that assistive technology interactions have been considered, since some criteria depend on how user agents and assistive technologies expose content;
- confirming that exceptions are explicitly recorded, not silently omitted;
- re-running validation when content, user interface, or technology stack changes;
- checking that the claim's "relied upon technologies" list is current and reflects how content is actually delivered.

## Failure correction

Common failure modes the model exposes, and the corrective actions each imply:

- Claiming conformance based only on automated tooling results—the corrective action is incorporating manual and assistive-technology verification for criteria that automated tools cannot evaluate.
- Conformance claims that omit required elements—the corrective action is to use the W3C claim template and to complete each section.
- Scope ambiguity: a claim covering an entire site when only part is conformant—the corrective action is to narrow the claim to a defensible scope or to fix the non-conforming content.
- Treating WCAG as a one-time check—the corrective action is establishing re-evaluation triggers aligned with content change management.
- Relying on third-party components without verifying their accessibility—the corrective action is collecting vendor accessibility statements and re-verifying after upgrades.
- Confusing legal compliance with WCAG conformance, since regional laws may add or interpret accessibility rules—the corrective action is to keep legal compliance and WCAG conformance as separate assessments with their own evidence chains.

## Limitations

WCAG 2.2 is a content and behavior standard. It does not prescribe design system components, color values, or implementation libraries. It is content-neutral: it does not favor any specific technology. The standard's AAA criteria are not required for AA conformance and may be impractical to satisfy universally; organizations commonly target AA. WCAG 2.2 does not address every accessibility need: emerging technologies, immersive environments, and AI-mediated interactions may require additional standards, notably WAI-ARIA 1.2 and the W3C/WAI AccName specification. Conformance does not guarantee usability for all users with disabilities; it sets a floor of accessibility behaviors that the standard's evidence shows is achievable and measurable.

## Scope note

This article summarizes project-neutral engineering use of the W3C WCAG 2.2 conformance model. It does not claim implementation, conformance, certification, or legal compliance outcomes for any specific web content, product, or organization.

## Canonical sources

- W3C — Web Content Accessibility Guidelines (WCAG) 2.2 Recommendation: https://www.w3.org/TR/WCAG22/
- W3C — WCAG 2.2 Conformance Requirements: https://www.w3.org/WAI/standards-guidelines/wcag/conformance/