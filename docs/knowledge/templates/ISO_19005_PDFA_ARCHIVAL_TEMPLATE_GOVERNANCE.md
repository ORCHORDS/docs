# ISO 19005 PDF/A Archival Template Governance

## Purpose

Long-term preservation of documents in electronic form requires a file format whose rendering and structure can be reproduced far into the future, independent of the tools that created the file. ISO 19005 ("Document management — Electronic document file format for long-term preservation"), commonly called PDF/A, defines constrained profiles of PDF for this purpose. A PDF/A conforming file embeds its fonts, colour data, and where required its structure, so that it renders identically without external dependencies.

This article provides a public, project-neutral method for governing an archival document template that produces PDF/A output: choosing the conformance level, controlling what goes into the source, validating output, and correcting failures. It does not certify any file as conforming; conformance is demonstrated by validation against the standard.

## Scope

The scope covers the PDF/A parts published as ISO 19005. Part 1 (PDF/A-1, based on PDF 1.4), Part 2 (PDF/A-2, based on ISO 32000-1), and Part 3 (PDF/A-3, which permits embedding arbitrary files), together with their levels and conformance levels. It covers:

- the distinction between conformance levels A (accessible, with structure and Unicode mapping), B (basic, visual reproduction), and U (Unicode-mapped text without full structure);
- the prohibition of features that compromise long-term reproduction: encryption, external content references, JavaScript, and multimedia, with the details differing by part;
- font embedding requirements, including the programs and character-to-unicode mappings needed to reproduce text;
- colour space requirements, including the embedding of ICC profiles where device-independent colour is required;
- XMP metadata, which carries the PDF/A identification and conformance claim;
- optional content, transparency, and the layered restrictions introduced by later parts; and
- the Part 3 allowance for arbitrary embedded files and the governance implications of using it.

## Workflow

Producing governed PDF/A output is a source-control and validation workflow, not a conversion afterthought:

1. **Select the part and conformance level.** Choose PDF/A-1, PDF/A-2, or PDF/A-3, and level A, B, or U, based on the preservation requirement. Level A adds tagged structure and full Unicode mapping, which supports accessibility and text extraction; level B guarantees visual reproduction only. PDF/A-3's embedded arbitrary files bring supply-chain risk and should be justified explicitly.
2. **Control the source document.** Decide what the template may contain: fonts (licensed for embedding), images (with colour profiles), vector graphics, and text. Exclude features the target part forbids, such as encryption, actions, and external references, at the template level rather than at conversion time.
3. **Declare fonts and colour.** Use fonts whose licences permit embedding and subset embedding, and attach ICC profiles where colour fidelity matters. Record the fonts and profiles used in the template so the conversion is reproducible.
4. **Add structure and tagging where required.** For level A, ensure the template produces tagged structure: headings, lists, tables, and reading order must be expressed in the tag tree, not merely rendered visually.
5. **Embed XMP metadata.** Ensure the XMP metadata carries the PDF/A identification, including the part and conformance level claimed, and that document-level metadata such as title, author, and creation date are populated consistently.
6. **Convert with a conforming producer.** Use a producer that writes the chosen profile. Record the producer and its version, because revalidation may be needed when the producer changes.
7. **Validate every file.** Validate each output file against the chosen profile with a validator that implements the standard's requirements. A file that fails validation is not PDF/A, whatever its extension or metadata claim.
8. **Store with preservation metadata.** Store validated files with fixity information (for example, cryptographic checksums) and record the validation result alongside the file.

## Controls and evidence

Evidence that PDF/A template governance operates correctly includes:

- the template definition, recording the target part and conformance level, permitted fonts, colour profiles, and content types;
- the list of fonts used, with confirmation that their licences permit embedding;
- producer configuration and version, recorded for reproducibility;
- validation reports for each produced file, showing the validator, its version, and the result;
- fixity records (checksums) stored with each archived file, supporting later integrity verification;
- for level A, tag-tree checks demonstrating structure and reading order are present and meaningful; and
- for PDF/A-3, an inventory of embedded files with justification for each.

## Validation

A governed PDF/A output is validated by:

- profile validation against the requirements of the selected part and conformance level, using an independent validator rather than the producer alone;
- font checks confirming all fonts are embedded with the programs and mappings required;
- colour checks confirming colour data is device-independent or accompanied by the required ICC profiles;
- metadata checks confirming XMP carries the correct PDF/A identification and the claimed conformance level;
- rendering comparison across independent PDF readers, confirming visual reproduction without the originating application;
- text-extraction checks, for level U and A, confirming the text maps to Unicode correctly; and
- fixity verification at defined intervals, confirming archived files are unchanged.

## Failure correction

Common failure modes in PDF/A governance include:

- **Producer claims without independent validation.** The corrective action is to validate every file with an independent validator and to reject files that fail, regardless of producer claims.
- **Missing font embedding.** The corrective action is to restrict the template to embeddable fonts and to fail the build when a font cannot be embedded.
- **Level B chosen where extraction is needed.** The corrective action is to move to level U or A, add Unicode mappings, and re-convert the affected corpus.
- **PDF/A-3 used for convenience.** The corrective action is to inventory and justify embedded files, and to move to PDF/A-2 where attachment is unnecessary.
- **Validation not retained.** The corrective action is to store the validation report and checksum alongside each file so later verification has a baseline.

## Limitations

PDF/A guarantees reproducible rendering and, at levels U and A, reliable text extraction. It does not guarantee semantic correctness, legal admissibility, or fitness for a given business purpose. PDF/A does not itself manage retention: disposition, legal hold, and records scheduling remain the province of records-management standards such as ISO 15489 and organisational policy. Later parts relax or change earlier restrictions, so a corpus may mix parts; migration between parts should be planned rather than accidental. Validation depends on the validator's fidelity to the standard, so validator choice and version are part of the evidence. Finally, PDF/A does not preserve the originating application's editable form: the archival copy is a fixed rendition, and source formats must be preserved separately where re-editing is required.

## Canonical sources

- ISO — ISO 19005-2:2011, Document management — Electronic document file format for long-term preservation — Part 2: Use of ISO 32000-1 (PDF/A-2): https://www.iso.org/standard/50655.html
- ISO — ISO 19005-1:2005, Document management — Electronic document file format for long-term preservation — Part 1: Use of PDF 1.4 (PDF/A-1): https://www.iso.org/standard/38912.html
- Library of Congress — PDF/A Format Description (sustainability factors): https://www.loc.gov/preservation/digital/formats/fdd/fdd000125.shtml

## Scope note

This article describes project-neutral governance of PDF/A archival templates. It does not certify any file as conforming and does not replace the published standard's normative requirements or the use of a conformant validator.
