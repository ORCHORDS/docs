---
title: "CycloneDX VEX Analysis Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# CycloneDX VEX Analysis Governance

## CycloneDX vulnerability model

CycloneDX JSON/XML BOMs identify components with `bom-ref`; vulnerability entries use `id`, `source`, optional `ratings`, `cwes`, `description`, `recommendation`, `advisories`, `affects`, and `analysis`. `affects[].ref` must resolve to the exact component or service `bom-ref`; affected version/range data narrows applicability. `analysis` carries `state`, `justification`, `response`, `detail`, and timestamps according to the pinned CycloneDX schema version.

Analysis state values in current schemas include `resolved`, `resolved_with_pedigree`, `exploitable`, `in_triage`, `false_positive`, and `not_affected`. Justifications explain why code is not affected; responses describe actions such as update, rollback, workaround, or monitoring. Validate enum availability against the exact schema—do not emit a value from a newer CycloneDX release into an older BOM.

```json
{"vulnerabilities":[{"id":"CVE-2026-1234","source":{"name":"NVD","url":"https://nvd.nist.gov/vuln/detail/CVE-2026-1234"},"affects":[{"ref":"pkg:npm/example@2.0.0"}],"analysis":{"state":"not_affected","justification":"code_not_reachable","detail":"Call graph review 2026-08-30; evidence CASE-42"}}]}
```

## Consumer and lifecycle tests

Stable `bom-ref` is essential; regenerate it deterministically or preserve a mapping when BOMs are merged. Test missing refs, duplicate refs, purl version mismatch, ranges, two VEX BOMs with conflicting analysis, and a newer document that narrows to one component. Keep scanner observations even when VEX sets not affected or false positive.

Validate with the official JSON/XML schema for the selected release and record serial number, BOM version, timestamp, author, document digest, and signature result. Define precedence using trusted issuer, subject specificity, creation time, and BOM version—not file arrival order. Reopen analysis after component digest/configuration, exposure, or advisory changes.

Monitor `in_triage` age, orphan affects refs, invalid enums, conflicts, and suppressed findings without evidence. Correct errors by issuing a new BOM version; do not mutate a signed document. Roll back consumer policy to “show finding” on ambiguity, which is safer than retaining an unsupported suppression.

## Sources

- [CycloneDX VEX](https://cyclonedx.org/capabilities/vex/)
- [Specifications](https://cyclonedx.org/specification/overview/)
