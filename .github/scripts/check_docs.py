#!/usr/bin/env python3
"""Repository-local public documentation quality gate."""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]

CONTROLLED_DIRS = {
    "accessibility", "ai", "commercial", "communications", "compliance",
    "corporate-development", "customer-success", "customer-trust", "data",
    "engineering", "ethics", "finance", "governance", "human-rights",
    "internal-audit", "knowledge", "legal", "marketing", "operations",
    "partnerships", "people", "physical-security", "privacy", "procurement",
    "product", "project-delivery", "quality", "records", "releases",
    "research", "resilience", "security", "sop", "standards", "strategy",
    "support", "sustainability", "tax", "templates", "third-party",
    "treasury", "workplace-safety",
}

ROOT_FAMILIES = {
    "archive", "business", "data-ai", "engineering", "lessons", "operations",
    "platforms", "playbooks", "reference", "security", "standards", "templates",
}

PRIVATE_FORBIDDEN = {
    "mr.orchords", "mrorchords", "w.a.s.p", "thewam", "searabbit", "retmo",
    "cutshit", "roomtoneoptimiser",
}

CONTROLLED_IMPLEMENTATION_FORBIDDEN = {
    "openfx", "directx", "ffmpeg", "firebase", "forgejo",
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
    "title", "owner", "status", "classification", "last-reviewed",
    "review-cycle", "next-review",
}
SUPPORTED_REVIEW_CYCLES = {"30 days", "60 days", "90 days", "180 days"}

MARKDOWN_INLINE_START_RE = re.compile(r"(!?)\[[^\]\n]*\]\(")
MARKDOWN_REFERENCE_TARGET_RE = re.compile(
    r"^[ \t]{0,3}\[([^\]\n]+)\]:[ \t]*(?:<([^>\n]+)>|(\S+))",
    re.M,
)
MARKDOWN_REFERENCE_IMAGE_USE_RE = re.compile(r"!\[([^\]]*)\]\[([^\]]*)\]")
HTML_TAG_RE = re.compile(r"<[^>\n]+>")
HTML_TARGET_RE = re.compile(
    r"(?<![-\w])(href|src)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'=<>`]+))",
    re.I,
)
URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
DYNAMIC_TARGET_PREFIXES = ("${", "{{", "{%", "<%")


def is_controlled(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if len(rel.parts) > 3 and rel.parts[0:2] == ("docs", "policies") and rel.parts[2] in CONTROLLED_DIRS:
        return True
    if len(rel.parts) >= 3 and rel.parts[0:2] == ("docs", "knowledge") and rel.parts[2] in ROOT_FAMILIES:
        return len(rel.parts) == 4 and rel.parts[3] == "README.md"
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
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1].strip()
        if value.lower() in {"null", "~"}:
            value = ""
        result[key.strip()] = value
    return result


def check_front_matter(rel: Path, front_matter: dict[str, str]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_FRONT_MATTER - set(front_matter))
    if missing:
        errors.append(f"{rel}: front matter missing: {', '.join(missing)}")

    blank = sorted(
        key for key in REQUIRED_FRONT_MATTER
        if key in front_matter and not front_matter[key].strip()
    )
    for key in blank:
        errors.append(f"{rel}: front matter blank: {key}")

    if front_matter.get("classification") and front_matter["classification"] != "public":
        errors.append(f"{rel}: classification must be public")
    if front_matter.get("status") and front_matter["status"] not in {
        "approved", "review", "draft", "deprecated",
    }:
        errors.append(f"{rel}: invalid status")

    cycle = front_matter.get("review-cycle")
    if cycle and cycle not in SUPPORTED_REVIEW_CYCLES:
        errors.append(f"{rel}: invalid review-cycle: {cycle}")

    parsed_dates: dict[str, date] = {}
    for key in ("last-reviewed", "next-review"):
        value = front_matter.get(key)
        if not value:
            continue
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError
            parsed_dates[key] = date.fromisoformat(value)
        except ValueError:
            errors.append(f"{rel}: invalid {key} date: {value}")

    last_reviewed = parsed_dates.get("last-reviewed")
    next_review = parsed_dates.get("next-review")
    if last_reviewed and last_reviewed > date.today():
        errors.append(f"{rel}: last-reviewed must not be in the future")
    if last_reviewed and next_review and next_review < last_reviewed:
        errors.append(f"{rel}: next-review must not precede last-reviewed")
    if last_reviewed and next_review and cycle in SUPPORTED_REVIEW_CYCLES:
        cycle_days = int(cycle.split()[0])
        if next_review != last_reviewed + timedelta(days=cycle_days):
            errors.append(f"{rel}: next-review must match review-cycle: {cycle}")
    return errors


