from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil

KEEP_ROOT_FILES = {"README.md", "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "LICENSE", "SECURITY.md"}
KEEP_ROOT_DIRS = {".github", "assets", "docs"}
KNOWLEDGE_FAMILIES = {
    "archive", "business", "data-ai", "engineering", "lessons", "operations",
    "platforms", "playbooks", "reference", "security", "standards", "templates",
}
REFERENCE_FILES = {"GOVERNANCE.md", "SUPPORT.md", "CHANGELOG.md", "CITATION.cff"}
MD_LINK_RE = re.compile(r'(!?\[[^\]]*\]\()([^\n)]+)(\))')


def destination_for(rel: Path) -> Path:
    p = PurePosixPath(rel.as_posix())
    if not p.parts:
        return rel
    first = p.parts[0]
    if first == "categories":
        return Path(PurePosixPath("docs/policies", *p.parts[1:]).as_posix())
    if first in KNOWLEDGE_FAMILIES:
        return Path(PurePosixPath("docs/knowledge", *p.parts).as_posix())
    if first == "scripts":
        return Path(PurePosixPath(".github/scripts", *p.parts[1:]).as_posix())
    if len(p.parts) == 1 and first in REFERENCE_FILES:
        return Path("docs/reference") / first
    if len(p.parts) == 1 and first == "CODEOWNERS":
        return Path(".github/CODEOWNERS")
    return rel


def _split_target(raw: str):
    s = raw.strip()
    wrapped = s.startswith("<") and ">" in s
    if wrapped:
        end = s.index(">")
        return s[1:end], s[end + 1 :], True
    m = re.match(r"([^\s]+)(.*)$", s, re.S)
    return (m.group(1), m.group(2), False) if m else (s, "", False)


def _is_external(target: str) -> bool:
    low = target.lower()
    return not target or target.startswith("#") or low.startswith(
        ("http://", "https://", "mailto:", "tel:", "data:", "javascript:")
    )


def _strip_suffix(target: str):
    anchor = ""
    query = ""
    base = target
    if "#" in base:
        base, frag = base.split("#", 1)
        anchor = "#" + frag
    if "?" in base:
        base, q = base.split("?", 1)
        query = "?" + q
    return base, query, anchor


def _norm_old_target(old_file: PurePosixPath, target: str) -> PurePosixPath:
    if target.startswith("/"):
        joined = target.lstrip("/")
    else:
        joined = posixpath.join(str(old_file.parent), target)
    return PurePosixPath(posixpath.normpath(joined))


def rewrite_link(old_file: Path, new_file: Path, raw: str, file_map, dir_map) -> str:
    target, suffix, wrapped = _split_target(raw)
    if _is_external(target):
        return raw
    base, query, anchor = _strip_suffix(target)
    old_target = _norm_old_target(PurePosixPath(old_file.as_posix()), base)
    mapped = file_map.get(old_target) or dir_map.get(old_target)
    if mapped is None:
        return raw
    rel = posixpath.relpath(str(mapped), str(PurePosixPath(new_file.as_posix()).parent))
    if base.endswith("/") and not rel.endswith("/"):
        rel += "/"
    rebuilt = rel + query + anchor
    if wrapped:
        return f"<{rebuilt}>{suffix}"
    return rebuilt + suffix


def build_maps(root: Path):
    file_map = {}
    dir_map = {}
    for p in root.rglob("*"):
        if ".git" in p.parts:
            continue
        rel = p.relative_to(root)
        dst = destination_for(rel)
        key = PurePosixPath(rel.as_posix())
        val = PurePosixPath(dst.as_posix())
        if p.is_dir():
            dir_map[key] = val
        else:
            file_map[key] = val
    for name in ["categories", "scripts", *sorted(KNOWLEDGE_FAMILIES)]:
        src = PurePosixPath(name)
        dir_map[src] = PurePosixPath(destination_for(Path(name)).as_posix())
    return file_map, dir_map


def rewrite_markdown_text(text: str, old_file: Path, new_file: Path, file_map, dir_map) -> str:
    def repl(match):
        return (
            match.group(1)
            + rewrite_link(old_file, new_file, match.group(2), file_map, dir_map)
            + match.group(3)
        )

    out = MD_LINK_RE.sub(repl, text)
    out = out.replace("categories/", "docs/policies/")
    out = out.replace("scripts/check_docs.py", ".github/scripts/check_docs.py")
    out = out.replace(
        "scripts/check_public_neutrality.py", ".github/scripts/check_public_neutrality.py"
    )
    return out


def move_path(root: Path, src: str, dst: str):
    source = root / src
    target = root / dst
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RuntimeError(f"collision: {src} -> {dst}")
    shutil.move(str(source), str(target))


def patch_validators(root: Path):
    check = root / ".github/scripts/check_docs.py"
    text = check.read_text()
    text = text.replace(
        "ROOT = Path(__file__).resolve().parents[1]",
        "ROOT = Path(__file__).resolve().parents[2]",
    )
    text = text.replace(
        'if len(rel.parts) > 2 and rel.parts[0] == "categories" and rel.parts[1] in CONTROLLED_DIRS:',
        'if len(rel.parts) > 3 and rel.parts[0:2] == ("docs", "policies") and rel.parts[2] in CONTROLLED_DIRS:',
    )
    text = text.replace(
        'if rel.parts and rel.parts[0] in ROOT_FAMILIES:\n        return len(rel.parts) == 2 and rel.parts[1] == "README.md"',
        'if len(rel.parts) >= 3 and rel.parts[0:2] == ("docs", "knowledge") and rel.parts[2] in ROOT_FAMILIES:\n        return len(rel.parts) == 4 and rel.parts[3] == "README.md"',
    )
    text = text.replace(
        "return len(rel.parts) > 1 and rel.parts[0] in CONTROLLED_DIRS", "return False"
    )
    check.write_text(text)

    neutral = root / ".github/scripts/check_public_neutrality.py"
    text = neutral.read_text().replace(
        "ROOT = Path(__file__).resolve().parents[1]",
        "ROOT = Path(__file__).resolve().parents[2]",
    )
    neutral.write_text(text)


def patch_ci(root: Path):
    workflow = root / ".github/workflows/docs-quality.yml"
    text = workflow.read_text()
    text = text.replace('"scripts/check_docs.py"', '".github/scripts/check_docs.py"')
    text = text.replace(
        '"scripts/check_public_neutrality.py"',
        '".github/scripts/check_public_neutrality.py"',
    )
    text = text.replace("python scripts/check_docs.py", "python .github/scripts/check_docs.py")
    text = text.replace(
        "python scripts/check_public_neutrality.py",
        "python .github/scripts/check_public_neutrality.py",
    )
    workflow.write_text(text)


def patch_codeowners(root: Path):
    path = root / ".github/CODEOWNERS"
    text = path.read_text().replace("/categories/", "/docs/policies/")
    text = text.replace("/scripts/", "/.github/scripts/")
    if "/docs/knowledge/" not in text:
        text += "\n/docs/knowledge/ @ORCHORDS\n/docs/reference/ @ORCHORDS\n"
    path.write_text(text)


def write_indexes(root: Path):
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "README.md").write_text(
        "# Documentation\n\n"
        "The repository documentation is organized into three collections:\n\n"
        "- [Policies](./policies/README.md) — controlled public policy, governance, assurance, and operating documentation.\n"
        "- [Knowledge](./knowledge/README.md) — reusable project-neutral technical and operational knowledge.\n"
        "- [Reference](./reference/README.md) — repository governance, support, changelog, and citation metadata.\n"
    )

    knowledge = root / "docs/knowledge"
    knowledge.mkdir(parents=True, exist_ok=True)
    families = sorted(p.name for p in knowledge.iterdir() if p.is_dir())
    lines = ["# Reusable Knowledge", "", "Project-neutral reusable knowledge is grouped by domain:", ""]
    for family in families:
        target = knowledge / family / "README.md"
        lines.append(
            f"- [{family}](./{family}/README.md)" if target.exists() else f"- [{family}](./{family}/)"
        )
    (knowledge / "README.md").write_text("\n".join(lines) + "\n")

    reference = root / "docs/reference"
    reference.mkdir(parents=True, exist_ok=True)
    lines = ["# Repository Reference", "", "Repository-level supporting material:", ""]
    for name in ["GOVERNANCE.md", "SUPPORT.md", "CHANGELOG.md", "CITATION.cff"]:
        if (reference / name).exists():
            lines.append(f"- [{name}](./{name})")
    (reference / "README.md").write_text("\n".join(lines) + "\n")


