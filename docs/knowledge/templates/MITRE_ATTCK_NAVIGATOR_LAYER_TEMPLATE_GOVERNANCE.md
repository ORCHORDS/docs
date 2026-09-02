# MITRE ATT&CK Navigator Layer Template Governance

## Purpose

MITRE ATT&CK Navigator is a web-based tool for visualizing, annotating, and sharing ATT&CK matrices. A reusable Navigator Layer template captures the layer metadata (name, description, domain, version), the technique selection (color, score, comment), the gradient or scoring scale, and the linkage to ATT&CK Campaigns, Threat Reports, or Detections. The template converts an organization's detection coverage or threat-informed defense position from an ad-hoc annotation into a versioned, reviewable artifact suitable for adversary-emulation planning, detection-gap analysis, and red/blue team exercises.

The template must remain generic: it MUST NOT embed real technique scoring that identifies a specific organization's detection maturity, nor real comments that disclose customer environments, internal IP ranges, or threat-actor attribution that has not been publicly disclosed.

## Scope

This template applies to ATT&CK Navigator layers authored against MITRE ATT&CK Enterprise, Mobile, or ICS matrices (current as of the September 2026 release). It does not address ATT&CK Workbench deployments or Navigator-Stix integrations, which require separate templates. The template does not substitute for a detection-rule catalog (Sigma, YARA, Splunk SPL, Elastic EQL); the rules are referenced from a separate catalog.

## Workflow

1. Open the template and complete the header with the layer name, the layer description, the domain (Enterprise, Mobile, ICS), the matrix version, the ATT&CK version, the layer author, the layer creation date, and the layer version.
2. Define the layer metadata: domain, platform restrictions (Windows, macOS, Linux, AWS, Azure, GCP, Kubernetes, Office 365, SaaS, Containers, Network, PRE).
3. Define the technique selection:
   - For each ATT&CK technique (T-id), assign a color or score on the documented gradient.
   - For selected techniques, attach a comment explaining the rationale (detection rule, threat report reference, gap reason).
   - For visualization purposes, group techniques under Tactic overlays.
4. Define the gradient or scoring scale (for example 0 = no coverage, 1 = detection rule exists, 2 = detection rule validated, 3 = detection rule + alerting on telemetry quality).
5. Add metadata fields: filters, sorting, gradient palette, legend descriptions, external references.
6. Validate the layer JSON against the Navigator schema using the Navigator `validate-layer` API or the offline validator.
7. Save the layer JSON to the threat-informed defense repository with version control.
8. Reference the layer from the adversary-emulation plan, detection-gap report, or threat-intel assessment.

## Controls and evidence

- Header records name, description, domain, matrix, version, author, and date.
- Technique selection includes T-id, color or score, and comment.
- Gradient scale is defined and consistent across the layer.
- Comments are present for selected techniques.
- External references point to the underlying threat report or detection rule.

## Validation

- Layer JSON validates against the Navigator schema.
- Every selected T-id resolves to a current ATT&CK technique (not deprecated or revoked).
- Color or score is consistent with the gradient definition.
- Comments do not leak identifying information.
- The layer is reviewed by both the threat-intel and detection-engineering teams before publication.

## Failure correction

Common defects include selecting deprecated techniques without marking them, assigning inconsistent scores, and embedding identifying information in comments. Corrective actions include using the `att&ck-validator` or equivalent offline checker, normalizing the scoring rubric across teams, and routing comments through a review pass that strips identifying data.

## Limitations

- The template does not substitute for an automated detection-rule catalog.
- It does not address Navigator-Stix 2.1 export, which has a separate format.
- It does not cover ATT&CK Workbench integration; a separate template is required.
- It does not address the ATT&CK Flow visual format for adversary-emulation sequences.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **security** (detection engineering and threat-informed defense), **reference** (MITRE ATT&CK knowledge articles), **engineering** (Sigma and YARA rule governance), and **operations** (detection-rule catalog maintenance). The template should be used together with those sibling-leaf articles.

## Canonical sources

- MITRE ATT&CK Navigator GitHub repository (MITRE): https://github.com/mitre-attack/attack-navigator
- MITRE ATT&CK Matrix (MITRE): https://attack.mitre.org/
- MITRE ATT&CK Navigator layer schema (MITRE): https://github.com/mitre-attack/attack-navigator/blob/master/layers/LAYERFORMATv4.md

Sources were verified on September 1, 2026.
