<p align="center">
  <img src="./assets/1080x360.jpg" width="1080" alt="ORCHORDS — BUILD DIFFERENT.">
</p>

# Contributing to ORCHORDS Public Documentation

**Independent software studio founded in 2025.**

## Before changing a document

1. Check whether the change is safe for a public repository.
2. Prefer current primary or authoritative sources for factual or standards-based claims.
3. Check existing related files first and avoid duplicate or near-duplicate pages.
4. Do not add product-specific architecture, infrastructure topology, secrets, customer information, private URLs, internal identifiers, or unannounced work.
5. Distinguish policy requirements from implemented controls.
6. Keep controlled documents in the category or domain family that owns the subject.

## Workflow

Authorized routine maintenance is performed directly on **`main`**.

- No feature branches or PRs are required for routine documentation growth or maintenance.
- External contributions, larger structural changes, and automated dependency
  updates (Dependabot) use pull requests. A maintainer reviews them against
  this checklist before merge, and the documentation-quality workflow must pass.
- Keep changes narrow and evidence-based.
- Keep affected README/index files synchronized.
- Recompute numeric inventory claims from repository contents.
- Review every change for credentials, private identifiers, customer/internal data, and other sensitive material before commit.

## Bulk and imported knowledge

Do not directly copy a private, project-specific, or operational knowledge
base into this public repository.

Before a bulk import can be published:

1. Convert source material to project-neutral wording and remove private/source-specific repository names, paths, endpoints, identifiers, and operational context.
2. Scan every exported Markdown file for secrets, credentials, personal/customer data, internal infrastructure details, and other public-safety findings.
3. Check for duplicate or near-duplicate topics and refuse destination collisions.
4. Rewrite and validate relative Markdown links.
5. Verify the exported file count against a manifest.
6. Verify the reconstructed transfer with its expected cryptographic checksum.
7. Run the repository documentation-quality and public-neutrality checks on the complete receiving tree.
8. Treat a prepared or sanitized snapshot as **not published** until the receiving import and all required checks succeed.

## Reporting problems

Use the documentation-issue form for content problems (see
[SUPPORT.md](docs/reference/SUPPORT.md) for routing); security-sensitive findings go to
[SECURITY.md](SECURITY.md), never a public issue.

## Brand

**ORCHORDS — BUILD DIFFERENT.**
