# IETF Internet-Draft to RFC Transition Governance

## Purpose

Internet-Drafts are temporary working documents. RFCs are stable publications with assigned RFC numbers, but RFCs also have categories, statuses, update relationships, obsoletion relationships, and errata that affect how they should be cited and adopted.

This article defines a public, project-neutral method for governing references and implementations as IETF work moves from an Internet-Draft to a published RFC.

## Document status matters

An Internet-Draft identifies itself as work in progress and can be updated, replaced, or obsoleted. A draft revision can expire, and its filename includes a revision number. It must not be cited as though it were an immutable RFC.

A published RFC has a stable RFC number and publication record. Publication does not mean every RFC has the same standards status. Records should preserve the category and status shown by the RFC Editor or IETF source rather than calling every RFC an “Internet Standard.”

RFC 9000 illustrates the transition: it is a May 2021 Internet Standards Track RFC with a stable identifier, while `draft-ietf-quic-transport-34` was a January 2021 Internet-Draft revision that explicitly described itself as work in progress and carried an expiry date.

## Governance workflow

### 1. Inventory exact references

For each dependency on IETF work, record:

- the draft name and revision or RFC number;
- title, publication date, category, and status;
- canonical datatracker or RFC Editor URL;
- normative references used by the implementation;
- relevant updates, obsoletes, or is-obsoleted-by relationships;
- known errata reviewed; and
- the implementation, configuration, or public claim that depends on it.

Never shorten a draft reference so far that its revision becomes ambiguous.

### 2. Control draft adoption

Using an Internet-Draft in production should be an explicit exception or experimentation decision. Define the required revision, interoperability partners, change-detection owner, fallback, migration budget, and expiry review. Do not silently track an unversioned latest draft.

Draft text can change between revisions. Compare normative behavior, wire formats, registries, algorithms, error handling, and security considerations before updating the pinned revision.

### 3. Detect RFC publication

Monitor the datatracker and RFC Editor record for publication. When an RFC appears, verify that it is the actual successor to the adopted draft and identify changes made after the pinned revision. A title or Working Group match alone is not sufficient migration evidence.

Record the RFC's category accurately. “Standards Track” and “Internet Standard” are not interchangeable labels, and Informational, Experimental, Best Current Practice, and Historic publications should retain their published classification.

### 4. Migrate with evidence

A draft-to-RFC migration should:

1. compare the pinned draft revision with the published RFC;
2. identify changed requirements, code points, examples, and dependencies;
3. test protocol, parser, serializer, security, and failure behavior as applicable;
4. coordinate interoperability with external peers;
5. update citations, generated artifacts, and public claims; and
6. preserve the prior evidence and approve any temporary divergence.

Do not assume that an implementation matching a late draft automatically conforms to the RFC.

### 5. Track RFC lineage and errata

After adoption, monitor the RFC Editor record for verified errata and for RFCs that update or obsolete the baseline. An updating RFC can change only part of the operational picture; an obsoleting RFC does not prove that every deployed peer has migrated. Maintain a lineage view and make compatibility decisions explicitly.

## Evidence record

Retain source identifiers, status metadata, a draft-to-RFC change assessment, test and interoperability results, registry checks, errata disposition, compatibility exceptions, approval, and review date. Evidence should state which claims come from a draft and which come from a published RFC.

## Failure modes

- Citing an expired Internet-Draft as a final standard misstates its status.
- Tracking “latest draft” without a revision makes behavior irreproducible.
- Treating all RFCs as Internet Standards loses meaningful publication categories.
- Replacing a draft citation with an RFC number without a change review can conceal behavioral differences.
- Ignoring updates, obsoletion, or errata leaves an apparently stable citation operationally stale.
- Assuming publication means every peer has migrated can break interoperability.

## Sources

- RFC 9000, QUIC: A UDP-Based Multiplexed and Secure Transport: https://www.rfc-editor.org/rfc/rfc9000.html
- Internet-Draft `draft-ietf-quic-transport-34`: https://www.ietf.org/archive/id/draft-ietf-quic-transport-34.html
- IETF Datatracker: https://datatracker.ietf.org/
- RFC Editor: https://www.rfc-editor.org/

Sources were checked on September 1, 2026.

## Scope note

This article governs document-status, citation, and migration evidence. It does not declare protocol conformance, reproduce normative RFC text, or replace the IETF Datatracker, RFC Editor records, errata, or applicable specifications.
