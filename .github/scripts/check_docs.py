#!/usr/bin/env python3
"""Repository-local public documentation quality gate."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]

CONTROLLED_DIRS = {
    "accessibility",
    "ai",
    "commercial",
    "communications",
    "compliance",
    "corporate-development",
    "customer-success",
    "customer-trust",
    "data",
    "engineering",
    "ethics",
    "finance",
    "governance",
    "human-rights",
    "internal-audit",
    "knowledge",
    "legal",
    "marketing",
    "operations",
    "partnerships",
    "people",
    "physical-security",
    "privacy",
    "procurement",
    "product",
    "project-delivery",
    "quality",
    "records",
    "releases",
    "research",
    "resilience",
    "security",
    "sop",
    "standards",
    "strategy",
    "support",
    "sustainability",
    "tax",
    "templates",
    "third-party",
    "treasury",
    "workplace-safety",
}

ROOT_FAMILIES = {
    "archive",
    "business",
    "data-ai",
    "engineering",
    "lessons",
    "operations",
    "platforms",
    "playbooks",
    "reference",
    "security",
    "standards",
    "templates",
}

# Project/private identifiers are forbidden everywhere in public Markdown.
PRIVATE_FORBIDDEN = {
    "mr.orchords",
    "mrorchords",
    "w.a.s.p",
    "thewam",
    "searabbit",
    "retmo",
    "cutshit",
    "roomtoneoptimiser",
}

# These remain prohibited in controlled policy/assurance documents, but are
# legitimate neutral technologies in reusable engineering articles.
CONTROLLED_IMPLEMENTATION_FORBIDDEN = {
    "openfx",
    "directx",
    "ffmpeg",
    "firebase",
    "forgejo",
}

FORBIDDEN_PATTERNS = {
    "private organization repository URL": re.compile(r"https?://github\.com/orchords/(?!docs(?:[/?#]|$))", re.I),
    "private repository API URL": re.compile(r"https?://api\.github\.com/repos/orchords/(?!docs(?:[/?#]|$))", re.I),
    "private repository raw URL": re.compile(r"https?://raw\.githubusercontent\.com/orchords/(?!docs(?:[/?#]|$))", re.I),
    "private repository SSH URL": re.compile(r"git@github\.com:orchords/(?!docs(?:\.git)?(?:\s|$))", re.I),
    "private secondary repository URL": re.compile(r"https?://github\.com/sapperskills/", re.I),
    "private repository shorthand": re.compile(r"\b(?:ORCHORDS|sapperskills)/(?!docs\b)[A-Za-z0-9_.-]+\b", re.I),
    "private knowledge-base path": re.compile(r"(?:^|[\\/])knowledge_base[\\/]", re.I | re.M),
    "private fleet path": re.compile(r"(?:^|[\\/])\.fleet[\\/]", re.I | re.M),
    "absolute user-home path": re.compile(r"(?:/home/[^/\s]+/|/Users/[^/\s]+/|[A-Z]:\\Users\\[^\\\s]+\\)", re.I),
    "conversation sandbox path": re.compile(r"/mnt/data/[^\s)]+", re.I),
}

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "Stripe live key": re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
}

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|api[_-]?token|access[_-]?token|auth[_-]?token|secret|password|passwd|private[_-]?key|client[_-]?secret)"
    r"\s*[:=]\s*[\"']?([^\s\"']{12,})"
)
SAFE_SECRET_VALUE_RE = re.compile(
    r"(?i)(?:example|sample|dummy|placeholder|redacted|your[_-]|changeme|test|fake|xxxxx|\*\*\*|\.\.\.|^<|^\$|^process\.env|^env\.|^os\.getenv|^secrets\.)"
)

REQUIRED_FRONT_MATTER = {
    "title",
    "owner",
    "status",
    "classification",
    "last-reviewed",
    "review-cycle",
    "next-review",
}

MARKDOWN_TARGET_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_TARGET_RE = re.compile(r"\b(?:href|src)\s*=\s*[\"']([^\"']+)[\"']", re.I)
FENCED_CODE_RE = re.compile(r"^(```|~~~).*?^\1\s*$", re.M | re.S)
URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)


def is_controlled(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if len(rel.parts) > 3 and rel.parts[0:2] == ("docs", "policies") and rel.parts[2] in CONTROLLED_DIRS:
        return True
    # Root knowledge families intentionally contain ordinary reusable articles.
    # Only each family's landing README is a controlled document.
    if len(rel.parts) >= 3 and rel.parts[0:2] == ("docs", "knowledge") and rel.parts[2] in ROOT_FAMILIES:
        return len(rel.parts) == 4 and rel.parts[3] == "README.md"
    # Retain compatibility with any legacy controlled root directories that are
    # not one of the reusable knowledge families.
    return False


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
    rendered_text = FENCED_CODE_RE.sub("", text)
    targets = MARKDOWN_TARGET_RE.findall(rendered_text) + HTML_TARGET_RE.findall(rendered_text)
    for raw in targets:
        target = raw.strip().split()[0].strip("<>")
        if (
            not target
            or target.startswith(("#", "/", "${"))
            or target.startswith("mailto:")
        ):
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


def check_secret_like_material(rel: Path, text: str) -> list[str]:
    errors: list[str] = []
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"{rel}: secret-like material detected: {label}")
    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        value = match.group(1)
        if not SAFE_SECRET_VALUE_RE.search(value):
            errors.append(f"{rel}: literal credential-like assignment")
            break
    return errors


def main() -> int:
    errors: list[str] = []
    markdown = sorted(ROOT.rglob("*.md"))
    root_md = {p.name for p in ROOT.glob("*.md")}
    allowed_root_md = {
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "SUPPORT.md",
        "GOVERNANCE.md",
        "CHANGELOG.md",
    }
    unexpected_root = sorted(root_md - allowed_root_md)
    if unexpected_root:
        errors.append("root: controlled documentation must live in a category: " + ", ".join(unexpected_root))

    for path in markdown:
        rel = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        controlled = is_controlled(path)

        if "\t" in text:
            errors.append(f"{rel}: tab character found")
        for no, line in enumerate(text.splitlines(), 1):
            if line.rstrip() != line:
                errors.append(f"{rel}:{no}: trailing whitespace")

        for term in PRIVATE_FORBIDDEN:
            if term in lower:
                errors.append(f"{rel}: forbidden project/private term: {term}")
        for label, pattern in FORBIDDEN_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{rel}: forbidden sensitive/private reference: {label}")
        errors.extend(check_secret_like_material(rel, text))

        if controlled:
            for term in CONTROLLED_IMPLEMENTATION_FORBIDDEN:
                if term in lower:
                    errors.append(f"{rel}: forbidden project/implementation term: {term}")

        if "$title" in lower or "lorem ipsum" in lower:
            errors.append(f"{rel}: unresolved template placeholder")
        if controlled:
            for token in ("todo", "tbd"):
                if re.search(rf"\b{token}\b", lower):
                    errors.append(f"{rel}: unresolved placeholder token: {token}")

        if controlled:
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