def patch_root_readme(root: Path):
    path = root / "README.md"
    text = path.read_text()
    count = sum(1 for _ in root.rglob("*.md"))
    text = re.sub(
        r"(currently\n)[0-9,]+( Markdown files)",
        lambda match: match.group(1) + f"{count:,}" + match.group(2),
        text,
        count=1,
    )
    text = re.sub(
        r"Reusable project-neutral knowledge is also organized into top-level domain\nfamilies including `business/`, `data-ai/`, `engineering/`, `operations/`,\n`platforms/`, `security/`, `playbooks/`, `lessons/`, `standards/`,\n`templates/`, `reference/`, and `archive/`\.",
        "Reusable project-neutral knowledge is organized under\n"
        "[`docs/knowledge/`](./docs/knowledge/README.md), grouped into domain families.",
        text,
    )
    text = text.replace(
        "published in\nthe project-neutral top-level domain families.",
        "published under\n`docs/knowledge/` in project-neutral domain families.",
    )
    path.write_text(text)


def enforce_root(root: Path):
    extra_dirs = sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and p.name != ".git" and p.name not in KEEP_ROOT_DIRS
    )
    extra_files = sorted(
        p.name for p in root.iterdir() if p.is_file() and p.name not in KEEP_ROOT_FILES
    )
    if extra_dirs or extra_files:
        raise RuntimeError(f"root layout violation: dirs={extra_dirs}, files={extra_files}")


