# OASIS SARIF 2.1.0 Platform Integration Governance

## Purpose

Govern the use of the Static Analysis Results Interchange Format (SARIF) v2.1.0 as the studio's canonical format for static analysis, security scanning, and code quality tool results, so that findings from heterogeneous tools flow into one pipeline, are deduplicated by stable identity, and are triaged in one place regardless of which tool produced them.

## Scope

Applies to every analysis tool integrated into studio CI or developer workflows that emits findings: SAST, dependency scanning, secret scanning, linters, and infrastructure-as-code analyzers. Covers SARIF output requirements, result identity, severity mapping, and ingestion pipeline behavior. Does not cover triage policy by severity (covered by vulnerability management guidance) or the scanning tools themselves.

## Workflow

1. Require SARIF 2.1.0 output from every findings-producing tool where the tool supports it; tools without SARIF support are wrapped with a converter that produces conformant SARIF, or phased out.
2. Emit stable result identities: every result carries `ruleId` (and `ruleIndex` where applicable); results lacking a stable rule identity cannot be tracked across runs and are treated as a tool defect.
3. Include locations with physical and logical coordinates (`physicalLocation` with file and line, `logicalLocations` where applicable) so results land in developer context; results without actionable locations are rejected at ingestion.
4. Map severity consistently into the studio's triage levels using `level` (error, warning, note, none) combined with any tool-specific security severity in `properties`; the mapping table is version-controlled.
5. Deduplicate at ingestion on tool + ruleId + location identity so the same finding from overlapping tools does not create duplicate work items.
6. Preserve full run metadata: tool name and version, invocation, and `originalUriBaseIds` so that results remain interpretable after repository evolution.
7. Version the pipeline's SARIF schema handling; when SARIF 2.2 or later is adopted, migrate deliberately with a compatibility window rather than a hard cutover.

## Controls and evidence

- Tool integration register listing each tool's SARIF conformance, converter status, and severity mapping version.
- Deduplication rule specification (tool + ruleId + location) with examples.
- Ingestion rejection logs showing results rejected for missing identity or location, by tool.
- SARIF schema version handling record and migration plan.

## Validation

- Sample 10 ingested results and confirm each has a stable ruleId and a resolvable physical location.
- Confirm a deliberately injected duplicate (same tool, rule, location across two runs) creates one work item, not two.
- Confirm every findings-producing tool in the register either emits native SARIF or has a converter in place.

## Failure correction

- **Tool emits results without stable identity** → file a tool defect, apply the converter path in the interim, and track upstream.
- **Duplicate work items from overlap** → fix the dedup key or the tools' overlapping scope, and merge the duplicates.
- **Location resolution broken after repository restructuring** → regenerate `originalUriBaseIds` handling and re-baseline open findings to their new locations.

## Limitations

- SARIF normalizes representation, not semantics: two tools' "high severity" findings differ in meaning; the mapping layer exists for this reason and needs maintenance.
- Not all analysis dimensions fit SARIF's model (e.g., whole-program properties); those flow as supplementary evidence.
- Ingestion quality depends on tool output quality; wrapping poor tools adds conversion maintenance.

## Scope note

This article is part of the platforms leaf. Cross-reference: `code-scanning-codeql-custom-queries.md` (platforms/github), `CNCF_TRIVY_VULNERABILITY_SCANNING_GOVERNANCE.md` (operations leaf), and `FIRST_CVSS_V4_0_SCORING_GOVERNANCE.md` (security leaf).

## Canonical sources

- OASIS — Static Analysis Results Interchange Format (SARIF) v2.1.0: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
- OASIS — SARIF TSC and errata: https://www.oasis-open.org/committees/tc_home.php?wg_abbrev=sarif
- GitHub — SARIF support for code scanning: https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning
- IETF RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax: https://datatracker.ietf.org/doc/html/rfc3986
- OWASP — Vulnerability management guidance: https://owasp.org/www-community/vulnerabilities/
