# Normative Keyword Governance with RFC 8174

## Purpose

Requirement keywords can make specifications easier to test and review, but capitalization, boilerplate, context, and exception language determine how readers interpret them. Visual emphasis alone does not create a requirement.

This article defines a public, project-neutral method for using and reviewing the requirement keywords governed by BCP 14, comprising RFC 2119 and RFC 8174.

## Source status and interpretation rule

RFC 8174, **Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words**, was published in May 2017 as part of Best Current Practice 14. It updates RFC 2119.

Under RFC 8174, the special BCP 14 meanings apply only when the defined keywords appear entirely in uppercase. Lowercase words such as “must,” “should,” and “may” retain their ordinary English meanings. Uppercase text is not automatically normative merely because it is capitalized, and normative requirements can be written without BCP 14 keywords.

A specification using the keywords should include the BCP 14 boilerplate that cites both RFC 2119 and RFC 8174 and states that the special meanings apply only to all-capital forms.

## Authoring controls

1. Decide whether the document uses BCP 14 keywords and include the required boilerplate once.
2. Use an uppercase keyword only for a deliberate requirement level, not for emphasis.
3. State the actor, required behavior, triggering conditions, and observable outcome.
4. Keep exceptions adjacent to the requirement or link them unambiguously.
5. Use **MUST** and **MUST NOT** only where violation would cause a material interoperability, security, safety, or protocol failure.
6. When using **SHOULD** or **SHOULD NOT**, explain when deviation can be justified and what analysis is required.
7. Use **MAY** to express genuine permission, not uncertainty about expected behavior.
8. Separate informative examples and implementation advice from normative requirements.
9. Assign stable requirement identifiers when tests, controls, or conformance claims need traceability.

Do not mechanically uppercase every occurrence of a keyword. Ordinary prose often needs lowercase words, and excessive normative language can make a specification contradictory or impossible to implement.

## Review workflow

For each uppercase keyword, reviewers should ask:

- Is the intended requirement level justified?
- Is the responsible actor clear?
- Are preconditions and exceptions bounded?
- Can an implementation or process demonstrate compliance?
- Does another requirement conflict with it?
- Does the surrounding text accidentally weaken or broaden it?
- Is the requirement appropriate for the document’s status and scope?

Review lowercase occurrences separately for ambiguity. If a lowercase word appears to carry a mandatory meaning, rewrite the sentence rather than relying on reader inference.

## Quotation and derived requirements

When quoting an external specification, preserve capitalization and enough context to avoid changing meaning. Identify the source version and section. Do not convert explanatory prose into a BCP 14 requirement without recording that the new requirement is local.

A derived control should distinguish:

- the source’s exact normative statement;
- the local interpretation or implementation decision;
- any stricter local requirement; and
- the evidence used to verify the local control.

Changing a keyword while paraphrasing can materially change obligation strength. Treat such changes as specification edits, not editorial cleanup.

## Linting and verification

Automated checks can find missing boilerplate, lowercase keyword candidates, undefined requirement identifiers, or keywords inside examples. They cannot determine whether a requirement level is appropriate or whether prose is genuinely normative.

Maintain a requirement matrix linking identifiers to actors, conditions, implementation components, tests, exceptions, and approval. Negative tests should verify prohibited behavior for **MUST NOT** requirements, while exception tests should cover approved deviations from **SHOULD** guidance.

## Failure modes

- Treating lowercase “must” as automatically carrying the RFC 2119 meaning.
- Assuming any uppercase word is normative.
- Using BCP 14 keywords without citing both RFC 2119 and RFC 8174.
- Writing **SHOULD** without describing when deviation is reasonable.
- Using **MAY** where the document merely lacks a decision.
- Replacing source wording with a stronger keyword during paraphrase.
- Counting keywords as a substitute for testing requirement clarity and consistency.
- Claiming conformance without mapping requirements to evidence.

## Sources

- RFC 8174, Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words: https://www.rfc-editor.org/rfc/rfc8174.html
- RFC 2119, Key words for use in RFCs to Indicate Requirement Levels: https://www.rfc-editor.org/rfc/rfc2119.html
- BCP 14 record: https://www.rfc-editor.org/info/bcp14

Sources were checked on September 1, 2026.

## Scope note

This article governs authoring, interpretation, review, and traceability of BCP 14 keywords. It does not decide whether a requirement is technically correct, make non-normative text normative, or replace the complete source documents.
