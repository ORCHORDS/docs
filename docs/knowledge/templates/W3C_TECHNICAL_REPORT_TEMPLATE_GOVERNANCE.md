# W3C Technical Report Template Governance

## Purpose

W3C publishes technical reports on the Recommendation track: Working Draft, Candidate Recommendation, and W3C Recommendation, with additional states such as Recommendation-track regressions, rescinded, and obsoleted publications. Each publication is a dated technical report with a defined status, a status section, and a canonical set of links. A technical report template must therefore encode more than document structure: it must encode publication state.

This article provides a public, project-neutral method for governing a W3C technical report template — the boilerplate, status section, reference style, and publication metadata that must be correct before a document can advance. It does not submit a document to W3C and does not imply W3C endorsement.

## Scope

The scope covers the structure and governance of documents intended for the W3C Recommendation track, based on the W3C Process and the W3C publication rules. It covers:

- the document status section, including the maturity level, publication date, and stability statement;
- the relationship between a document's dated URL and its latest-version URL;
- the front matter W3C requires, including the title, the group's home page, and the publication date;
- normative references, informative references, and the requirement that references to W3C documents identify the dated publication being depended on;
- errata and amendments, which modify a published Recommendation without necessarily producing a new edition; and
- the requirements specific to each maturity level, including implementation experience and formal objections at Candidate Recommendation.

## Workflow

Governing a W3C technical report template follows the Recommendation-track workflow:

1. **Model the boilerplate as data, not prose.** Treat the maturity level, publication date, latest-version URL, this-version URL, and editor list as structured fields populated at build time. Hand-editing the status section invites errors that block advancement.
2. **Derive the status section from the maturity level.** Each maturity level has required statements. A Working Draft states it is a draft that may be updated or abandoned. A Candidate Recommendation Snapshot states how implementation feedback should be provided and identifies the review end date. The template must render the correct statement for the declared level, or the publication is invalid.
3. **Build references from a curated citation store.** References to W3C documents must identify the specific dated publication relied on, not merely the latest version. The template pulls each reference from a citation store that records the title, dated URL, and publication date.
4. **Separate normative from informative references.** The distinction is semantic: a normative reference is one the document depends on. The template enforces the split at build time and fails when a normative reference is missing required publication data.
5. **Track errata and amendments.** A published Recommendation accumulates errata and, since the 2020 revision of the Process, proposed corrections and amendments. The template must support publishing an updated edition that incorporates errata while preserving the original dated publication for reference.
6. **Record the advancement gate evidence.** Before each transition, record the change log since the previous publication, the implementation experience report where required, the disposition of formal objections, and the Director's or W3C's decision.
7. **Archive each dated publication.** Preserve the dated URL, the source used to build it, and the build configuration, so the publication can be reproduced exactly.

## Controls and evidence

Evidence that a technical report template is governed correctly includes:

- the structured source of the status metadata, versioned alongside the document content;
- the rendered status section for each publication, with the maturity level, date, and stability statement verified against the Process requirements for that level;
- the citation store entry for every reference, including the dated URL of each referenced W3C document;
- the build configuration and toolchain version used for each publication;
- the change log between successive publications, with a summary of substantive changes;
- errata and amendment records for each published edition; and
- transition request packets, including implementation experience evidence and the resolution of formal objections.

## Validation

A governed W3C technical report template is validated by:

- checking the rendered status section against the requirements for the declared maturity level in the operative W3C Process;
- verifying the this-version and latest-version URLs resolve to the intended publications;
- verifying every normative reference identifies a dated publication, not an undated or latest-version URL;
- verifying each referenced document's maturity level is adequate for the dependency claimed (a Recommendation's normative references should generally be Recommendations, or the dependency must be justified);
- reproducing the publication from its archived source and build configuration; and
- checking that errata published for the current edition are incorporated or explicitly deferred in the next edition.

## Failure correction

Common failure modes in W3C technical report governance include:

- **Hand-edited status sections.** The corrective action is to move all status metadata into structured fields and regenerate the section at build time.
- **Normative references to a Working Draft.** The corrective action is to either wait for the referenced document to advance, make the reference informative, or document the dependency and its risk in the transition request.
- **Latest-version links used as the citation.** The corrective action is to replace them with the dated publication URL and record the publication date in the citation store.
- **Errata left unincorporated.** The corrective action is to fold published errata into the next edition and note the incorporation in the change log.
- **Non-reproducible publications.** The corrective action is to archive the source and build configuration for every dated publication.

## Limitations

The W3C Process is periodically revised, and the publication rules are maintained separately by the W3C Team; a template must be checked against the operative versions at each use. The Process governs W3C publications; a document that merely imitates W3C style gains no standing from the resemblance. Membership of a Working Group, publication of a Working Draft, or even advancement to Candidate Recommendation does not indicate consensus on the document's content. Finally, W3C Recommendations define technology, not implementation quality: a product claiming to implement a Recommendation must demonstrate that claim through testing, not through the Recommendation's existence.

## Canonical sources

- W3C — W3C Process Document, 18 August 2025: https://www.w3.org/policies/process/20250818/
- W3C — W3C Technical Reports and Specifications index: https://www.w3.org/TR/

## Scope note

This article describes project-neutral governance of technical report templates for the W3C Recommendation track. It does not publish, submit, or endorse any W3C document and does not reproduce the normative content of the W3C Process.