def strip_markdown_code(text: str) -> str:
    """Mask fenced blocks and inline code before scanning rendered targets."""
    output: list[str] = []
    fence_char: str | None = None
    fence_len = 0
    for line in text.splitlines(keepends=True):
        if fence_char is None:
            opening = re.match(r"^[ ]{0,3}(`{3,}|~{3,})(?:[^\n]*)$", line.rstrip("\r\n"))
            if opening:
                marker = opening.group(1)
                fence_char = marker[0]
                fence_len = len(marker)
                output.append("\n" if line.endswith(("\n", "\r")) else "")
                continue
            output.append(line)
            continue

        closing = re.match(
            rf"^[ ]{{0,3}}{re.escape(fence_char)}{{{fence_len},}}[ \t]*$",
            line.rstrip("\r\n"),
        )
        if closing:
            fence_char = None
            fence_len = 0
        output.append("\n" if line.endswith(("\n", "\r")) else "")

    rendered = "".join(output)
    return re.sub(r"(`+)([^`\n]*?)\1", "", rendered)


def iter_markdown_inline_targets(text: str):
    """Yield (is_image, raw_destination) with balanced parentheses preserved."""
    for match in MARKDOWN_INLINE_START_RE.finditer(text):
        is_image = bool(match.group(1))
        start = match.end()
        depth = 1
        escaped = False
        i = start
        while i < len(text):
            char = text[i]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    yield is_image, text[start:i]
                    break
            i += 1


def is_dynamic_target(target: str) -> bool:
    return target.lstrip().startswith(DYNAMIC_TARGET_PREFIXES)


def normalize_markdown_destination(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<"):
        end = raw.find(">")
        return raw[1:end] if end != -1 else raw[1:]
    return raw.split()[0] if raw else ""


def check_local_target(path: Path, raw: str, target: str, *, is_image: bool) -> list[str]:
    if not target or target.startswith(("#", "/")) or is_dynamic_target(target):
        return []
    if target.startswith("mailto:") or URL_RE.match(target):
        return []

    decoded = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not decoded:
        return []
    resolved = (path.parent / decoded).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError:
        return [f"{path.relative_to(ROOT)}: link escapes repository: {raw}"]

    if not resolved.exists() or (is_image and not resolved.is_file()):
        return [f"{path.relative_to(ROOT)}: broken relative link: {raw}"]
    return []


def check_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    rendered_text = strip_markdown_code(text)

    for is_image, raw in iter_markdown_inline_targets(rendered_text):
        target = normalize_markdown_destination(raw)
        errors.extend(check_local_target(path, raw, target, is_image=is_image))

    image_reference_labels: set[str] = set()
    for alt, label in MARKDOWN_REFERENCE_IMAGE_USE_RE.findall(rendered_text):
        image_reference_labels.add((label or alt).strip().casefold())

    for label, angle_target, bare_target in MARKDOWN_REFERENCE_TARGET_RE.findall(rendered_text):
        raw = angle_target or bare_target
        target = raw.strip() if angle_target else normalize_markdown_destination(raw)
        errors.extend(
            check_local_target(
                path,
                raw,
                target,
                is_image=label.strip().casefold() in image_reference_labels,
            )
        )

    for tag in HTML_TAG_RE.findall(rendered_text):
        for attribute, double_quoted, single_quoted, unquoted in HTML_TARGET_RE.findall(tag):
            raw = double_quoted or single_quoted or unquoted
            target = raw.strip()
            errors.extend(
                check_local_target(
                    path,
                    raw,
                    target,
                    is_image=attribute.casefold() == "src",
                )
            )

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
        "README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
        "SUPPORT.md", "GOVERNANCE.md", "CHANGELOG.md",
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
                errors.extend(check_front_matter(rel, front_matter))

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
