# OASIS SARIF 2.1 Static Analysis Results Governance

## Purpose

OASIS Static Analysis Results Interchange Format (SARIF) 2.1 is a JSON-based format for the output of static analysis tools. Governance ensures that an organization uses SARIF for static analysis result interchange, that the SARIF output is validated, and that the results are integrated into the engineering workflow.

## Current context and source status

OASIS published SARIF 2.1 as an OASIS Standard in 2023, replacing SARIF 2.1.0. SARIF 2.1 is widely adopted by static analysis tools, IDEs, and code review platforms. Verify the current OASIS publication before treating any specific SARIF property as a current requirement.

## Governance workflow and controls

### 1. Use SARIF for static analysis output

Configure static analysis tools to emit SARIF. Document the supported SARIF version per tool.

### 2. Validate SARIF output

Validate SARIF output against the SARIF schema. Document validation results.

### 3. Integrate with engineering tools

Integrate SARIF output with code review platforms (GitHub code scanning, GitLab code quality), IDEs, and dashboards.

### 4. Define severity mapping

Define severity mapping between tool-specific severities and the organization's severity levels. Apply consistently.

### 5. Apply suppression and baseline

Apply suppression and baseline per the SARIF suppression model. Document the baseline. Re-evaluate baseline periodically.

### 6. Use runs and results

Use SARIF runs, results, rules, locations, fixes, and code flows. Document each finding with sufficient context for triage.

### 7. Apply invocations and tool metadata

Apply SARIF invocations and tool metadata. Track tool versions and configurations.

## Validation and evidence

- SARIF output from each tool.
- Validation reports.
- Integration with code review and dashboards.

## Failure correction

Common defects include missing tool metadata, inconsistent severity mapping, and stale baselines. Corrective actions include a metadata completeness check, a severity mapping review, and a baseline re-evaluation cadence.

## Limitations

- SARIF is a format; integration with specific tools requires their SARIF support.
- SARIF output size can be large; apply filtering.
- Some tools emit SARIF 1.0 or non-standard extensions; verify version compatibility.
- SARIF supports suppression but does not enforce suppression policy.

## Canonical sources

- OASIS, Static Analysis Results Interchange Format (SARIF) Version 2.1, OASIS Standard, 2023.

## Scope note

This article belongs to the reference leaf and cross-references the engineering leaf for static analysis, the security leaf for application security testing, and the operations leaf for build automation.
