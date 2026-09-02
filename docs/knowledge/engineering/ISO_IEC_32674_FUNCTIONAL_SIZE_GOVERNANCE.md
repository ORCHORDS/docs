# ISO/IEC 32674 Functional Size Measurement Methodology Governance

## Purpose

ISO/IEC 32674 defines a generic functional size measurement method for software. Functional size measurement supports estimation, productivity analysis, and benchmarking. Governance ensures that an organization uses a consistent functional size measurement method, applies it to comparable scope, and uses the results appropriately.

## Current context and source status

ISO/IEC 32674 was published in 2022 as the first edition. The standard provides a measurement framework that supports multiple functional size methods, including IFPUG Function Point Analysis, COSMIC Function Points, and others. Verify the current ISO/IEC 32674 publication before treating any specific clause as a current requirement.

## Governance workflow and controls

### 1. Select a functional size method

Select a functional size method (IFPUG, COSMIC, NESMA, FiSMA, or comparable). Document the choice. Different methods produce different size values; compare within method.

### 2. Apply ISO/IEC 32674 framework

Apply the ISO/IEC 32674 framework: purpose, scope, audience, definitions, measurement process, method usage, output.

### 3. Train measurers

Train measurers on the chosen method. Apply a certification exercise before production sizing.

### 4. Establish sizing scope

Establish the sizing scope per project (logical boundary, functional user requirements, level of decomposition). Document the scope.

### 5. Apply consistent measurement

Apply consistent measurement across projects. Maintain a sizing glossary and decision log.

### 6. Use sizing in estimation

Use sizing in estimation. Combine with effort drivers (product, platform, personnel, project). Calibrate the estimation model.

### 7. Maintain sizing database

Maintain a sizing database. Use for benchmarking and trend analysis.

## Validation and evidence

- Sizing procedure documentation.
- Measurer certification records.
- Sizing database.
- Estimation model calibration.

## Failure correction

Common defects include inconsistent sizing across measurers, missing estimation calibration, and sizing scope drift. Corrective actions include a measurer calibration exercise, an estimation model refresh, and a scope verification check.

## Limitations

- Different methods produce different size values; comparisons across methods are not direct.
- Functional size does not capture all project attributes; supplement with other measures.
- Measurement requires expertise; measurer turnover affects consistency.
- Sizing may not capture emergent complexity; re-validate as scope evolves.

## Canonical sources

- ISO/IEC 32674:2022, Software engineering — Measurement and analysis — Common framework for the measurement method of functional size, first edition.
- ISO/IEC 14143 series, Software and systems engineering — Software measurement — Functional size measurement.
- IFPUG, Function Point Counting Practices Manual, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the standards leaf for measurement standards, the operations leaf for productivity analysis, and the business leaf for project estimation.
