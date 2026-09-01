# IETF RFC 7997 Unicode Document Template Governance

## Purpose

The RFC Series is published under rules that govern every part of a published document, including its character set. RFC 7997 ("The RFC Series and the Unicode Format for Network Interchange") defines the Unicode characters the RFC Series permits and the rules for combining them so that documents remain archivable, renderable, and citable long after the tools that produced them. A document template targeting the RFC Series — or any document that reuses those rules — must encode those restrictions at the source level rather than treat them as a downstream concern.

This article provides a public, project-neutral method for governing a document template subject to RFC 7997's character policy. It does not publish any document and does not imply IETF endorsement of any template produced with it.

## Scope

The scope covers the character policy defined in RFC 7997 and the operational rules the RFC Editor applies. It covers:

- the permitted character set, defined in terms of Unicode code points and code-point sequences;
- the prohibition on certain characters that are inappropriate for the RFC Series (for example, unassigned code points, private-use characters, presentation forms, and surrogate pairs when used incorrectly);
- the rendering rules for combining characters and bidirectional text, where ambiguity in rendering must be removed before publication;
- the relationship between the character policy and the source XML defined by RFC 7991; and
- the operational checks the RFC Editor applies before accepting a document.

## Workflow

Governing a template subject to RFC 7997 is a build-time character discipline:

1. **Identify the permitted set.** Establish the current character set published by the RFC Series Editor and record it in the template configuration. Re-check at every authoring milestone, since the policy is updated over time and out-of-policy characters have stalled publication.
2. **Configure the source to reject non-permitted characters.** Configure the authoring tools and xml2rfc validator to fail the build when a character is outside the policy. Detection at build time is more reliable than correction at proofreading.
3. **Normalise on input.** Where text is imported from external sources, normalise to a defined Unicode normalisation form before publishing. Conflicting normalisations of the same code points produce text the user cannot see but the validator and reviewer can, and the discrepancy becomes a publication delay.
4. **Resolve bidirectional ambiguity.** Where text contains bidirectional text (for example, Latin and Hebrew combined), use the rendering controls recognised by the RFC Editor and record that they have been applied. Mixed-direction text that renders ambiguously between viewers will be returned by the Editorial Team.
5. **Resolve combining characters.** Where text uses combining characters (for example, accents applied after a base letter), ensure the resulting grapheme is well-defined. Use precomposed characters where they exist and the source allows them; document the choice where precomposed characters are not available.
6. **Check for problematic punctuation.** The policy excludes characters whose appearance is platform-dependent (for example, legacy presentation forms, ligature presentation forms, and ideographic variation selectors). Use a code-point list to scan every input file, not visual inspection.
7. **Validate before submission.** Run the build with the policy enforced and capture the validator output with the version pinned. The validated output is part of the submission evidence.
8. **Retain the validation evidence.** Store the validator output alongside the document and the build configuration, so any future concession (for example, a request for a new character) can reference what was actually present at submission.

## Controls and evidence

Evidence that RFC 7997 template governance operates correctly includes:

- the permitted character set, recorded at build time as a configuration artefact;
- the normalisation form applied to every input file, recorded in the build log;
- the bidirectional and combining character handling, documented in the template and validated by the build;
- the build configuration including validator version and policy version;
- the validator output for each build, archived with the document source; and
- the change log for the policy itself, recording when the policy set was upgraded and how the template was retested.

## Validation

A governed template subject to RFC 7997 is validated by:

- code-point scans confirming every character in the source falls within the permitted set at the policy version in force;
- normalisation checks confirming the document's bytes conform to a declared normalisation form;
- bidirectional rendering checks confirming mixed-direction text renders unambiguously in independent viewers;
- combining grapheme checks confirming visible characters are well-formed graphemes;
- punctuation checks confirming excluded presentation and legacy forms are absent; and
- a validator run with the same version that will be applied at submission, recorded as the build artefact.

## Failure correction

Common failure modes in RFC 7997 template governance include:

- **Policy consulted only at the end.** The corrective action is to enforce character constraints at build time, not at proofreading, so off-policy characters are caught before the document is ready for human review.
- **Normalisation drift between tools.** The corrective action is to fix a normalisation form in the build, apply it consistently, and revalidate.
- **Inconsistent rendering of mixed-direction text.** The corrective action is to apply the rendering controls recognised by the RFC Editor, retest across viewers, and document the applied control.
- **Out-of-policy punctuation copied from external sources.** The corrective action is to apply the code-point scanner to every imported fragment, not only to the document at large.
- **Validator pinned to an outdated policy version.** The corrective action is to track the RFC Series Editor's policy changes, retest the template at every policy update, and record the result.

## Limitations

The character policy is updated over time; a template that meets today's policy may be out of conformance after the next revision. The policy covers characters and rendering, not language policy: it does not endorse or exclude any particular language. RFC 7997 governs the RFC Series; documents intended for other series or other publishers should apply the relevant publisher's policy. The rule set is constrained to the IETF context; documents that need a broader character set than the policy permits cannot be RFC Series documents. Finally, character-policy compliance does not ensure publication: a document may be character-perfect and still fail IETF consensus or editorial requirements.

## Canonical sources

- RFC 7997 — The RFC Series and the Unicode Format for Network Interchange: https://www.rfc-editor.org/rfc/rfc7997.html
- RFC Editor — RFC Style Guide (publication policies relevant to character use): https://www.rfc-editor.org/styleguide/

## Scope note

This article describes project-neutral governance of document templates subject to RFC 7997's character policy. It does not submit, publish, or endorse any document and does not reproduce the normative policy maintained by the RFC Series Editor.
