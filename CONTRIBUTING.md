# Contributing to ORCHORDS Public Documentation

Thank you for helping improve the documentation.

## Before changing a document

1. Check whether the change is safe for a public repository.
2. Prefer primary, current sources for factual or standards-based claims.
3. Do not add product-specific architecture, infrastructure topology, secrets,
   customer information, private URLs, internal identifiers, or unannounced
   work.
4. Distinguish policy requirements from implemented controls.

## Workflow

1. Create or use an issue when the change is substantial.
2. Work on a branch.
3. Keep the change focused.
4. Run `python scripts/check_docs.py`.
5. Open a pull request.
6. Complete the pull-request evidence checklist.
7. Obtain review from the document owner.

## Commit messages

Use clear conventional prefixes when practical:

- `docs:` documentation content
- `policy:` policy change
- `sop:` procedure change
- `chore:` maintenance or automation

## Sources

When changing security, accessibility, engineering, or operational guidance,
prefer the sources in [REFERENCES.md](./REFERENCES.md). If a source is a draft,
state that explicitly.

## Security reports

Do not open a public issue for security-sensitive findings. Follow
[SECURITY.md](./SECURITY.md).
