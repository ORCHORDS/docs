# RFC 7991 XML v3 Document Template Governance

## Purpose

The IETF publishes Requests for Comments (RFCs) and Internet-Drafts from a canonical XML source format. RFC 7991 ("The 'xml2rfc' Version 3 Vocabulary") defines the XML elements used to produce RFC Series documents, and RFC 7997 ("The RFC Series and the Unicode Format for Network Interchange") governs the use of Unicode within that format. A document authored in XML v3 is the source of truth; the text, HTML, and PDF renditions are generated from it.

This article provides a public, project-neutral method for governing an XML v3 document template: choosing which elements to include, how the vocabulary is validated, how renditions are produced and compared, and how errors are corrected. It does not publish an Internet-Draft and does not imply IETF endorsement of any template produced with it.

## Scope

The scope covers the XML v3 vocabulary defined in RFC 7991 and the Unicode conformance rules of RFC 7997. It covers:

- the root `<rfc>` element and its attributes, including `version="3"`, `submissionType`, `category`, `ipr`, and `docName`;
- the front-matter elements `<title>`, `<author>`, `<date>`, `<area>`, `<workgroup>`, and `<keyword>`;
- the structural body elements `<section>`, `<figure>`, `<table>`, `<list>` (as `<ul>`, `<ol>`, `<dl>`), `<sourcecode>`, and `<artwork>`;
- references elements `<references>` and `<reference>` and how they interact with the DOI and Internet-Draft submission tooling;
- the back-matter elements `<section>` and `<appendix>`; and
- the Unicode character and script constraints from RFC 7997 that restrict which characters may appear in RFC Series documents.

## Workflow

Authoring in XML v3 is a build-and-validate loop, not a manual typesetting exercise. The workflow is:

1. **Select a template.** Start from a minimal `<rfc>` skeleton with `version="3"` and the correct `submissionType` (`IETF`, `IRTF`, `independent`, or `status`). Confirm the `ipr` attribute matches the intended stream, because it controls the IETF Trust's copyright notices.
2. **Populate front matter.** Supply the `<title>`, the full `<author>` set with `<organization>` and `<address>`, the intended `<date>`, and the relevant `<workgroup>` and `<keyword>` elements. An absent `<date>` is filled in at publication time, which is not acceptable when the document must be reproduced verbatim.
3. **Compose the body.** Use `<section>` elements for the structure and the block elements defined by the vocabulary. Ensure cross-references use `<xref>` with a stable target, and that `<artwork>` and `<sourcecode>` distinguish diagrams from code.
4. **Build the references.** Group `<references>` into normative and informative sets. Use `<reference>` elements copied from the official citation libraries so that author lists, dates, and DOIs are correct and stable.
5. **Validate.** Run the document through xml2rfc and the schema validation available from the RFC Editor tooling. Schema violations, unresolved `<xref>` targets, and duplicate anchors are build errors, not cosmetic warnings.
6. **Generate and compare renditions.** Produce the text, HTML, and PDF renditions and compare them page-for-page with the intended layout. Differences are resolved by changing the XML, never by editing the generated output.
7. **Check Unicode conformance.** Confirm the characters used comply with RFC 7997. The permitted set is defined by the RFC Series Editor's character policy; characters outside it cause build failures or pre-publication rejection.

## Controls and evidence

The evidence that an XML v3 document is governed correctly includes:

- the canonical XML source, retained in version control with a documented origin and owner;
- a build configuration that pins the xml2rfc version, so that renditions are reproducible;
- the generated text, HTML, and PDF renditions, stored as immutable build artefacts;
- validation output showing zero schema errors and a list of warnings that were reviewed and dispositioned;
- a reference-citation audit trail showing each `<reference>` came from an official citation library or a stable primary source;
- Unicode conformance evidence, including the tool output or script used to check character usage; and
- a change log recording every change to the XML source, the reason, and the resulting rebuild.

## Validation

A governed XML v3 document is validated by:

- schema validation against the RFC 7991 XML schema published by the RFC Editor;
- build reproducibility: regenerating the text, HTML, and PDF from the XML yields identical outputs;
- cross-reference resolution: every `<xref>` resolves and every anchor is unique;
- reference integrity: every `<reference>` entry matches a published document, with the correct date and DOI;
- Unicode conformance: character usage falls within the permitted set defined for the RFC Series; and
- human review of the rendered text rendition, including page breaks, table alignment, and figure layout.

## Failure correction

Failure modes in XML v3 document governance include:

- **Editing generated output directly.** The corrective action is to revert the generated artefact and make the change in the XML source, then rebuild.
- **Stale references.** The corrective action is to replace hand-written `<reference>` entries with those from the official citation library and to re-run the reference audit.
- **Non-reproducible builds.** The corrective action is to pin the toolchain version and archive the build environment.
- **Unicode drift.** An author pastes text containing characters outside the permitted set. The corrective action is to normalise to the permitted characters and add a conformance check to the build.
- **Broken cross-references after restructuring.** The corrective action is to use stable anchors and to treat unresolved `<xref>` as build failures.

## Limitations

RFC 7991 is a vocabulary, not a style guide. Conformance to the schema does not ensure clarity, correctness, or consensus; those are determined by the stream's editorial and community processes. The vocabulary continues to evolve, and xml2rfc implements the vocabulary with its own release cadence, so a document valid under one version may need adjustment under another. RFC 7997 restricts character use for RFC Series documents but does not govern non-IETF uses of the same XML. This article does not address the IETF Stream's consensus process, which is governed by RFC 2026 and related process documents.

## Canonical sources

- RFC 7991 — The 'xml2rfc' Version 3 Vocabulary: https://www.rfc-editor.org/rfc/rfc7991.html
- RFC 7997 — The RFC Series and the Unicode Format for Network Interchange: https://www.rfc-editor.org/rfc/rfc7997.html

## Scope note

This article describes project-neutral authoring and governance of XML v3 documents. It does not submit, publish, or endorse any Internet-Draft or RFC and does not reproduce the normative content of the RFCs cited.
