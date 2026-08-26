# Synthetic content transparency control stack

**Issue:** A single watermark or detector is often treated as proof that content is AI-generated or authentic, even though each technique has distinct failure modes and can be removed, forged, or degraded.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use a layered transparency design for generated or transformed media. NIST AI 100-4 surveys provenance tracking, labeling/watermarking, detection, testing, and auditing; it does not justify treating any one signal as universally reliable.

## Control layers

- **Generation record:** capture model/service version, operation type, timestamp, policy context, and output digest without retaining unnecessary prompts or personal data.
- **Provenance:** attach cryptographically verifiable provenance where the format and distribution channel preserve it.
- **Disclosure:** present a clear user-facing label when content is generated or materially altered, including in accessible and text-only contexts.
- **Watermarking:** use only with measured robustness for expected edits, compression, screenshots, and transcoding.
- **Detection:** treat detector output as probabilistic evidence. Store confidence, model/version, calibration set, and decision threshold.
- **Policy enforcement:** require human review for high-impact decisions and prohibit detector-only adverse action.
- **Audit:** sample outputs, test metadata survival through the real publishing pipeline, and record false-positive/false-negative rates.
- **Incident response:** define correction, withdrawal, and notification steps for misleading or falsely labeled content.

## Verification

1. Build a representative evaluation set with generated, edited, and authentic content.
2. Test provenance and labels through export, CDN processing, social sharing, and format conversion.
3. Attempt stripping, copying, recompression, cropping, and screenshot attacks.
4. Evaluate detectors across languages, modalities, demographics, and post-processing relevant to the product.
5. Confirm logs minimize prompt, identity, and biometric data and follow retention policy.
6. Reassess after model or media-pipeline changes.

## Gotchas

- Absence of provenance is not proof of human origin.
- Presence of metadata is not proof unless authenticity and binding to content are verified.
- Detector confidence is not a calibrated probability unless demonstrated.
- Visible labels can be cropped; invisible signals can be destroyed.
- Transparency controls do not replace misuse prevention or content safety.

## Sources

- [NIST AI 100-4: Reducing Risks Posed by Synthetic Content](https://www.nist.gov/publications/reducing-risks-posed-synthetic-content-overview-technical-approaches-digital-content)
- [NIST report DOI](https://doi.org/10.6028/NIST.AI.100-4)
