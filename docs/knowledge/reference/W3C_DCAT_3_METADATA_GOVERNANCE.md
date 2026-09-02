# W3C DCAT 3 Data Catalog Metadata Governance

## Purpose

W3C Data Catalog Vocabulary (DCAT) 3 is a vocabulary for describing datasets and data services in catalogs. Governance ensures that an organization publishing or consuming catalog metadata uses DCAT 3 consistently, that vocabulary elements are selected with documentation, and that catalog records enable discovery and integration.

## Current context and source status

W3C published DCAT 3 as a W3C Recommendation in 2024, replacing DCAT 2. DCAT 3 extends DCAT 2 with profiles, dataset series, versioning, and additional properties. Verify the current DCAT 3 Recommendation status before treating any specific element as a current requirement.

## Governance workflow and controls

### 1. Identify scope

Identify the cataloging scope: which datasets, which services, which access mechanisms, which organizations. Document the scope.

### 2. Apply DCAT 3 classes and properties

Apply DCAT 3 classes (Catalog, Dataset, Distribution, DataService, DatasetSeries, CatalogedResource) and properties (dcat:title, dcat:description, dcat:keyword, dcat:theme, dcat:distribution, dcat:contactPoint, dcterms:license, dcterms:publisher, dcat:qualifiedRelation).

### 3. Apply DCAT 3 profiles

DCAT 3 supports profiles. Apply the appropriate profile (for example, the European Data Portal's DCAT-AP). Document the profile choice.

### 4. Document versioning

Document dataset versioning using dcat:version and dcat:hasVersion. Document the relationship between versions and series.

### 5. Document access

Document access mechanisms (download URL, API endpoint, restricted access). Document the license and the rights statement.

### 6. Document quality

Document dataset quality using dqv:QualityMeasurement or profile-specific quality properties. Document conformance with quality standards.

### 7. Validate

Validate catalog records against DCAT 3 (or the chosen profile) using SHACL or similar validation tools.

## Validation and evidence

- DCAT catalog records.
- Profile documentation.
- Validation reports.

## Failure correction

Common defects include missing required properties, inconsistent profile application, and invalid records. Corrective actions include a completeness check, a profile review, and a validation pipeline.

## Limitations

- DCAT 3 is a vocabulary, not a system; tooling support varies.
- Profiles may impose additional requirements; track the chosen profile.
- Versioning semantics may differ between catalogs.
- Quality measurement is profile-dependent.

## Canonical sources

- W3C, Data Catalog Vocabulary (DCAT) 3, Recommendation, 2024.
- W3C, DCAT 3 Profile guidance, current edition.

## Scope note

This article belongs to the reference leaf and cross-references the engineering leaf for data engineering, the standards leaf for metadata standards, and the operations leaf for catalog operations.
