"""Recheck retained GIW acquisition bytes and coverage before local import."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from .adapter import SOURCE_ID, SOURCE_URL, SECTIONS, RegisterPage, bundle_digest


def validate_acquisition(root, run_id, manifest, summary, max_age):
    target = Path(root) / "acquisition" / SOURCE_ID / run_id
    path = target / "acquisition-metadata.json"
    pages = target / "source-pages"
    if path.is_symlink() or pages.is_symlink():
        raise ValueError("GIW acquisition locator is invalid")
    facts = json.loads(path.read_text(encoding="utf-8"))
    acquired = datetime.fromisoformat(facts["retrieved_at_utc"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if (acquired.utcoffset() is None or acquired > now + timedelta(minutes=5)
            or now - acquired > timedelta(days=max_age)):
        raise ValueError("GIW acquisition timestamp is invalid or stale")
    if (facts.get("source_id") != SOURCE_ID or facts.get("run_id") != run_id
            or facts.get("canonical_url") != SOURCE_URL or manifest.get("source_url") != SOURCE_URL
            or facts.get("retrieved_at_utc") != manifest.get("retrieved_at_utc")
            or facts.get("artifact_sha256") != manifest.get("checksum_sha256")
            or bundle_digest(pages) != (facts.get("artifact_sha256"), facts.get("artifact_byte_size"))
            or facts.get("terms_review", {}).get("decision") != "approved"
            or facts.get("terms_review", {}).get("private_preview_only") is not True):
        raise ValueError("GIW acquisition provenance mismatch")
    if (len(facts["sections"]) != len(SECTIONS)
            or {s.get("section") for s in facts["sections"]} != set(SECTIONS)):
        raise ValueError("GIW section coverage is incomplete")
    expected_names = {p["artifact"] for p in facts["pages"]}
    if expected_names != {p.name for p in pages.glob("*.html")} or len(expected_names) != len(facts["pages"]):
        raise ValueError("GIW retained page set changed")
    observed = 0
    coverage = {section: [] for section in SECTIONS}
    for receipt in facts["pages"]:
        file = pages / receipt["artifact"]
        if file.parent != pages or file.is_symlink():
            raise ValueError("GIW page locator is invalid")
        raw = file.read_bytes()
        parsed = RegisterPage(raw)
        if (hashlib.sha256(raw).hexdigest() != receipt["sha256"] or len(raw) != receipt["byte_size"]
                or parsed.selected_section != receipt["section"] or len(parsed.data) != receipt["approval_observations"]
                or len(parsed.ordinals) != receipt["establishment_entries"]
                or receipt["section"] not in coverage):
            raise ValueError("GIW retained page verification failed")
        coverage[receipt["section"]].append((receipt["page"], parsed, receipt))
        observed += len(parsed.data)
    for section in facts["sections"]:
        count, size = section["establishment_entries"], section["page_size"]
        if not 1 <= size <= 100 or count < 0:
            raise ValueError("GIW section paging metadata is invalid")
        expected_pages = max(1, (count + size - 1) // size)
        retained = sorted(coverage[section["section"]], key=lambda entry: entry[0])
        if (section["page_count"] != expected_pages or section["count_rechecked"] is not True
                or [number for number, _, _ in retained] != list(range(1, expected_pages + 1))):
            raise ValueError("GIW section page coverage is incomplete")
        identifiers = set()
        observed_ordinals = set()
        for number, parsed, receipt in retained:
            expected = set(range((number - 1) * size + 1, min(number * size, count) + 1))
            ids = {row["wni"] for row in parsed.data}
            if (parsed.count != count or not parsed.ordinals.issubset(expected)
                    or (expected and not parsed.ordinals)
                    or receipt["source_omitted_ordinals"] != sorted(expected - parsed.ordinals)):
                raise ValueError("GIW retained section coverage changed")
            identifiers.update(ids)
            observed_ordinals.update(parsed.ordinals)
        if section["unique_veterinary_identifiers"] != len(identifiers):
            raise ValueError("GIW section identity count changed")
        if (section["observed_establishment_entries"] != len(observed_ordinals)
                or section["source_omitted_ordinals"] != sorted(set(range(1,count+1)) - observed_ordinals)):
            raise ValueError("GIW source omission receipt changed")
    if (facts["page_count"] != len(facts["pages"])
            or facts["source_establishment_section_entries"] != sum(s["establishment_entries"] for s in facts["sections"])):
        raise ValueError("GIW section totals changed")
    if (observed != facts.get("approval_observations") or observed != summary.get("input_rows")
            or summary.get("input_rows") != summary.get("normalized_rows") + summary.get("quarantined_rows")
            or manifest.get("normalized_sha256") != summary.get("candidate_handoff_sha256")
            or manifest.get("normalized_rows") != summary.get("normalized_rows")):
        raise ValueError("GIW lifecycle count or handoff mismatch")
    return facts
