![ORCHORDS](assets/orchords-logo.svg)

# Contributing to ORCHORDS Public Documentation

**Independent software studio founded in 2025.**

## Before changing a document

1. Check whether the change is safe for a public repository.
2. Prefer primary, current sources for factual or standards-based claims.
3. Check existing related files first and avoid duplicate or near-duplicate pages.
4. Do not add product-specific architecture, infrastructure topology, secrets, customer information, private URLs, internal identifiers, or unannounced work.
5. Distinguish policy requirements from implemented controls.
6. Place controlled documents in the category that owns the subject rather than adding unnecessary root-level policy files.

## Workflow

Authorized routine documentation maintenance is performed directly on **`main`**.

- Do not create feature branches or pull requests for routine documentation growth or maintenance.
- Keep each change narrow and evidence-based.
- Run the repository documentation checks when available.
- Re-read the affected category README/index after adding a page and keep it synchronized.
- Recompute numeric inventory claims from repository contents; do not copy stale totals forward.
- Review every change for credentials, private identifiers, customer/internal data, and other sensitive material before commit.

## Commit messages

Use clear conventional prefixes when practical:

- `docs:` documentation content
- `policy:` policy change
- `sop:` procedure change
- `chore:` maintenance or automation

## Sources

When changing policy or standards-based guidance, prefer the sources in the [Standards and Guidance Register](./standards/REFERENCES.md). If a source is a draft, state that explicitly.

## Security reports

Do not open a public issue for security-sensitive findings. Follow [SECURITY.md](./SECURITY.md).