def migrate(root: Path):
    file_map, dir_map = build_maps(root)
    markdown = []
    for path in root.rglob("*.md"):
        if ".git" in path.parts:
            continue
        old = path.relative_to(root)
        markdown.append((old, destination_for(old), path.read_text()))

    move_path(root, "categories", "docs/policies")
    (root / "docs/knowledge").mkdir(parents=True, exist_ok=True)
    for family in sorted(KNOWLEDGE_FAMILIES):
        move_path(root, family, f"docs/knowledge/{family}")

    scripts = root / "scripts"
    if scripts.exists():
        target = root / ".github/scripts"
        target.mkdir(parents=True, exist_ok=True)
        for child in scripts.iterdir():
            destination = target / child.name
            if destination.exists():
                raise RuntimeError(
                    f"collision: scripts/{child.name} -> .github/scripts/{child.name}"
                )
            shutil.move(str(child), str(destination))
        scripts.rmdir()

    for name in sorted(REFERENCE_FILES):
        move_path(root, name, f"docs/reference/{name}")
    move_path(root, "CODEOWNERS", ".github/CODEOWNERS")
    if (root / ".gitignore").exists():
        (root / ".gitignore").unlink()

    for old, new, text in markdown:
        destination = root / new
        if destination.exists():
            destination.write_text(rewrite_markdown_text(text, old, new, file_map, dir_map))

    patch_validators(root)
    patch_ci(root)
    patch_codeowners(root)
    write_indexes(root)
    patch_root_readme(root)
    enforce_root(root)


if __name__ == "__main__":
    migrate(Path.cwd())
