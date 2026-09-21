"""Deterministically select the private FAOSTAT land-animal edition."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from .catalog import validate_catalog


FAOSTAT_ITEM_SCOPE = (
    ("Meat of asses, fresh or chilled", "asses", "An", 1),
    ("Meat of buffalo, fresh or chilled", "buffalo", "An", 1),
    ("Meat of camels, fresh or chilled", "camels", "An", 1),
    ("Meat of cattle with the bone, fresh or chilled", "cattle", "An", 1),
    ("Meat of chickens, fresh or chilled", "chickens", "1000 An", 1000),
    ("Meat of ducks, fresh or chilled", "ducks", "1000 An", 1000),
    ("Meat of geese, fresh or chilled", "geese", "1000 An", 1000),
    ("Meat of goat, fresh or chilled", "goats", "An", 1),
    ("Meat of mules, fresh or chilled", "mules", "An", 1),
    ("Meat of other domestic camelids, fresh or chilled", "other domestic camelids", "An", 1),
    ("Meat of other domestic rodents, fresh or chilled", "other domestic rodents", "1000 An", 1000),
    ("Meat of pig with the bone, fresh or chilled", "pigs", "An", 1),
    ("Meat of pigeons and other birds n.e.c., fresh, chilled or frozen", "pigeons and other birds n.e.c.", "1000 An", 1000),
    ("Meat of rabbits and hares, fresh or chilled", "rabbits and hares", "1000 An", 1000),
    ("Meat of sheep, fresh or chilled", "sheep", "An", 1),
    ("Meat of turkeys, fresh or chilled", "turkeys", "1000 An", 1000),
)


def _whole_value(row: dict[str, Any], item: str) -> int:
    try:
        value = Decimal(str(row["Value"]))
    except (KeyError, InvalidOperation) as exc:
        raise ValueError(f"{item}: invalid Value") from exc
    if value < 0 or value != value.to_integral_value():
        raise ValueError(f"{item}: source Value must be a non-negative whole number")
    return int(value)


def build_entry(
    rows: Iterable[dict[str, Any]],
    *,
    artifact_path: str,
    sha256: str,
    byte_size: int,
    retrieved_at_utc: str,
    effective_date: str = "2024-12-31",
    publication_date: str = "2025-12-15",
) -> dict[str, Any]:
    """Build and validate the 2024 entry from normalized FAOSTAT rows."""
    expected = {item: (population, unit, conversion) for item, population, unit, conversion in FAOSTAT_ITEM_SCOPE}
    selected: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("Area") != "World" or row.get("Year") != "2024" or row.get("Element") != "Producing Animals/Slaughtered":
            continue
        item = row.get("Item")
        if item not in expected:
            continue
        if item in selected:
            raise ValueError(f"duplicate selected FAOSTAT row: {item}")
        population, expected_unit, conversion = expected[item]
        if row.get("Unit") != expected_unit:
            raise ValueError(f"{item}: expected unit {expected_unit}, got {row.get('Unit')}")
        source_value = _whole_value(row, item)
        selected[item] = {
            "component_id": population.replace(" ", "-"),
            "population": population,
            "source_item": item,
            "source_unit": expected_unit,
            "source_value": source_value,
            "conversion_to_central_unit": conversion,
            "overlap_group": population,
        }
        if row.get("Flag"):
            selected[item]["source_flag"] = row["Flag"]
    missing = [item for item, *_ in FAOSTAT_ITEM_SCOPE if item not in selected]
    if missing:
        raise ValueError("missing selected FAOSTAT rows: " + ", ".join(missing))
    components = [selected[item] for item, *_ in FAOSTAT_ITEM_SCOPE]
    central = sum(component["source_value"] * component["conversion_to_central_unit"] for component in components)
    entry = {
        "statistic_id": "land-animals-slaughtered-for-meat-world-2024",
        "version_id": "land-animals-slaughtered-for-meat-world-2024-faostat-qcl-2025-12-15-v1",
        "label": "FAOSTAT World slaughtered animals for selected land-animal meat items, 2024",
        "status": "validated-private",
        "source": {
            "source_id": "faostat.qcl.livestock-primary",
            "publisher": "Food and Agriculture Organization of the United Nations (FAO)",
            "dataset_name": "Livestock primary (Global, National - Annual)",
            "dataset_url": "https://data.fao.org/catalog/iso/55375b1e-51d0-47db-ac9b-536ac8a1c738",
            "origin": "intergovernmental statistical source",
            "license": "CC-BY-4.0",
        },
        "population_scope": {
            "scope_id": "faostat-meat-leaf-items-heads-v1",
            "animal_class": "land animals",
            "activity": "slaughtered for meat production",
            "included": [population for _, population, _, _ in FAOSTAT_ITEM_SCOPE],
            "scope_note": "The selected scope contains the 16 non-aggregate FAOSTAT 2024 World meat-item rows that expose Producing Animals/Slaughtered. It is not a claim to count every land animal killed for food.",
        },
        "geography": {
            "level": "global aggregate",
            "area": "World (FAOSTAT Area)",
            "geography_note": "FAOSTAT values describe animals slaughtered within national boundaries, irrespective of origin; the World row is an FAO aggregate.",
        },
        "period": {"kind": "calendar-year", "start": "2024-01-01", "end": "2024-12-31", "calendar_year": 2024},
        "unit": {"kind": "count", "name": "animals (heads)", "numerator": "slaughtered animals", "denominator": "calendar year", "scale": 1},
        "estimate": {"type": "point-with-qualitative-uncertainty", "low": None, "central": central, "high": None},
        "method": {
            "type": "derived-from-components",
            "description": "Select World rows whose item is a named Meat of ... leaf item, retain FAOSTAT's source value and flag, convert 1000 An to heads, then sum the non-overlapping rows.",
            "formula": "sum(source_value * conversion_to_central_unit)",
        },
        "exclusions": [
            "FAOSTAT aggregate rows such as Meat, Total; Beef and Buffalo Meat, primary; Sheep and Goat Meat; and Meat, Poultry",
            "dairy and egg production, including animals culled from those systems when not represented in the selected meat rows",
            "aquatic animals, fish, crustaceans, molluscs, and other aquatic populations",
            "hides, fat, offal, wool, milk, eggs, and other non-meat commodities",
            "species or items with no selected 2024 World leaf row",
            "a numeric uncertainty interval, because this FAOSTAT release does not publish one for the selected rows",
        ],
        "uncertainty": {
            "kind": "qualitative-data-flags-and-coverage",
            "statement": "FAO says country inputs can be reported, estimated, supplemented from unofficial sources, or imputed, and flags them accordingly. The selected World rows are therefore a source-backed estimate with unknown numeric error; omitted categories and coverage gaps remain unknown.",
        },
        "provenance": {
            "artifact_id": "faostat-qcl-2025-12-15-production-crops-livestock-normalized",
            "artifact_path": artifact_path,
            "public_artifact": False,
            "sha256": sha256,
            "byte_size": byte_size,
            "retrieved_at_utc": retrieved_at_utc,
            "effective_date": effective_date,
            "publication_date": publication_date,
            "retrieval_url": "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip",
            "code_version": "animal-scale-statistics-v1",
            "config_version": "faostat-qcl-leaf-meat-items-v1",
            "retention_note": "The downloaded archive is ignored private research evidence; only this sanitized manifest is tracked.",
        },
        "revision": {
            "revision_id": "faostat-qcl-2025-12-15",
            "released_date": publication_date,
            "supersedes": None,
            "change_note": "Initial private catalog entry for the 2024 FAOSTAT revision; later source revisions must create a new version and preserve this one.",
        },
        "citations": [
            {"citation_id": "faostat-catalog-livestock-primary", "title": "FAOSTAT: Livestock primary (Global, National - Annual)", "url": "https://data.fao.org/catalog/iso/55375b1e-51d0-47db-ac9b-536ac8a1c738", "locator": "Dataset abstract, data lineage, units, time coverage, and revision metadata", "accessed_date": "2026-09-15"},
            {"citation_id": "faostat-qcl-methodology", "title": "FAOSTAT Agricultural production — Livestock methodology", "url": "https://files-faostat.fao.org/production/QCL/QCL_methodology_e.pdf", "locator": "PDF page 3: meat scope; PDF page 4: reference period and totals", "accessed_date": "2026-09-15"},
            {"citation_id": "faostat-qcl-bulk-archive", "title": "FAOSTAT Crops and livestock products normalized bulk archive", "url": "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip", "locator": "2024 World rows; Element=Producing Animals/Slaughtered; selected Meat of ... items", "accessed_date": "2026-09-15"},
        ],
        "citation_ids": ["faostat-catalog-livestock-primary", "faostat-qcl-methodology", "faostat-qcl-bulk-archive"],
        "aggregation": {"operation": "sum", "overlap_status": "resolved-non-overlapping", "basis": "Each component is a distinct FAOSTAT meat leaf item; aggregate meat rows and non-meat commodity rows are excluded."},
        "components": components,
    }
    validate_catalog({"schema_version": "aggregate-statistics-catalog-v1", "statistics": [entry]})
    return entry
