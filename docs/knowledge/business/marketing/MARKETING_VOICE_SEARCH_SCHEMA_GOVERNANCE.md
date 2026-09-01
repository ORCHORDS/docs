# Voice Search Schema Governance

## Scope

This control governs the production, custody, and validation of structured data used to enable voice-assistant and voice-search content to read marketing claims aloud to the user with the intended accuracy, attribution, and scope. It applies to content published on first-party web properties (corporate sites, blog posts, news articles, product pages, FAQ pages, knowledge-base pages, podcast pages, video pages, location pages, and event pages), to syndicated content delivered to partners, to RSS feeds, and to the structured-data elements that voice assistants, smart speakers, in-car assistants, mobile voice assistants, and accessibility tools rely on when the assistant reads content aloud. It applies to the markup that designates which parts of a page are intended for vocal rendering, and to the markup that controls the language, the audience restriction, and the source attribution.

The governing reference is Schema.org's SpeakableSpecification, a type that identifies sections of a web page that are particularly well suited to be read aloud by text-to-speech applications and the criteria by which those sections are nominated. SpeakableSpecification is part of Schema.org's vocabulary, which is published at schema.org; while Schema.org is a vocabulary publisher rather than a regulator, it is the conventional schema for marking content that voice assistants and accessibility applications consult.

## Workflow or implementation guidance

The voice-search schema workflow proceeds in six steps.

1. Identify the pages eligible for voice rendering. The eligibility list is determined by the use case: news and timely articles, FAQs, how-to content, product descriptions, location information, event details, customer-service workflows, accessibility-oriented content, and other content where a spoken summary adds value to the user.
2. Choose the speakable markup mechanism. The mechanism is one of: CSS selectors anchored to elements within a page (in the `xpath` or `cssSelector` properties of a SpeakableSpecification), or a reference to a section of the page that contains the speakable text. The choice is documented with a rationale.
3. Author the speakable content. The content is written for clarity when read aloud: full names rather than abbreviations, no reliance on context that a listener can't infer, numbers read in spoken form where ambiguity matters, dates and times specified in machine-readable form with a parallel spoken form where needed. Disclosures are included where required, and the disclosure text is included in the speakable text where the disclosure is part of the substance.
4. Validate the markup. Validation confirms that the markup is parseable, that the selectors point to elements that exist, that the speakable content actually appears in those elements at render time, and that the markup does not include text that should not be read aloud (for example, a hidden promotional section).
5. Validate via the chosen surface. The team's chosen voice surface (a smart speaker skill or an in-app voice experience) is asked the typical queries the marketing team expects; the response is compared with the intended response and with the on-page content.
6. Maintain. The schematic versioning, the page changes, and the surface's behavior change over time. The markup is reviewed when the page changes, when the surface announces a schema-policy change, and when a discrepancy is observed.

## Controls

The controls in this workflow are designed to ensure that markup is accurate, parseable, and aligned with the actual rendering.

- Every page that publishes a SpeakableSpecification has a single named author and a review date. The schema type (`@type: SpeakableSpecification`) and the selector mechanism (`xpath` or `cssSelector`) are explicitly declared.
- Selectors are stable: they survive reasonable markup changes and are tested before publication. A selector that points to nothing, or to a different element than intended, is treated as a defect.
- The speakable text is the substantive content that should be read aloud; informational scaffolding that should not be read (such as navigation or hidden promotional notes) is excluded.
- Language identifiers are set on the speakable content where the page's primary language is not the only language or where the audience is restricted by locale. Locale-specific variants publish their own speakable blocks rather than reusing the primary-language block.
- Disclosures are included in the speakable text where the disclosure is substantive to the message. A surface that reads only the non-disclosure text and skips the disclosure is a defect that the team escalates.
- The chosen voice surface is documented. A change in the surface (a sunset, a new skill, a partner change) is recorded and re-tests the speakable content.

## Validation evidence

Evidence is collected at each phase.

- Speakable markup snapshot for each page: type, properties, selectors, the rendered content the selectors pointed to at the moment of capture, and a hash of the markup at that moment.
- A representative question-and-answer log for the chosen voice surface, with the response compared against the intended response and the on-page content.
- Periodic surface-policy snapshots, the date of capture, and the implications for the team's markup.
- Audit logs of page changes that affect speakable content, with the corrected markup, the date, and the re-validation result.

## Failure modes and correction

Common failures include marking a page as speakable when the page's content is not actually suitable for spoken rendering, using selectors that break when the underlying markup is edited, including navigation or hidden promotional material in the speakable block, omitting the disclosure in the speakable block, and assuming a single voice surface will use the markup without confirming that the surface supports the chosen version. Other failures include publishing speakable markup without a corresponding page rendering test and failing to honor the chosen surface's schema-policy changes.

Correction begins with the page. When a markup defect is detected, the markup is updated; the page is re-tested; the surface is re-tested with representative queries. Where a disclosure was omitted from the speakable block, the block is updated and a record is made of the omission. Where the surface has changed policy, the markup is re-evaluated against the new policy and the corrected markup is published; the previous version is preserved in the audit trail. The audit log captures the cause, the correction, the reviewer, and the date.

## Limitations

This control does not adjudicate which voice surfaces will use the published markup; a particular smart speaker, in-app assistant, or accessibility tool may choose to ignore speakable markup, to use a different version of Schema.org, or to render content differently. It does not address other forms of spoken content (podcast transcriptions, audio advertising, voice search advertising on platforms with their own policies). It does not replace accessibility work; speakable markup complements, but does not substitute for, accessibility-aware content.

## Canonical sources

- **Primary authority 1 — Schema.org, SpeakableSpecification:** [https://schema.org/SpeakableSpecification](https://schema.org/SpeakableSpecification)
- **Primary authority 2 — Schema.org, Speakable concept entry:** [https://schema.org/Speakable](https://schema.org/Speakable)
