# ISO 32000-2:2024 PDF 2.0 Specification Template Governance

## Purpose

ISO 32000-2:2024, "Document management — Portable document format — Part 2: PDF 2.0," specifies PDF 2.0 as the successor to PDF 1.7 (which ISO 32000-1 standardized). PDF 2.0 maintains the core PDF structure (objects, file structure, document structure, cross-reference, trailer) and introduces improvements to encryption, signatures, annotations, accessibility, and tag structure. This article governs the application of ISO 32000-2 as a template for producing and validating PDF documents, including their conformance claims.

## Scope

The specification applies to any organization producing or processing PDF documents. Within this knowledge base, the article covers the PDF 2.0 object structure, the file structure, the document structure, the optional features (encryption, signatures, JavaScript, forms, multimedia, 3D), the accessibility (tagged PDF, structure tree), and the conformance levels the specification defines. It does not cover PDF viewers or producers specifically; the specification governs the file format.

## Workflow

1. Identify the PDF conformance level the organization's documents must meet. PDF 2.0 defines conformance for both producers and consumers (viewers).
2. Produce PDF documents in conformance with the ISO 32000-2 specification: object types, cross-reference tables, trailer, document structure, and the file structure.
3. Apply optional capabilities as needed:
   - Encryption: AES-256 with the ISO 32000-2 defined parameters; legacy RC4 is deprecated.
   - Digital signatures: use ISO 32000-2's signature dictionary structure and a trusted signing key.
   - Tagged PDF: include the structure tree and marked content for accessibility.
   - Forms: use the AcroForm or XFA structure the specification defines.
4. Validate produced PDFs against the specification using validators and against the conformance criteria the specification provides.
5. Document the conformance claims for the organization's PDFs.

## Controls and evidence

Conformance evidence includes the PDF produced (the artifact itself), the validation report (from a PDF validator against ISO 32000-2), the signature and encryption settings (where used), and the documentation of the producer's conformance level. Each artifact should be reviewable against the specification's conformance criteria.

## Validation

Validation should confirm PDFs are produced in conformance with the specification, optional capabilities are correctly implemented, validation against the specification passes, and the conformance claims are supported by the validation results. Sample-based testing across document types is appropriate.

## Failure correction

Common failure modes: PDFs are produced with deprecated features (corrective: update the producer to use PDF 2.0 and remove deprecated features); encryption is implemented incorrectly (corrective: use the ISO 32000-2 encryption parameters); tagged PDF is claimed but the structure tree is incomplete (corrective: validate the structure tree with an accessibility checker and remediate); signatures use weak algorithms (corrective: use approved algorithms and keys).

## Limitations

ISO 32000-2 is the format specification; it does not certify any specific producer or consumer. The specification does not address the substantive content of the PDF; that is governed by the document's content domain. The specification does not guarantee that a PDF is semantically correct or accessible; the producer must construct the structure tree and the tags correctly for accessibility claims.

## Scope note

This article summarizes project-neutral use of ISO 32000-2:2024 as a template. It does not assert any specific PDF producer's conformance or claim any certification outcome.

## Canonical sources

- ISO 32000-2:2024 — Document management — Portable document format — Part 2: PDF 2.0: https://www.iso.org/standard/63534.html