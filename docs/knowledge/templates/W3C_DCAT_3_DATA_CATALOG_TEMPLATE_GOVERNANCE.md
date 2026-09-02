# W3C DCAT 3 Data Catalog Vocabulary Template Governance

## Purpose
Establish the governance pattern for templating dataset descriptions using the W3C Data Catalog Vocabulary (DCAT) 3 — including Dataset, Catalog, DataService, and Distribution classes — for the studio's public-facing and internal data catalogs.

## Scope
Applies to every dataset, data service, and distribution description that is published, indexed, or consumed through a studio-operated data catalog, regardless of the catalog's hosting technology.

## Workflow
1. Establish a DCAT 3 template with mandatory fields (dct:title, dct:description, dct:identifier) and recommended fields (dcat:keyword, dcat:theme, dct:issued, dct:modified, dcat:contactPoint).
3. Use controlled vocabularies for dcat:theme (e.g., EU Vocabularies Data Themes) and dcat:keyword (a curated term list) so cross-catalog discovery is possible.
5. For each dcat:Distribution, template mandatory fields (dcat:accessURL or dcat:downloadURL, dct:format, dct:license, dcat:mediaType) and reference the parent Dataset via dcat:distribution.
7. Validate each record against the DCAT 3 SHACL shapes prior to publication; reject records that fail validation.
9. Maintain a versioned profile of the template in the catalog registry with version, profile identifier, and SHACL conformance URL.

## Controls and evidence
- DCAT 3 template artefact with mandatory and recommended fields, mapped to controlled vocabularies.
- Validation report per dataset with SHACL conformance URL and result (pass/fail).
- Catalog profile with version, owner, last review date, and changelog.
- Quarterly cross-catalog reconciliation log verifying that downstream catalogs (e.g., open data portals) reflect the published DCAT 3 records.

## Validation
- Re-validate a sample of 10 datasets against the SHACL shapes and confirm zero validation errors.
- Confirm each record's dcat:contactPoint resolves to an active contact (e.g., mailto or URI).
- Verify the template profile version cited by each record matches the current registry version.

## Failure correction
- **SHACL validation failure on a published record** → retract the record from the catalog, fix the violation, re-validate, and republish.
- **Controlled vocabulary drift** → reconcile with the canonical vocabulary within 7 days, document the gap, and update the template.
- **Catalog profile out of date** → refresh the profile, document the staleness window, and notify downstream consumers.

## Limitations
- DCAT 3 builds on DCAT 2; some catalogs may still publish DCAT 2 records, requiring dual-templating during transition.
- SHACL validation is one form of quality control; downstream catalogs may impose additional quality checks.
- DCAT 3 does not define all metadata fields that may be required by sector-specific regulations (e.g., geospatial metadata per ISO 19115).

## Scope note
This article is part of the templates leaf. Cross-reference: OASIS_TOSCA_SIMPLE_PROFILE_TEMPLATE_GOVERNANCE.md, OGC_API_FEATURES_TEMPLATE_GOVERNANCE.md, IETF_RFC_8259_JSON_INTERCHANGE_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- W3C Data Catalog Vocabulary (DCAT) 3 — Recommendation: https://www.w3.org/TR/vocab-dcat-3/
- W3C DCAT 3 SHACL Shapes: https://w3c.github.io/dxwg/dcat-shapes/
- W3C Data Catalog Vocabulary (DCAT) — Version 2: https://www.w3.org/TR/vocab-dcat-2/
- EU Vocabularies — Data Themes: https://op.europa.eu/en/web/eu-vocabularies
- ISO 19115-1:2014 — Geographic information — Metadata: https://www.iso.org/standard/53798.html