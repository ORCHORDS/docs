# Secure File Ingestion for Agent Workflows

## Scope

Agents ingest files for summarization, retrieval, extraction, transformation, and tool use. A file crosses several boundaries: upload transport, metadata handling, object storage, decompression, parser execution, indexing, model context, and generated download. OWASP's File Upload Cheat Sheet emphasizes defense in depth because extension or content-type checks alone cannot establish safety.

This article covers files entering an agent system. It is distinct from workspace change review: the concern is hostile or malformed content, parser exploitation, resource exhaustion, unauthorized disclosure, and unsafe publication. Instructions embedded in a valid document remain untrusted content even after malware checks pass.

## Implementation workflow

Define an intake policy per capability: allowed business purpose, formats, maximum compressed and expanded size, page or object count, encryption policy, retention, and downstream parsers. Prefer a small allowlist. If the use case needs text, consider converting supported formats to a constrained intermediate representation rather than exposing original files to every component.

Receive uploads into quarantine outside executable and public web roots. Generate a random storage identifier; retain the original name only as encoded display metadata. Validate transport limits before buffering the full body. Check extension after canonicalizing the name, inspect declared content type only as a hint, and verify file signatures and structural parsing with maintained libraries.

Scan with available anti-malware controls and apply content disarm and reconstruction where appropriate to the format and risk. Decompress in an isolated worker with CPU, memory, nesting, file-count, and expanded-byte limits. Reject path traversal, absolute paths, links, device names, and duplicate-entry ambiguities in archives. Never extract over an existing directory.

After validation, create a derived safe object for indexing or rendering and preserve provenance to the quarantined source according to retention policy. Mark extracted text as untrusted when inserted into agent context. Apply authorization at retrieval time; possession of an opaque object ID must not grant access.

## Controls

Use separate identities for upload, scanning, conversion, indexing, and serving. Parsers run without network access or business credentials in a sandboxed environment. Keep libraries patched and remove unused format handlers. Disable macros, scripts, external entity resolution, remote resource loading, and active content unless a narrowly reviewed capability requires them.

Serve approved downloads from a separate origin or attachment endpoint with fixed content-disposition and safe content-type headers. Prevent user-controlled names from becoming response headers. Encrypt storage as required, use per-tenant authorization, and expire temporary artifacts. Do not place raw document text in ordinary logs or telemetry.

Protect availability with quotas per user and tenant, queue limits, cancellation, and deduplication that does not leak whether another tenant uploaded the same file. Hashes can support integrity and internal correlation but are not malware verdicts.

## Validation evidence

Test permitted samples and adversarial cases: double extensions, mixed case, null and control characters, misleading MIME types, polyglots, malformed containers, nested archives, zip bombs, traversal names, symlinks, password-protected files, macro-enabled documents, external references, oversized images, parser timeouts, and duplicate archive entries. Use safe test corpora and isolated infrastructure.

Evidence includes policy versions, scanner and parser versions, quarantine access rules, sandbox network tests, resource-limit results, provenance records, authorization tests, serving headers, retention deletion checks, and failure telemetry. Verify that no index entry becomes searchable before the entire required pipeline succeeds. Confirm that replacing a source invalidates or versions all derivatives.

## Failure handling

On validation, scanning, conversion, or policy failure, keep the object quarantined or delete it according to incident and evidence policy; never partially publish extracted content. Return a generic reason category without exposing scanner internals. Exhausted workers should terminate the job and clean temporary files through an out-of-process supervisor.

If a malicious file reaches downstream systems, stop retrieval and serving, revoke derived objects and index entries, identify every parser and reviewer exposed, and preserve minimal forensic evidence. Patch or reconfigure the vulnerable stage, reprocess only from trusted originals, and add the sample or a safe surrogate to regression tests.

## Canonical sources

- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP XML External Entity Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html
- NIST Secure Software Development Framework 1.1: https://doi.org/10.6028/NIST.SP.800-218
