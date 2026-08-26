# file-upload-security-pipeline

**Issue:** An application accepts user files — avatars, documents, imports, support attachments — and stores them under a web-served path. Attackers upload polyglot files, crafted images, or executable payloads with spoofed extensions and Content-Type headers, aiming for stored XSS via SVG/HTML, RCE via server-side processing bugs, path traversal via filenames, or persistent malware distribution to other users. Upload is one of the highest-leverage attack surfaces because a single weak handler turns a viewer into an attacker-controlled delivery channel.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Validation layers (defense in depth)

1. **Never trust the client-supplied filename or Content-Type.** The `Content-Type` header and browser-provided extension are attacker-controlled; both are advisory metadata, not evidence of file content.
2. **Verify magic bytes against a small allowlist.** Sniff the first bytes of the stream (e.g., `\x89PNG\r\n\x1a\n`, `%PDF-`, `\xFF\xD8\xFF`) and accept only signatures matching the permitted formats; reject anything with no signature or a mismatched extension/signature pair.
3. **Parse with the real codec and re-encode.** For images, decode with a hardened library and re-encode to a canonical output format; this strips embedded payloads, EXIF, and polyglot second streams that survive naive validation.
4. **Enforce extension and size allowlists server-side.** One list of extensions per upload purpose (e.g., `.png/.jpg/.webp` for avatars), a hard byte cap enforced while streaming (reject early, do not buffer then check), and rejection of double extensions like `.png.html`.
5. **Generate the stored filename yourself.** Discard the user filename entirely and store under a random UUID or content hash plus a fixed safe extension; the original name, if needed, lives in the database as data, never in filesystem paths.
6. **Reject archive and nested-container formats unless essential.** ZIPs enable zip-bomb decompression DoS and smuggle malicious nested files; if archives are required, scan nested entries, cap total uncompressed size, and reject encrypted or path-traversal entries (`../` names inside archives).

## Storage and serving rules

1. **Store uploads outside the web root or in object storage without public listing.** The upload destination must never execute or server-side process anything; if a misconfiguration re-enables script handling there, filenames you control keep the blast radius small.
2. **Serve downloads with an explicit, benign Content-Type and `Content-Disposition: attachment`.** Forcing `application/octet-stream` with attachment disposition prevents the browser from rendering uploaded HTML/SVG in your origin, which would be stored XSS.
3. **Serve user content from a separate origin.** A dedicated domain for uploads (different eTLD+1 or at least a distinct subdomain with isolated cookies) contains XSS and confines `document.domain` style attacks to a worthless origin.
4. **Set restrictive response headers on the upload path.** `X-Content-Type-Options: nosniff`, a tight `Content-Security-Policy` (e.g., `default-src 'none'`), and no cookies on the storage domain reduce the value of any bypass.
5. **Never pass user input into filesystem APIs unmodified.** Even with generated filenames, reject or neutralize `../`, absolute paths, null bytes, and overlong names at the boundary — belt and braces for the path-traversal class.
6. **Stream large files to final storage, never through the app server's memory or `/tmp` with predictable names.** Predictable temp names plus a local file inclusion bug is a classic RCE chain.

## Processing pipeline hardening

1. **Scan for malware before the file becomes retrievable.** Route uploads through ClamAV or a commercial ICAP/MDR scanner; quarantine or auto-delete positives and alert — do not store first and scan later.
2. **Run media processing in an isolated, resource-capped sandbox.** Image/PDF/video parsers are bug-dense; process in a container with no network, no credentials, CPU/memory/time limits, and a non-root user so a parser exploit is not instant compromise.
3. **Set per-user and global rate/size quotas.** Cap uploads per hour and total storage per account to blunt DoS and make mass malware staging visible in metrics.
4. **Process asynchronously with status polling.** Synchronous heavy parsing in the request thread invites timeout-based DoS; a queue also gives you one choke point to add scanning stages later.
5. **Log every upload's hash, size, verdict, and uploader.** Content hashes enable later abuse takedowns (find all users hosting the same malware) and forensic tracing.
6. **Re-scan retroactively when signature DBs update.** Files that passed scanning last week with yesterday's signatures should be re-checkable; store them retrievably keyed by hash to make sweeps cheap.

## Verification

1. **Upload theOWASP malicious-file corpus variants** — polyglots (`image.php.png` with PHP inside GIF magic bytes), SVGs with `<script>`, HTML with meta-refresh, EXIF-exploit JPEGs — and confirm every one is rejected or neutralized.
2. **Attempt filename traversal** (`../../etc/passwd`, null-byte `%00.png`, overlong names, unicode lookalikes) and verify stored paths are always server-generated.
3. **Fetch a stored upload as a browser and confirm behavior** — the response must download or render inertly on the isolated origin, never execute script or inherit session cookies.
4. **Verify a zip bomb** (nested or highly compressed archive) is rejected by uncompressed-size caps without exhausting memory or disk.
5. **Plant an EICAR test file through the pipeline** and confirm the scanner quarantines it end to end.

**Source:** [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html), [OWASP Unrestricted File Upload](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload), [OWASP WSTG — Test Upload of Malicious Files](https://www.owasp.org/www-project-web-security-testing-guide/v42/4-Web_Application_Security_Testing/10-Business_Logic_Testing/09-Test_Upload_of_Malicious_Files.html).
