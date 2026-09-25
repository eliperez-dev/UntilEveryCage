"""Small source-control hygiene gate for runtime, generated, and doc boundaries."""
from __future__ import annotations

import argparse
import posixpath
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


MAX_KNOWN_GENERATED_BYTES = 1_500_000
KNOWN_GENERATED = {
    "static/private-review/readiness-matrix.json",
    "data/reports/geospatial-readiness.json",
    "data/manifests/d5-live-readiness-report.json",
    "data/manifests/d1-data-readiness-report.json",
}
FORBIDDEN_PATH_PARTS = {
    "target", ".runtime", "private-output", "private-preview-output",
    "runtime-output", "raw-output", "restricted-output",
}
TEMP_DOC_NAME = re.compile(r"(?:^|[-_])(?:plan|sprint|kickoff|handoff)(?:[-_.]|$)", re.I)
IMMUTABLE_DOC_ALLOWLIST = {
    # Versioned historical records are evidence, not temporary execution plans.
    "docs/archive/sprints/V2-SPRINT-2026-09-13.md",
    "docs/archive/sprints/sprint01-integration-execution.md",
}
PRIVATE_FILE_EXTENSIONS = {".sqlite", ".sqlite3", ".db", ".dump", ".pgdump"}


def tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    return [value.decode("utf-8") for value in result.stdout.split(b"\0") if value]


def _markdown_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [unquote(target) for target in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text)
            if not re.match(r"(?:[a-z]+:|#)", target, re.I)]


def internal_link_errors(source: str, links: list[str], existing: set[str]) -> list[str]:
    """Validate local links in the hub and docs section index files."""
    if not (source == "docs/README.md" or (source.startswith("docs/") and Path(source).name.lower() in {"readme.md", "index.md"})):
        return []
    errors = []
    for raw in links:
        target = raw.split("#", 1)[0].strip()
        if not target or re.match(r"(?:[a-z]+:|#)", target, re.I):
            continue
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
        if resolved == ".." or resolved.startswith("../") or target.startswith("/"):
            errors.append(f"{source}: link escapes repository: {raw}")
        elif resolved not in existing:
            errors.append(f"{source}: broken internal link: {raw}")
    return errors


def _doc_errors(root: Path, files: list[str]) -> list[str]:
    docs = {name for name in files if name.startswith("docs/") and name.lower().endswith(".md")}
    incoming: set[str] = set()
    errors: list[str] = []
    for name in docs:
        path = root / name
        links = _markdown_links(path)
        errors.extend(internal_link_errors(name, links, set(files)))
        for raw in links:
            target = raw.split("#", 1)[0].strip()
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            try:
                rel = resolved.relative_to(root.resolve()).as_posix()
            except ValueError:
                errors.append(f"{name}: link escapes repository: {raw}")
                continue
            if resolved.exists() and rel in docs:
                incoming.add(rel)
    errors.extend(orphan_temporary_docs(sorted(docs), incoming))
    return errors


def path_policy_errors(name: str, size: int | None = None) -> list[str]:
    """Return policy violations for one tracked path and optional byte size."""
    errors: list[str] = []
    parts = {part.lower() for part in Path(name).parts}
    if parts & FORBIDDEN_PATH_PARTS:
        errors.append(f"forbidden committed runtime/private output path: {name}")
    if Path(name).suffix.lower() in PRIVATE_FILE_EXTENSIONS:
        errors.append(f"forbidden committed private database artifact: {name}")
    if name in KNOWN_GENERATED and size is not None and size > MAX_KNOWN_GENERATED_BYTES:
        errors.append(f"oversized generated readiness/report artifact (> {MAX_KNOWN_GENERATED_BYTES} bytes): {name}")
    return errors


def orphan_temporary_docs(files: list[str], incoming: set[str]) -> list[str]:
    """List unreferenced plan/sprint/kickoff/handoff docs outside the archive."""
    return [
        f"orphan temporary Markdown: {name}"
        for name in sorted(files)
        if name.startswith("docs/")
        and name.lower().endswith(".md")
        and name not in IMMUTABLE_DOC_ALLOWLIST
        and TEMP_DOC_NAME.search(Path(name).stem)
        and name not in incoming
    ]


def check_repository(root: Path, files: list[str] | None = None) -> list[str]:
    files = tracked_paths(root) if files is None else files
    errors: list[str] = []
    for name in files:
        size = (root / name).stat().st_size if name in KNOWN_GENERATED else None
        errors.extend(path_policy_errors(name, size))
    if (root / "docs" / "README.md").exists():
        errors.extend(_doc_errors(root, files))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    errors = check_repository(args.root.resolve())
    if errors:
        print("\n".join(f"FAIL: {error}" for error in errors))
        return 1
    print("PASS: repository hygiene boundaries verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
