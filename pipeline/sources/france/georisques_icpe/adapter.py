"""Normalize filtered Géorisques ICPE pages into a private candidate handoff.

The API's animal-related rubrics are regulatory observations, not proof that a
facility currently keeps animals. Source names and business identifiers stay
in this restricted flow; personal-contact data is never selected as a field.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from pyproj import Transformer

from pipeline.common.review import write_operator_review_packet
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.contracts.source_lifecycle import atomic_json, atomic_jsonl, private_manifest

from .config import CONFIG


class GeorisquesIcpeAnimalAdapter:
    source_id = CONFIG["source_id"]
    source_url = CONFIG["source_url"]
    adapter_version = CONFIG["adapter_version"]
    schema_version = CONFIG["schema_version"]

    def __init__(self) -> None:
        self.allowed_rubrics = frozenset(CONFIG["animal_rubrics"])

    @staticmethod
    def _source_values(raw: dict[str, Any], allowed_rubrics: frozenset[str]) -> dict[str, Any]:
        # Keep only facility/operator facts needed for this source scope.
        # Inspection narratives, document URLs, and unknown nested fields are
        # deliberately omitted from the candidate handoff.
        fields = (
            "codeAIOT", "siret", "raisonSociale", "adresse1", "adresse2", "adresse3",
            "codePostal", "codeInsee", "commune", "codeNaf", "longitude", "latitude",
            "coordonneeXAIOT", "coordonneeYAIOT", "systemeCoordonneesAIOT",
            "bovins", "porcs", "volailles", "etatActivite", "date_maj", "regime",
        )
        values = {key: raw[key] for key in fields if key in raw}
        service = GeorisquesIcpeAnimalAdapter._text(raw.get("serviceAIOT"))
        if service is not None:
            values["serviceAIOT"] = service
        rubriques = raw.get("rubriques")
        if isinstance(rubriques, list):
            rubric_fields = ("numeroRubrique", "nature", "alinea", "regimeAutoriseAlinea",
                             "quantiteTotale", "unite", "dateMotif")
            values["rubriques"] = [
                {key: item[key] for key in rubric_fields if key in item}
                for item in rubriques if isinstance(item, dict)
                and GeorisquesIcpeAnimalAdapter._text(item.get("numeroRubrique")) in allowed_rubrics
            ]
        return values

    @staticmethod
    def _page_files(raw_path: str | Path) -> list[Path]:
        root = Path(raw_path)
        if root.is_file():
            return [root]
        pages = sorted(root.glob("page-*.json"))
        if not pages:
            raise ValueError("acquisition directory contains no page-*.json artifacts")
        return pages

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return None

    @staticmethod
    def _coordinate(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _france_extent(lon: float, lat: float) -> str:
        # Broad boxes are a validation aid, not geofences or proof of commune.
        extents = {
            "metropolitan-france": (-6.0, 10.0, 41.0, 52.5),
            "guadeloupe-saint-martin-saint-barthelemy": (-64.0, -60.0, 14.0, 19.0),
            "martinique": (-62.0, -60.0, 13.0, 16.0),
            "french-guiana": (-56.0, -51.0, 2.0, 6.0),
            "reunion": (54.0, 57.0, -22.5, -19.0),
            "mayotte": (44.0, 46.0, -14.0, -11.0),
            "saint-pierre-and-miquelon": (-57.5, -55.0, 46.0, 48.0),
            "new-caledonia": (162.0, 169.0, -23.0, -18.0),
            "french-polynesia": (-155.0, -134.0, -28.0, -7.0),
            "wallis-and-futuna": (-178.5, -175.0, -15.0, -12.0),
        }
        for name, (west, east, south, north) in extents.items():
            if west <= lon <= east and south <= lat <= north:
                return name
        return "outside-configured-france-extents"

    @staticmethod
    @lru_cache(maxsize=32)
    def _transformer(source_crs: str) -> Transformer:
        return Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True,
                                    allow_ballpark=False, only_best=True)

    @classmethod
    def _source_point(cls, raw: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """Transform only the API's explicitly projected AIOT coordinate pair.

        The separate API longitude/latitude fields are retained as corroboration,
        never used as the location authority because their output datum is not
        declared in the upstream schema.
        """
        x = cls._coordinate(raw.get("coordonneeXAIOT"))
        y = cls._coordinate(raw.get("coordonneeYAIOT"))
        epsg = cls._text(raw.get("systemeCoordonneesAIOT"))
        if x is None or y is None:
            return None, "missing-or-invalid-projected-coordinate-pair"
        if not epsg:
            return None, "missing-source-coordinate-reference-system"
        code = epsg.upper().replace(" ", "")
        if code.isdigit():
            code = f"EPSG:{code}"
        elif not code.startswith("EPSG:") or not code[5:].isdigit():
            return None, "unsupported-source-coordinate-reference-system"
        try:
            transformer = cls._transformer(code)
            lon, lat = transformer.transform(x, y, errcheck=True)
        except Exception:
            return None, "source-coordinate-transform-failed"
        if transformer.accuracy < 0:
            return None, "source-coordinate-transform-accuracy-unknown"
        if not (math.isfinite(lon) and math.isfinite(lat)
                and -180 <= lon <= 180 and -90 <= lat <= 90):
            return None, "transformed-coordinate-out-of-wgs84-range"

        api_lon = cls._coordinate(raw.get("longitude"))
        api_lat = cls._coordinate(raw.get("latitude"))
        corroboration = "not-comparable"
        if api_lon is not None and api_lat is not None and -180 <= api_lon <= 180 and -90 <= api_lat <= 90:
            # Quality signal only; it never selects or suppresses the source-CRS point.
            from pyproj import Geod
            _, _, distance_m = Geod(ellps="WGS84").inv(lon, lat, api_lon, api_lat)
            corroboration = "within-100m" if distance_m <= 100 else "differs-over-100m"
        return ({
            "longitude": lon,
            "latitude": lat,
            "coordinate_reference_system": "EPSG:4326",
            "source_coordinate_reference_system": code,
            "source_coordinate_x": raw.get("coordonneeXAIOT"),
            "source_coordinate_y": raw.get("coordonneeYAIOT"),
            "transform_method": "pyproj best available non-ballpark operation; source-declared AIOT CRS to EPSG:4326; always_xy",
            "transform_accuracy_m": transformer.accuracy,
            "api_lonlat_corroboration": corroboration,
            "jurisdiction_extent": cls._france_extent(lon, lat),
            "state": "source-declared-crs-transformed",
        }, "transformed")

    def _parse_payload_for_size(self, payload: dict[str, Any], expected_page: int,
                                page_size: int, max_records: int) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("API page must be a JSON object")
        page = payload.get("page")
        total_pages = payload.get("total_pages")
        total = payload.get("results")
        rows = payload.get("data")
        if (not isinstance(page, int) or isinstance(page, bool) or page != expected_page
                or not isinstance(total_pages, int) or isinstance(total_pages, bool) or total_pages < 1):
            raise ValueError("API page number or total_pages is invalid")
        if not isinstance(total, int) or isinstance(total, bool) or total < 0 or not isinstance(rows, list):
            raise ValueError("API results/data fields have an unexpected shape")
        if total > max_records or total_pages > CONFIG["max_pages"]:
            raise ValueError("API result exceeds the checked-in acquisition bound")
        if expected_page > total_pages:
            raise ValueError("page number exceeds API total_pages")
        expected_count = min(page_size, max(0, total - (expected_page - 1) * page_size))
        if len(rows) != expected_count:
            raise ValueError(f"page {expected_page} returned {len(rows)} rows; expected {expected_count}")
        return {"page": page, "total_pages": total_pages, "results": total, "data": rows}

    def _parse_payload(self, payload: dict[str, Any], expected_page: int,
                       page_size: int) -> dict[str, Any]:
        return self._parse_payload_for_size(payload, expected_page, page_size, CONFIG["max_records"])

    def parse_pages(self, raw_path: str | Path) -> dict[str, Any]:
        page_files = self._page_files(raw_path)
        root = Path(raw_path)
        page_size = CONFIG["page_size"]
        if root.is_dir() and (root.parent / "snapshot-manifest.json").is_file():
            page_size = int(json.loads((root.parent / "snapshot-manifest.json").read_text(encoding="utf-8"))["page_size"])
        if not 1 <= page_size <= 100:
            raise ValueError("snapshot page_size is outside the acquisition bound")
        pages: list[dict[str, Any]] = []
        hashes: list[tuple[str, int]] = []
        snapshot_manifest = None
        if root.is_dir() and (root.parent / "snapshot-manifest.json").is_file():
            try:
                snapshot_manifest = json.loads((root.parent / "snapshot-manifest.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError("snapshot manifest is invalid") from error
            if snapshot_manifest.get("source_id") != CONFIG["source_id"]:
                raise ValueError("snapshot manifest source_id does not match this adapter")
            page_size = int(snapshot_manifest.get("page_size", 0))
            if not 1 <= page_size <= 100:
                raise ValueError("snapshot page_size is outside the acquisition bound")
            manifest_pages = snapshot_manifest.get("pages")
            if not isinstance(manifest_pages, list) or len(manifest_pages) != len(page_files):
                raise ValueError("snapshot manifest page list does not match acquired pages")
        else:
            manifest_pages = None
        for expected, path in enumerate(page_files, 1):
            raw = path.read_bytes()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ValueError(f"page {expected} is not valid JSON") from error
            pages.append(self._parse_payload(payload, expected, page_size))
            digest = hashlib.sha256(raw).hexdigest()
            hashes.append((digest, len(raw)))
            if manifest_pages is not None:
                fact = manifest_pages[expected - 1]
                if (not isinstance(fact, dict) or fact.get("page") != expected
                        or fact.get("sha256") != digest or fact.get("byte_size") != len(raw)
                        or fact.get("rows") != len(payload["data"])):
                    raise ValueError(f"page {expected} does not match snapshot-manifest provenance")
        first = pages[0]
        if len(pages) != first["total_pages"]:
            raise ValueError("acquired page count does not equal API total_pages")
        if any((p["results"], p["total_pages"]) != (first["results"], first["total_pages"]) for p in pages):
            raise ValueError("API pagination totals changed during snapshot")
        rows = [row for page in pages for row in page["data"]]
        if len(rows) != first["results"]:
            raise ValueError("acquired row count does not reconcile to API results")
        digest = hashlib.sha256(b"".join(Path(path).read_bytes() for path in page_files)).hexdigest()
        if snapshot_manifest is not None:
            if (snapshot_manifest.get("sha256") != digest
                    or snapshot_manifest.get("byte_size") != sum(size for _, size in hashes)
                    or snapshot_manifest.get("results") != first["results"]
                    or snapshot_manifest.get("total_pages") != first["total_pages"]):
                raise ValueError("snapshot bytes or counts do not match snapshot-manifest provenance")
        return {"pages": pages, "rows": rows, "input_rows": len(rows), "results": first["results"],
                "total_pages": first["total_pages"], "page_hashes": hashes, "sha256": digest,
                "byte_size": sum(size for _, size in hashes)}

    def normalize(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        seen_observations: set[str] = set()
        for index, raw in enumerate(rows, 1):
            if not isinstance(raw, dict):
                quarantined.append({"reasons": ("row_not_object",), "source_row": index})
                continue
            rubriques = raw.get("rubriques")
            if not isinstance(rubriques, list):
                rubriques = []
            matches = [item for item in rubriques if isinstance(item, dict)
                       and self._text(item.get("numeroRubrique")) in self.allowed_rubrics]
            match_codes = [self._text(item.get("numeroRubrique")) for item in matches]
            match_codes = [code for code in match_codes if code is not None]
            match_labels = [CONFIG["animal_rubric_descriptions"][code] for code in match_codes]
            categories = list(dict.fromkeys(
                "slaughter" if code in {"2210", "3641"} else
                "processing" if code in {"2221", "2230"} else
                "animal_keeping"
                for code in match_codes
            ))
            reasons: list[str] = []
            aiot = self._text(raw.get("codeAIOT"))
            name = self._text(raw.get("raisonSociale"))
            if not matches:
                reasons.append("no_allowed_animal_rubric")
            if not aiot:
                reasons.append("missing_aiot_identifier")
            if not name:
                reasons.append("missing_native_establishment_name")
            observation_digest = hashlib.sha256(json.dumps(
                raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest()
            if observation_digest in seen_observations:
                reasons.append("duplicate_identical_source_observation")
            seen_observations.add(observation_digest)

            coords, coordinate_state = self._source_point(raw)
            map_point = bool(coords and matches
                             and coords["jurisdiction_extent"] != "outside-configured-france-extents")

            source_row_id = hashlib.sha256(f"{index}:{aiot or 'missing'}".encode()).hexdigest()
            record = {
                "source_id": self.source_id,
                "source_row": index,
                "source_row_id": source_row_id,
                "source_record_key": f"{aiot or 'unknown'}|row-{index}",
                "source_values": self._source_values(raw, self.allowed_rubrics),
                "normalized": {
                    "establishment_id": aiot,
                    "facility_grouping": "source-aiot; source-scoped; merge-review-required",
                    "identity_review": "required-before-merge",
                    "name": name,
                    "trading_name": name,
                    "siret": self._text(raw.get("siret")),
                    "address": " ".join(v for v in (self._text(raw.get("adresse1")),
                                                          self._text(raw.get("adresse2")),
                                                          self._text(raw.get("adresse3"))) if v) or None,
                    "postal_code": self._text(raw.get("codePostal")),
                    "municipality": self._text(raw.get("commune")),
                    "municipality_code": self._text(raw.get("codeInsee")),
                    "country_code": "FR",
                    "jurisdiction_level": "national",
                    "activity": "ICPE animal-related rubric observation; current operation not inferred",
                    "activity_code": self._text(raw.get("codeNaf")),
                    "source_classification_codes": match_codes,
                    "source_classification_labels": match_labels,
                    "activity_categories": categories,
                    "animal_rubrics": matches,
                    "rubriques_source": [item for item in rubriques if isinstance(item, dict)
                                         and self._text(item.get("numeroRubrique")) in self.allowed_rubrics],
                    "regime": raw.get("regime"),
                    "activity_status_source": raw.get("etatActivite"),
                    "activity_status_interpretation": "source-value-preserved; not independently verified",
                    "inspection_service_source": self._text(raw.get("serviceAIOT")),
                    "capacity_indicators_source": {key: raw.get(key) for key in ("bovins", "porcs", "volailles") if key in raw},
                    "capacity_semantics": "source indicators preserved; no capacity conversion or use inferred",
                    "source_updated_at": raw.get("date_maj"),
                    "coordinates": coords,
                    "coordinate_state": coordinate_state,
                    "async_coordinate_enrichment_state": "eligible-for-separately-approved-private-enrichment" if not coords else "not-requested-source-coordinate-present",
                    "in_default_map_scope": map_point,
                    "map_scope_reason": ("source animal rubric matches; private point transformed from the source-declared AIOT CRS; privacy, factual, and publication gates remain separate" if map_point else
                                         "source-declared projected coordinates unavailable, invalid, or outside configured France extents; no point inferred"),
                    "geocoding": "disabled",
                    "observation_state": "listed-at-retrieval",
                    "disappearance_semantics": "not-observed; never inferred as closure",
                    "privacy_gate": "pending-review",
                    "coordinate_gate": "source_declared_crs_transformed" if coords else coordinate_state,
                    "publication_gate": "blocked",
                },
            }
            if reasons:
                quarantined.append({"reasons": tuple(dict.fromkeys(reasons)), "record": record})
            else:
                accepted.append(record)
        return {"accepted": accepted, "quarantined": quarantined, "input_rows": len(rows)}

    def parse_path(self, raw_path: str | Path) -> dict[str, Any]:
        snapshot = self.parse_pages(raw_path)
        normalized = self.normalize(snapshot["rows"])
        return {**snapshot, **normalized}

    def run(self, raw_path: str | Path, run_dir: str | Path, artifact: SourceArtifact) -> dict[str, Any]:
        result = self.parse_path(raw_path)
        if artifact.sha256 != result["sha256"] or artifact.byte_size != result["byte_size"]:
            raise ValueError("aggregate acquisition provenance mismatch")
        root = Path(run_dir)
        accepted, quarantined = result["accepted"], result["quarantined"]
        parsed_rows = accepted + [item["record"] for item in quarantined if "record" in item]
        _, parsed_hash, _ = atomic_jsonl(root / "parsed" / "records.jsonl", parsed_rows)
        _, normalized_hash, _ = atomic_jsonl(root / "normalized" / "records.jsonl", accepted)
        atomic_jsonl(root / "quarantined" / "records.jsonl", quarantined)
        anomalies = Counter(reason for item in quarantined for reason in item.get("reasons", ()))
        manifest = private_manifest(
            source_id=self.source_id, adapter_version=self.adapter_version,
            schema_version=self.schema_version, artifact=artifact,
            input_rows=result["input_rows"], normalized_rows=len(accepted),
            quarantined_rows=len(quarantined), normalized_sha256=normalized_hash,
            parsed_sha256=parsed_hash, anomaly_counts=dict(sorted(anomalies.items())),
        )
        manifest.update({
            "country_code": "FR", "scope": CONFIG["coverage"],
            "api_results": result["results"], "api_pages": result["total_pages"],
            "schema_fingerprint": hashlib.sha256(json.dumps({
                "schema_version": self.schema_version,
                "config_version": CONFIG["config_version"],
                "source_fields": ["codeAIOT", "siret", "raisonSociale", "adresse1", "adresse2",
                                  "adresse3", "codePostal", "codeInsee", "commune", "codeNaf",
                                  "longitude", "latitude", "coordonneeXAIOT", "coordonneeYAIOT",
                                  "systemeCoordonneesAIOT", "bovins", "porcs", "volailles",
                                  "etatActivite", "date_maj", "regime", "serviceAIOT", "rubriques"],
                "animal_rubrics": sorted(self.allowed_rubrics),
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "animal_rubrics": sorted(self.allowed_rubrics),
            "terms_status": "accepted-for-private-acquisition-and-processing; attribution, privacy, factual review, and publication remain separate gates",
            "data_licence": "Licence Ouverte 2.0 stated in Géorisques CGU; retain attribution and source update dates",
            "geocoding": "disabled", "release_state": "not-created",
        })
        atomic_json(root / "manifest.json", manifest)
        write_operator_review_packet(
            root, manifest, source_scope=CONFIG["coverage"],
            checks=("retain the source-specific Géorisques CGU acceptance reference", "review Licence Ouverte 2.0 attribution and update-date obligations",
                    "review animal rubric allowlist and regulatory meaning", "screen native business names, addresses, identifiers and coordinates",
                    "review source activity status without inferring current animal use"),
            blockers=("publication and external redistribution not approved",
                      "privacy, coordinate, factual and release review pending"),
        )
        return manifest
