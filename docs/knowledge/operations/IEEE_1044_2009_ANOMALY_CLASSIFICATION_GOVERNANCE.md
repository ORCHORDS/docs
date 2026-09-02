# IEEE 1044-2009 Anomaly Classification Governance

## Purpose

IEEE 1044-2009, "Standard Classification for Software Anomalies," provides a classification scheme for software anomalies (defects, errors, faults, failures) that supports consistent reporting, root cause analysis, and trend monitoring. The standard defines the anomaly type, the severity, the source, the disposition, and the relationships among anomalies. This article governs the application of IEEE 1044 so anomaly data is comparable across projects and over time.

## Scope

The standard applies to software anomaly classification. Within this knowledge base, the article covers the classification dimensions the standard defines (anomaly class, severity, source, disposition, status), the use of the classification in defect reports, the analysis of classified data, and the documentation of the classification scheme. It does not prescribe a defect-tracking tool.

## Workflow

1. Adopt the IEEE 1044 classification dimensions for the organization's defect reports:
   - Anomaly class: the functional category the anomaly affects (functional, performance, interface, etc.).
   - Severity: the impact the anomaly has on the user or system (critical, major, minor, cosmetic).
   - Source: where the anomaly was introduced (requirements, design, code, configuration, environment).
   - Disposition: what was done with the anomaly (fixed, deferred, cannot reproduce, not a defect).
   - Status: where the anomaly is in the work flow (open, in progress, resolved, closed).
2. Apply the classification when each anomaly is reported. The classification fields should be filled in by the reporter or the developer.
3. Use the classified data for analysis:
   - Trend by class, severity, and source to identify problem areas.
   - Defect arrival rate over time to assess stability.
   - Defect removal efficiency (defects found in test / total defects).
   - Root cause analysis for severe anomalies.
4. Document the classification scheme and the analysis methods.

## Controls and evidence

Classification evidence includes the defect reports with complete classifications, the trend reports, the root cause analyses, and the improvement actions. Each anomaly should have a complete classification; incomplete classifications reduce the value of the data.

## Validation

Validation should confirm the classification is applied consistently, the fields are complete, the analysis produces useful information, and the improvement actions follow from the analysis. Periodic audits of the classification data confirm completeness and consistency.

## Failure correction

Common failure modes: classifications are not applied or are assigned loosely (correct: enforce classification at reporting and review for consistency); analysis is performed but not acted on (correct: require an improvement action after each analysis); classifications do not distinguish root cause (correct: add a field for root cause and apply it consistently); defect data is not compared across releases (correct: track per-release defect data and compare).

## Limitations

IEEE 1044 is a classification scheme; it does not certify any defect data. The standard does not address all anomaly types (e.g., security vulnerabilities may need additional classification). The classification scheme depends on consistent application; without it, the data is unreliable.

## Scope note

This article summarizes project-neutral operations use of IEEE 1044-2009. It does not assert any specific project's anomaly classification conformance or claim any defect data certification.

## Canonical sources

- IEEE 1044-2009 — Standard Classification for Software Anomalies: https://standards.ieee.org/ieee/1044/4811/