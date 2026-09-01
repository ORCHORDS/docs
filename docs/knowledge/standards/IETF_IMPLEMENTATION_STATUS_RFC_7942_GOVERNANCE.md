# IETF Implementation Status Governance with RFC 7942

## Purpose

Implementation experience can reveal ambiguity, interoperability failures, and impractical requirements while an Internet-Draft is still changing. That evidence is useful to reviewers, but implementation listings can become stale or be mistaken for endorsement if they are not governed carefully.

This article defines a public, project-neutral method for preparing and maintaining an Implementation Status section under RFC 7942.

## Source status and lifecycle

RFC 7942, **Improving Awareness of Running Code: The Implementation Status Section**, was published in July 2016 as Best Current Practice 205. It obsoletes RFC 6982.

The section is optional. It is intended for implementable Internet-Drafts seeking IETF consensus, whether developed in or outside a working group. It is temporary working-document content, not a permanent catalog in the resulting RFC. Authors should instruct the RFC Editor to remove the section and its RFC 7942 reference before publication.

## Entry content

For each known implementation, record information that helps reviewers evaluate the draft rather than merely count implementations:

- responsible organization;
- implementation name and a public implementation or description URL;
- brief description and maturity level;
- portions of the draft implemented;
- compatible draft revisions;
- licensing terms;
- implementation experience and known limitations;
- contact details;
- date the entry was last updated; and
- available interoperability results, test cases, or reports.

Label unknown or contributor-supplied facts as such. Do not infer full implementation from support for one feature or draft revision.

## Disclosure and neutrality controls

The section should make clear that:

- a listing is not an IETF endorsement;
- information can be supplied by contributors and may not be independently verified;
- the list is not necessarily complete; and
- unlisted implementations may exist.

Apply consistent inclusion criteria. Do not rank entries by commercial prominence, place promotional descriptions in the section, or use selective detail to imply preference. Working-group chairs and area directors can require changes when the section becomes promotional.

If detailed evidence is maintained outside the draft, keep it publicly accessible without authentication, registration, or access controls. Do not link to private dashboards or evidence containing credentials, customer data, private network details, or non-public vulnerabilities.

## Maintenance workflow

1. Add the section immediately before Security Considerations.
2. Define an owner and review interval for every entry.
3. Tie compatibility claims to an exact draft revision.
4. Ask implementers to confirm material updates, implemented portions, and interoperability results.
5. Mark stale claims, broken links, or unverifiable evidence instead of silently treating them as current.
6. Review whether implementation feedback requires changes to protocol text, not only changes to the listing.
7. Preserve issue and test references needed for the working group’s decision record.
8. Before RFC publication, verify explicit removal instructions and confirm the section and RFC 7942 reference are absent from the final RFC.

## Evidence quality

Implementation existence is not the same as interoperability. Stronger evidence includes reproducible test descriptions, independent peer combinations, draft-revision identifiers, exercised features, failure results, and dates.

Record negative findings. Two implementations that share code, libraries, or assumptions may reproduce the same defect. Successful exchange across one path does not establish full protocol conformance, security, operational safety, or implementation independence.

## Relationship to draft transition governance

Implementation Status evidence informs review while the draft evolves. Separately, draft-to-RFC transition governance compares the adopted draft revision with the published RFC and verifies migration. Removing the temporary section does not remove the need to retain appropriate project evidence or reassess implementations against the final text.

Do not copy a stale implementation listing into permanent product claims after publication. Revalidate claims against the RFC and applicable updates.

## Failure modes

- Treating a listing as endorsement or certification.
- Omitting the exact draft revisions an implementation supports.
- Counting partial or common-code implementations as independent full implementations.
- Publishing marketing language instead of review-relevant evidence.
- Linking to evidence that requires registration or private access.
- Leaving stale contacts, broken URLs, or unverified claims unmarked.
- Retaining the temporary section in the published RFC.
- Assuming implementation against a draft proves conformance to the final RFC.

## Sources

- RFC 7942, Improving Awareness of Running Code: The Implementation Status Section: https://www.rfc-editor.org/rfc/rfc7942.html
- IETF Datatracker: https://datatracker.ietf.org/
- RFC Editor: https://www.rfc-editor.org/

Sources were checked on September 1, 2026.

## Scope note

This article governs temporary implementation-status content, disclosure, evidence maintenance, neutrality, and publication removal. It does not endorse an implementation, certify interoperability, or replace technical review of the Internet-Draft or resulting RFC.
