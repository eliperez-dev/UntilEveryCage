"""Deterministic checks for the canonical product-readiness documentation."""

import json
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

    def test_universal_reading_order_is_declared(self):
        root_instructions = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        hub = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        for content in (root_instructions, hub):
            self.assertLess(content.index("AGENTS.md"), content.index("ETHICS.md"))
            self.assertLess(content.index("ETHICS.md"), content.index("VISION.md"))
            self.assertLess(content.index("VISION.md"), content.index("docs/README.md") if "docs/README.md" in content else content.index("this hub"))
        for label in ("Canonical", "Reference", "Generated", "Historical evidence"):
            self.assertIn(label, hub)

    def test_product_readiness_and_documentation_indexes_link_resolve(self):
        checked = [
            ROOT / "docs" / "PRODUCT-READINESS.md",
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "archive" / "README.md",
            ROOT / "docs" / "architecture" / "README.md",
            ROOT / "docs" / "api" / "README.md",
            ROOT / "docs" / "sources" / "README.md",
            ROOT / "docs" / "countries" / "README.md",
            ROOT / "docs" / "frontend" / "README.md",
            ROOT / "docs" / "operations" / "README.md",
            ROOT / "docs" / "governance" / "README.md",
        ]
        missing = []
        for path in checked:
            for target in local_markdown_targets(path):
                if not target.resolve().exists():
                    missing.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [])

    def test_strict_live_private_e2e_state_is_separate_from_monitoring_and_release(self):
        payload = json.loads((ROOT / "docs" / "source-status.json").read_text(encoding="utf-8"))
        e2e = payload["latest_strict_live_private_e2e"]
        self.assertEqual(e2e["as_of"], "2026-09-24")
        self.assertEqual(e2e["observations"], 64701)
        self.assertEqual(e2e["private_candidates"], 42875)
        self.assertEqual(e2e["map_visible_candidates"], 41110)
        self.assertEqual(e2e["listable_unmapped_candidates"], 1765)
        self.assertEqual(e2e["public_rows"], 0)
        self.assertEqual(e2e["publication"], "not_authorized")
        expected = {
            "au.sa.epa.licensed-activities", "be.locations", "fr.dgal.section-i",
            "fr.dgal.section-ii", "it.853-2004", "it.1069-2009", "us.fsis",
        }
        self.assertEqual(set(e2e["verified_sources"]), expected)
        by_id = {row["source_id"]: row for row in payload["sources"]}
        for source_id in expected:
            self.assertEqual(by_id[source_id]["acquisition"], "verified")
            self.assertEqual(by_id[source_id]["runtime_health"], "not_run")
            self.assertEqual(by_id[source_id]["publication_eligibility"], "blocked")

    def test_temporary_plans_and_duplicate_packets_are_removed_not_archived(self):
        forbidden = [
            "docs/aphis-lane1-refresh-2026-09-19.md",
            "docs/archive/research/v2-ideas.md",
            "docs/archive/sprints/sprint01-integration-execution.md",
            "docs/archive/sprints/V2-BACKEND-PHASE-0-CLOSEOUT.md",
            "docs/archive/sprints/V2-IMPLEMENTATION-TODO.md",
            "docs/archive/sprints/V2-INTEGRATION-BASELINE.md",
            "docs/archive/sprints/V2-SPRINT-2026-09-13.md",
            "docs/countries/france/sprint02-kickoff-20260919.md",
            "docs/countries/france/sprint02-handoff-20260919.md",
            "docs/reports/italy-sprint02-20260919.md",
            "docs/geocoder-sprint-lane-ledger.md",
            "docs/frontend-reset-ledger.md",
            "docs/research/integrated-sprint-review-2026-09-18.md",
            "docs/review-packet-accountability-graph-sprint-3.md",
            "docs/review-packet-belgium.md",
            "docs/review-packet-denmark.md",
            "docs/review-packet-france.md",
            "docs/review-packet-germany.md",
            "docs/review-packet-italy.md",
            "docs/review-packet-united-kingdom.md",
            "docs/review-packet-us-accountability.md",
            "docs/SPRINT-02-CONTRACT.md",
            "docs/sprint02-integration-ledger.md",
            "docs/archive/rehearsals/country-rehearsal-2026-09-15.md",
        ]
        for relative in forbidden:
            self.assertFalse((ROOT / relative).exists(), relative)
        self.assertTrue((ROOT / "docs" / "VISION.md").is_file())
        self.assertTrue((ROOT / "docs" / "archive" / "rehearsals" / "country-rehearsal-2026-09-15.json").is_file())

    def test_documentation_hub_and_section_indexes_have_no_broken_local_paths(self):
        checked = [ROOT / "docs" / "README.md"]
        checked.extend((ROOT / "docs").rglob("README.md"))
        missing = []
        for path in checked:
            for target in local_markdown_targets(path):
                if not target.resolve().exists():
                    missing.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
