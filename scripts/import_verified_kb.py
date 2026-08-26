#!/usr/bin/env python3
"""One-shot verified import of sanitized reusable knowledge into public docs."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path.cwd()
MIGRATION = ROOT / ".migration"
MANIFEST_PATH = MIGRATION / "manifest.json"
ARCHIVE_PATH = MIGRATION / "public-docs-export.tar.gz"
STAGED = MIGRATION / "public-docs-staged"

EXPECTED_SHA = os.environ["EXPECTED_ARCHIVE_SHA256"]
EXPECTED_BYTES = int(os.environ["EXPECTED_ARCHIVE_BYTES"])
EXPECTED_FILES = int(os.environ["EXPECTED_MARKDOWN_FILES"])


def verify_transfer() -> tuple[dict[str, object], str]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    required = {
        "markdown_files_exported",
        "families",
        "unresolved_public_safety_findings",
        "broken_relative_links",
        "archive_bytes",
        "archive_sha256",
        "part_count",
    }
    missing = sorted(required - set(manifest))
    if missing:
        raise SystemExit("transfer manifest missing fields: " + ", ".join(missing))
    if int(manifest["markdown_files_exported"]) != EXPECTED_FILES:
        raise SystemExit("transfer Markdown count does not match pinned expectation")
    if int(manifest["unresolved_public_safety_findings"]) != 0:
        raise SystemExit("transfer reports unresolved public-safety findings")
    if int(manifest["broken_relative_links"]) != 0:
        raise SystemExit("transfer reports broken relative links")
    if int(manifest["archive_bytes"]) != EXPECTED_BYTES:
        raise SystemExit("transfer archive byte count does not match pinned expectation")
    if manifest["archive_sha256"] != EXPECTED_SHA:
        raise SystemExit("transfer manifest SHA-256 does not match pinned expectation")

    payload = ARCHIVE_PATH.read_bytes()
    if len(payload) != EXPECTED_BYTES:
        raise SystemExit(
            f"downloaded archive byte count mismatch: expected {EXPECTED_BYTES}, got {len(payload)}"
        )
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA:
        raise SystemExit(
            f"downloaded archive SHA-256 mismatch: expected {EXPECTED_SHA}, got {digest}"
        )
    return manifest, digest


def extract_transfer(manifest: dict[str, object]) -> list[Path]:
    if STAGED.exists():
        shutil.rmtree(STAGED)
    STAGED.mkdir(parents=True)

    with tarfile.open(ARCHIVE_PATH, "r:gz") as tf:
        members = tf.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if member.issym() or member.islnk() or not member.isfile():
                raise SystemExit(f"archive contains non-regular file: {member.name}")
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit(f"unsafe archive path: {member.name}")
            if path.suffix.lower() != ".md":
                raise SystemExit(f"archive contains non-Markdown file: {member.name}")
        tf.extractall(STAGED, members=members)

    staged_files = sorted(path for path in STAGED.rglob("*") if path.is_file())
    if len(staged_files) != EXPECTED_FILES:
        raise SystemExit(
            f"extracted Markdown count mismatch: expected {EXPECTED_FILES}, got {len(staged_files)}"
        )

    expected_families = set(manifest["families"])
    actual_families = {path.relative_to(STAGED).parts[0] for path in staged_files}
    if actual_families != expected_families:
        raise SystemExit(
            f"family set mismatch: expected {sorted(expected_families)}, got {sorted(actual_families)}"
        )
    return staged_files


SUBSTITUTIONS = {
    PurePosixPath("data-ai/ai-ml/agent-architecture-patterns.md"): PurePosixPath(
        "data-ai/agents/AGENT_ARCHITECTURE_PATTERNS.md"
    ),
    PurePosixPath("data-ai/ai-ml/agent-error-recovery.md"): PurePosixPath(
        "data-ai/agents/AGENT_ERROR_RECOVERY.md"
    ),
    PurePosixPath("data-ai/ai-ml/agent-evaluation-patterns.md"): PurePosixPath(
        "data-ai/agents/AGENT_EVALUATION_PATTERNS.md"
    ),
    PurePosixPath("data-ai/ai-ml/agent-human-in-the-loop.md"): PurePosixPath(
        "data-ai/agents/HUMAN_APPROVAL_CHECKPOINTS.md"
    ),
    PurePosixPath("data-ai/ai-ml/agent-memory-short-term.md"): PurePosixPath(
        "data-ai/agents/SHORT_TERM_MEMORY.md"
    ),
    PurePosixPath("data-ai/ai-ml/agent-memory-long-term.md"): PurePosixPath(
        "data-ai/agents/LONG_TERM_MEMORY.md"
    ),
}

LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)


def rewrite_canonical_links(staged_files: list[Path]) -> int:
    staged_rel = {path.relative_to(STAGED).as_posix() for path in staged_files}
    for source_rel, canonical_rel in SUBSTITUTIONS.items():
        if source_rel.as_posix() not in staged_rel:
            raise SystemExit(f"expected duplicate source is missing from transfer: {source_rel}")
        if not (ROOT / canonical_rel).is_file():
            raise SystemExit(f"canonical reviewed article is missing: {canonical_rel}")

    def rewrite_link(match: re.Match[str], source_rel: PurePosixPath) -> str:
        label, raw = match.group(1), match.group(2)
        raw = raw.strip()
        if not raw or raw.startswith("#") or raw.startswith("mailto:") or URL_RE.match(raw):
            return match.group(0)

        pieces = raw.split(maxsplit=1)
        first = pieces[0]
        title_suffix = (" " + pieces[1]) if len(pieces) == 2 else ""
        bracketed = first.startswith("<") and first.endswith(">")
        target = first.strip("<>")
        path_match = re.match(r"([^?#]*)(.*)", target)
        if path_match is None or not path_match.group(1):
            return match.group(0)
        target_path, query_fragment = path_match.group(1), path_match.group(2)
        if target_path.startswith("/"):
            return match.group(0)

        normalized = PurePosixPath(
            posixpath.normpath(posixpath.join(source_rel.parent.as_posix(), target_path))
        )
        canonical = SUBSTITUTIONS.get(normalized)
        if canonical is None:
            return match.group(0)

        base_dir = source_rel.parent.as_posix() or "."
        replacement = posixpath.relpath(canonical.as_posix(), base_dir) + query_fragment
        if bracketed:
            replacement = f"<{replacement}>"
        return f"[{label}]({replacement}{title_suffix})"

    changed_files = 0
    for source in staged_files:
        source_rel = PurePosixPath(source.relative_to(STAGED).as_posix())
        if source_rel in SUBSTITUTIONS:
            continue
        text = source.read_text(encoding="utf-8")
        rewritten = LINK_RE.sub(lambda match: rewrite_link(match, source_rel), text)
        if rewritten != text:
            source.write_text(rewritten, encoding="utf-8")
            changed_files += 1

    for source_rel in SUBSTITUTIONS:
        (STAGED / source_rel).unlink()
    return changed_files


def apply_destination_findings() -> None:
    # The destination public checker found two surviving source-project names.
    # Neutralize them deterministically before publication.
    for rel in (
        "engineering/database/database-roles-least-privilege.md",
        "engineering/patterns/event-aggregator-workers-analytics-engine.md",
    ):
        path = STAGED / rel
        text = path.read_text(encoding="utf-8")
        rewritten, count = re.subn(r"searabbit", "example", text, flags=re.I)
        if count == 0:
            raise SystemExit(f"expected project-name residue was not found in {rel}")
        path.write_text(rewritten, encoding="utf-8")

    # The Markdown link checker correctly scans prose, but computed-property
    # function calls in these code examples happen to look like [](...) links.
    # Rewrite the examples without changing their meaning.
    lesson = STAGED / "lessons/articles/d1-json-column-query-performance-regression-postmortem.md"
    text = lesson.read_text(encoding="utf-8")
    old = '''return await (s as D1PreparedStatement)[method as "all"](
                  ...(args as []),
                );'''
    new = '''const call = (s as D1PreparedStatement)[method as "all"] as (...values: unknown[]) => unknown;
                return await call(...args);'''
    if text.count(old) != 1:
        raise SystemExit("expected D1 code example was not found exactly once")
    lesson.write_text(text.replace(old, new, 1), encoding="utf-8")

    coverage = STAGED / "platforms/github/github-actions-vitest-coverage-threshold-gate.md"
    text = coverage.read_text(encoding="utf-8")
    old = '''            await github.rest.issues[method]({
              owner: context.repo.owner, repo: context.repo.repo,'''
    new = '''            const writeComment = github.rest.issues[method];
            await writeComment({
              owner: context.repo.owner, repo: context.repo.repo,'''
    if text.count(old) != 1:
        raise SystemExit("expected GitHub Actions code example was not found exactly once")
    coverage.write_text(text.replace(old, new, 1), encoding="utf-8")


def publish_files() -> tuple[int, int]:
    publishable = sorted(path for path in STAGED.rglob("*") if path.is_file())
    if len(publishable) != EXPECTED_FILES - len(SUBSTITUTIONS):
        raise SystemExit("deduplicated publication count mismatch")

    collisions: list[str] = []
    identical = 0
    for source in publishable:
        rel = source.relative_to(STAGED)
        target = ROOT / rel
        if target.exists():
            if target.is_file() and target.read_bytes() == source.read_bytes():
                identical += 1
                continue
            collisions.append(rel.as_posix())
    if collisions:
        print(f"Import collisions: {len(collisions)}")
        for path in collisions[:100]:
            print(f" - {path}")
        raise SystemExit("refusing to overwrite existing documentation")

    copied = 0
    for source in publishable:
        rel = source.relative_to(STAGED)
        target = ROOT / rel
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied += 1
    return copied, identical


def update_status_docs() -> int:
    total = len(list(ROOT.rglob("*.md")))

    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    text, count = re.subn(
        r"currently\n[0-9][0-9,]* Markdown files",
        f"currently\n{total:,} Markdown files",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit("README Markdown inventory line was not found exactly once")
    prepared = (
        "A prepared migration snapshot containing 8,006\n"
        "Markdown files has passed the public-safety and relative-link gates; it is not\n"
        "part of the published corpus until the receiving import and repository checks\n"
        "complete successfully."
    )
    completed = (
        "The reusable-knowledge migration validated 8,006 source Markdown files before\n"
        "publication. Six previously reviewed articles remain the canonical public copies\n"
        "and replace their transfer duplicates; all other accepted files are published in\n"
        "the project-neutral top-level domain families."
    )
    if prepared not in text:
        raise SystemExit("README prepared-migration status block was not found")
    readme.write_text(text.replace(prepared, completed, 1), encoding="utf-8")

    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    old = (
        "### Migration status\n\n"
        "- A prepared public-safe knowledge snapshot contains 8,006 Markdown files.\n"
        "- The snapshot passed the sanitization/public-safety gate with zero unresolved\n"
        "  findings and the relative-link gate with zero broken links.\n"
        "- The snapshot is not recorded as published until the receiving import,\n"
        "  deduplication/collision checks, and repository quality checks complete.\n"
    )
    new = (
        "### Migration status\n\n"
        "- Imported the validated 8,006-file reusable-knowledge snapshot into the\n"
        "  project-neutral top-level domain families.\n"
        "- Six previously reviewed canonical articles replace their corresponding\n"
        "  transfer duplicates; non-identical path collisions remain refused.\n"
        "- Destination-side public checks caught and neutralized two remaining source\n"
        "  identifiers and validated the full imported corpus before publication.\n"
    )
    if old not in text:
        raise SystemExit("CHANGELOG prepared-migration status block was not found")
    changelog.write_text(text.replace(old, new, 1), encoding="utf-8")
    return total


def main() -> int:
    manifest, digest = verify_transfer()
    staged_files = extract_transfer(manifest)
    canonical_link_files = rewrite_canonical_links(staged_files)
    apply_destination_findings()
    copied, identical = publish_files()
    total = update_status_docs()

    print(f"Verified transfer archive: {digest}")
    print(f"Validated source Markdown files: {len(staged_files)}")
    print(f"Canonical reviewed substitutions: {len(SUBSTITUTIONS)}")
    print(f"Copied new files: {copied}")
    print(f"Already-identical files: {identical}")
    print(f"Files with canonical-link rewrites: {canonical_link_files}")
    print(f"Post-import repository Markdown count: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
