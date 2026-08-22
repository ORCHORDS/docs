#!/usr/bin/env python3
"""Repository-local public documentation quality gate."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

CONTROLLED_DIRS = {"engineering", "operations", "product", "releases", "sop"}
CONTROLLED_ROOT = {
    "GOVERNANCE.md",
    "DOCUMENT_CONTROL.md",
    "REFERENCES.md",
    "STYLE_GUIDE.md",
    "ACCESSIBILITY_POLICY.md",
    "SECURITY_POLICY.md",
}

FORBIDDEN = {
    "mr.orchords",
    "mrorchords",
    "w.a.s.p",
    "thewam",
    "openfx",
    "directx",
    "ffmpeg",
    "firebase",
    "forgejo",
}

REQUIRED_FRONT_MATTER = {
    "title",
    "owner",
    "status",
    "classification",
    "last-reviewed",
    "review-cycle",
    "next-review",
}

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)


def is_controlled(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return rel.name in CONTROLLED_ROOT or (
        len(rel.parts) > 1 and rel.parts[0] in CONTROLLED_DIRS
    )


def parse_front_matter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def check_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for raw in LINK_RE.findall(text):
        target = raw.strip().split()[0].strip("<>")
        if not target or target.startswith("#") or target.startswith("mailto:"):
            continue
        if URL_RE.match(target):
            continue
        target = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(ROOT)
        except ValueError:
            errors.append(f"{path.relative_to(ROOT)}: link escapes repository: {raw}")
            continue
        if not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken relative link: {raw}")
    return errors


def main() -> int:
    errors: list[str] = []
    markdown = sorted(ROOT.rglob("*.md"))

    for path in markdown:
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        lower = text.lower()

        if "\t" in text:
            errors.append(f"{rel}: tab character found")
        for no, line in enumerate(text.splitlines(), 1):
            if line.rstrip() != line:
                errors.append(f"{rel}:{no}: trailing whitespace")

        for term in FORBIDDEN:
            if term in lower:
                errors.append(f"{rel}: forbidden project/implementation term: {term}")

        if "$title" in lower or "lorem ipsum" in lower:
            errors.append(f"{rel}: unresolved template placeholder")
        for token in ("todo", "tbd"):
            if re.search(rf"\b{token}\b", lower):
                errors.append(f"{rel}: unresolved placeholder token: {token}")

        if is_controlled(path):
            front_matter = parse_front_matter(text)
            if front_matter is None:
                errors.append(f"{rel}: controlled document missing YAML front matter")
            else:
                missing = sorted(REQUIRED_FRONT_MATTER - set(front_matter))
                if missing:
                    errors.append(f"{rel}: front matter missing: {', '.join(missing)}")
                if front_matter.get("classification") != "public":
                    errors.append(f"{rel}: classification must be public")
                if front_matter.get("status") not in {"approved", "review", "draft", "deprecated"}:
                    errors.append(f"{rel}: invalid status")

        errors.extend(check_links(path, text))

    if errors:
        print("Documentation quality checks failed:")
        for error in errors:
            print(f" - {error}")
        return 1

    print(f"Documentation quality checks passed for {len(markdown)} Markdown files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
