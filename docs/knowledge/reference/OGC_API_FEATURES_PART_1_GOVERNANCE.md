# OGC API Features Part 1 Core Governance

## Purpose

OGC API Features Part 1: Core specifies a standard API for the creation, modification, and exchange of vector geospatial features. Governance ensures that an organization implementing or consuming an OGC API Features endpoint conforms to the core requirements, applies the resource model consistently, and documents extensions.

## Current context and source status

OGC API Features Part 1 was published by the Open Geospatial Consortium as OGC 19-086r6/ISO 19168. The current Part 1 is version 1.0.1. Additional parts (Part 2: Coordinate Reference Systems, Part 3: Filtering, Part 4: Create-Replace-Update-Delete) are published or in development. Verify the current OGC and ISO publications before treating any specific clause identifier as a current requirement.

## Governance workflow and controls

### 1. Apply the conformance classes

Apply the conformance classes defined in Part 1: Core, OpenAPI 3.0, GeoJSON, HTML. Conformance to each class is asserted through the API conformance declaration.

### 2. Apply the resource model

Apply the resource model: API, Collection, Feature. Use the prescribed endpoints for landing page, conformance, collections, collection, items, item.

### 3. Apply the query parameters

Apply the query parameters defined in Part 1 (limit, bbox, datetime, filter). Document the supported parameters per endpoint.

### 4. Document extensions

Document any extensions (additional parts or profile conformance classes). Provide documentation that follows the OGC extension pattern.

### 5. Manage coordinate reference systems

Manage coordinate reference systems (CRS) per Part 2. Document supported CRSes. Use the default CRS (WGS 84) unless otherwise required.

### 6. Manage access control

Apply access control per the organization's policy. Document the access model (anonymous, API key, OAuth 2.0). Verify that access control does not violate the conformance.

### 7. Validate conformance

Validate conformance using the OGC ETS or comparable. Document the conformance test results.

## Validation and evidence

- API conformance declaration.
- Endpoints documentation.
- CRS list.
- Conformance test results.

## Failure correction

Common defects include missing conformance declaration, undocumented extensions, and access control that violates conformance. Corrective actions include a conformance declaration review, an extension documentation requirement, and an access control review.

## Limitations

- Part 1 covers core; parts 2-4 address specific aspects.
- OGC API Features assumes HTTP-based APIs.
- CRS handling can be complex; validate per CRS.
- Conformance testing requires the OGC ETS or comparable.

## Canonical sources

- OGC, OGC API Features — Part 1: Core, current edition.
- OGC, OGC API Features — Part 2: Coordinate Reference Systems by Reference, current edition.
- OGC, OGC API Features — Part 3: Filtering, current edition.
- ISO 19168 (under revision), Geographic information — API for features.

## Scope note

This article belongs to the reference leaf and cross-references the engineering leaf for API implementation, the standards leaf for geospatial standards, and the operations leaf for API operations.
