"""Deterministic checks for the canonical product-readiness documentation."""

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
LOCAL_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
CANONICAL_DECLARATION = re.compile(
    r"\*\*Canonical authority:\*\*\s*this document is the sole product-level\s+"
    r"readiness\s+and\s+overall V2 roadmap authority\."
)


def local_markdown_targets(path: Path):
    text = path.read_text(encoding="utf-8")
    for match in LOCAL_LINK.finditer(text):
        target = match.group(1).strip()
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith("#"):
            continue
        relative = Path(unquote(parsed.path))
        if not relative:
            continue
        yield path.parent / relative


class ProductReadinessDocumentationTests(unittest.TestCase):
    def test_exactly_one_canonical_overall_roadmap_declaration(self):
        matches = []
        for path in (ROOT / "docs").rglob("*.md"):
            for match in CANONICAL_DECLARATION.finditer(path.read_text(encoding="utf-8")):
                matches.append((path, match.start()))
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][0], ROOT / "docs" / "PRODUCT-READINESS.md")

    def test_product_readiness_and_archive_index_links_resolve(self):
        checked = [ROOT / "docs" / "PRODUCT-READINESS.md", ROOT / "docs" / "archive" / "README.md"]
        missing = []
        for path in checked:
            for target in local_markdown_targets(path):
                if not target.resolve().exists():
                    missing.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [])

    def test_historical_overall_roadmap_inputs_are_archived(self):
        expected = {
            "docs/archive/audits/DEAD-CODE-AUDIT-2026-09-16.md",
            "docs/archive/audits/V2-REVIEW-CLEANUP-2026-09-13.md",
            "docs/archive/research/v2-ideas.md",
            "docs/archive/sprints/V2-BACKEND-PHASE-0-CLOSEOUT.md",
            "docs/archive/sprints/V2-IMPLEMENTATION-TODO.md",
            "docs/archive/sprints/V2-INTEGRATION-BASELINE.md",
            "docs/archive/sprints/V2-SPRINT-2026-09-13.md",
            "docs/archive/sprints/sprint01-integration-execution.md",
            "docs/archive/rehearsals/country-rehearsal-2026-09-15.md",
            "docs/archive/rehearsals/country-rehearsal-2026-09-15.json",
        }
        for relative in expected:
            self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertFalse((ROOT / "docs" / "V2-IMPLEMENTATION-TODO.md").exists())
        self.assertFalse((ROOT / "v2-ideas.md").exists())


if __name__ == "__main__":
    unittest.main()
