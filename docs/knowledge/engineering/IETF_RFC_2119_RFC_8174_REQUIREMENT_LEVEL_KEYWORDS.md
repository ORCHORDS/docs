# IETF RFC 2119 and RFC 8174 Requirement Level Keywords

## Purpose

IETF RFC 2119, "Key words for use in RFCs to Indicate Requirement Levels," defines the meaning of the uppercase words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, MAY, and OPTIONAL in IETF specifications. RFC 8174 extends that definition by clarifying that the keywords apply regardless of case and regardless of whether they appear in full capital letters, so long as they are intended as the requirement-level keywords. Together these documents give engineering teams writing or consuming technical specifications (HTTP APIs, protocol specifications, contract documents) the authoritative reference for what the words mean and how to read them. This article summarizes project-neutral engineering use of these specifications.

## Scope

RFC 2119 and RFC 8174 govern the meaning of requirement-level keywords in IETF documents and in any technical specification that explicitly adopts them. They are the primary reference for many open specifications, including HTTP semantics (RFC 9110) and numerous IETF protocol documents, and they are routinely imported into API contracts, public protocol specifications, and inter-service agreements. They do not govern the substantive correctness of any specification, the process by which it is written, or its licensing.

Within the engineering knowledge base, this article covers:

- the precise meanings of each keyword;
- how to apply them when drafting specifications or API contracts;
- how to read them when implementing against a specification;
- case and rendering rules established by RFC 8174;
- validation of correct usage; and
- limitations: definitions of words, not a process or methodology.

## Workflow

A team adopting RFC 2119/8174 conventions should explicitly declare their use at the head of the specification. The generic workflow is:

1. At the document or specification level, add a normative reference to RFC 2119 (and RFC 8174 where text may be rendered without guaranteed capitalization) in the document front matter, for example: "The key words 'MUST', 'MUST NOT', 'REQUIRED', 'SHALL', 'SHALL NOT', 'SHOULD', 'SHOULD NOT', 'RECOMMENDED', 'MAY', and 'OPTIONAL' in this document are to be interpreted as described in BCP 14, RFC 2119, and RFC 8174."
2. Use the keywords precisely:
   - MUST / REQUIRED / SHALL: the requirement is absolute. Implementations that do not satisfy the requirement are non-conformant. SHALL is retained for compatibility with prior practice but SHOULD NOT be used in new documents where MUST conveys the same meaning.
   - MUST NOT / SHALL NOT: the prohibition is absolute.
   - SHOULD / RECOMMENDED: there may be valid reasons to ignore the requirement in particular circumstances, but the full implications must be understood and weighed before doing so.
   - SHOULD NOT / NOT RECOMMENDED: the inverse, indicating situations where an action is advised against but not forbidden.
   - MAY / OPTIONAL: the item is truly optional; implementations may include or omit it without consequence to conformance.
3. Avoid weakening the keywords with hedging language ("should ideally", "must strongly consider"); such phrasing breaks the distinction between MUST and SHOULD and is non-conformant.
4. When documenting optional behavior, use MAY/OPTIONAL and provide explicit guidance on what omission means for interoperability.
5. Maintain a consistency pass in review to confirm every requirement uses exactly one keyword and that no requirement uses none.

## Controls and evidence

Effective use of these keywords produces specifications that are unambiguous about obligation. Evidence of disciplined use includes:

- the formal reference to RFC 2119 (and RFC 8174) at the document head, plus BCP 14 reference;
- a requirement register or specification list where each requirement is tagged with its keyword;
- conformance criteria sections, where the specification names what conformance means and how each requirement is verified;
- version-controlled diff history of the specification, so keyword changes are tracked and intentional;
- interoperability matrices or test plans mapping each MUST requirement to at least one conformance check;
- traceability from SHOULD and RECOMMENDED items to documented rationale explaining why the wording is not MUST.

These artifacts let readers reliably distinguish between absolute and conditional obligations and reduce disputes in implementation.

## Validation

Validation that RFC 2119/8174 is applied correctly should include:

- confirming the BCP 14 boilerplate is present at the head of the specification where conformance language appears;
- reviewing each requirement statement to confirm exactly one keyword applies and is correctly chosen;
- checking that no MUST is weakened by hedging or conditional clauses ("MUST, except when..."), since conditional MUSTs are actually SHOULD;
- verifying RFC 8174 is referenced where the document might be rendered without capitalization (markdown processors, certain display contexts, plain-text export);
- confirming conformance criteria and test coverage treat MUST requirements as blocking and SHOULD requirements as advisory;
- checking that the document does not introduce new ad hoc requirement-level terms alongside the keywords.

RFC 2119 itself notes that a requirement marked SHOULD, SHOULD NOT, MAY, or OPTIONAL that is ignored must be clearly understood; reviewers should confirm that each ignored SHOULD has a recorded reason rather than silent omission.

## Failure correction

Common failure modes the specifications expose, and the corrective actions each imply:

- Conflating MUST and SHOULD, with inconsistent usage across the document—the corrective action is a single review pass renaming every requirement to its proper level.
- Omitting the BCP 14 reference at the document head, leaving the keywords undefined in context—the corrective action is to add the standard reference in front matter.
- Adding custom requirement keywords ("STRONGLY RECOMMENDED", "MUST ALWAYS") that BCP 14 does not define—the corrective action is to remove custom terms and use the defined vocabulary.
- Treating SHOULD as MUST in implementation and breaking interop when another party reasonably ignores it—the corrective action is to clarify in the specification whether the obligation is absolute, and to promote it to MUST if so.
- Lowering a MUST to SHOULD silently when a constraint cannot always be met—the corrective action is to either keep the MUST and document the constraint, or document why the level was changed with appropriate stakeholder review.

## Limitations

RFC 2119 and RFC 8174 define words, not substance. A specification can use every keyword correctly and still describe an unworkable protocol or an insecure design. The keywords say nothing about how to write good specifications, how to test conformance, or how to resolve ambiguity between requirements; they only fix the meaning of the listed words. They do not cover every obligation type (some specifications need weaker qualifiers like "informational" or "for further study") nor do they address security classification, privacy obligations, or jurisdictional law. Conformance to BCP 14 is a stylistic and vocabulary discipline; it is not a quality, security, or interoperability certification.

## Scope note

This article summarizes project-neutral engineering use of IETF RFC 2119 and RFC 8174. It does not claim implementation, conformity, or certification outcomes for any specific specification, protocol, or implementation.

## Canonical sources

- IETF RFC 2119 — Key words for use in RFCs to Indicate Requirement Levels: https://www.rfc-editor.org/rfc/rfc2119
- IETF RFC 8174 — Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words: https://www.rfc-editor.org/rfc/rfc8174