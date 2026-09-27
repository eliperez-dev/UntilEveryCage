"""Bounded acquisition of the current official Catalonia Socrata CSV export."""
from __future__ import annotations
import hashlib, json, urllib.parse, urllib.request
from pathlib import Path
from typing import Any
from pipeline.contracts.source_lifecycle import atomic_json
from pipeline.sources.italy import acquire as transport

SOURCE_ID = "es.cat.feed-sandach"
DATASET_ID = "m48e-zdz9"
METADATA_URL = f"https://analisi.transparenciacatalunya.cat/api/views/{DATASET_ID}.json"
CSV_URL = f"https://analisi.transparenciacatalunya.cat/api/v3/views/{DATASET_ID}/export.csv?accessType=DOWNLOAD"
API_HOST = "analisi.transparenciacatalunya.cat"
HEADERS = ["Nom establiment", "Adreça", "Municipi", "Codi postal", "Codi municipi (idescat)", "Comarca", "Codi Comarca", "Província", "Núm Registre", "Nom Activitat", "Alimentació Animal (AA) - SANDACH (S)", "Data alta de l'Activitat", "Empresa"]
METADATA_FIELDS = ["nom_establiment", "adre_a", "municipi", "codi_postal", "codi_municipi_idescat", "comarca", "codi_comarca", "prov_ncia", "n_m_registre", "nom_activitat", "alimentaci_animal_aa_sandach", "data_alta_de_l_activitat", "empresa"]

def _get(url: str, timeout: float, max_bytes: int) -> tuple[bytes, dict[str, str], str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != API_HOST:
        raise ValueError("Catalonia source URL outside approved HTTPS origin")
    request = urllib.request.Request(url, headers={"User-Agent": "UntilEveryCage-private-preview/1.0", "Accept": "text/csv,application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final = urllib.parse.urlparse(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != API_HOST:
            raise ValueError("Catalonia source response status or redirect rejected")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("Catalonia source response exceeds configured byte bound")
        return body, {k: v for k, v in response.headers.items()}, response.geturl()

def fetch(*, output_root: Path, run_id: str, terms_review_path: Path,
          timeout_seconds: float = 60.0, max_bytes: int = 128 * 1024 * 1024) -> dict[str, Any]:
    review = transport.require_terms_review(terms_review_path)
    metadata_raw, metadata_headers, metadata_final = _get(METADATA_URL, timeout_seconds, 4 * 1024 * 1024)
    metadata = json.loads(metadata_raw)
    current = [c.get("fieldName") for c in metadata.get("columns", []) if c.get("fieldName")]
    if current != METADATA_FIELDS:
        raise ValueError("Catalonia metadata schema drift")
    body, headers, final = _get(CSV_URL, timeout_seconds, max_bytes)
    content_type = next((v for k, v in headers.items() if k.lower() == "content-type"), "").lower()
    if "csv" not in content_type and "octet-stream" not in content_type:
        raise ValueError("Catalonia export content type rejected")
    import csv, io
    try:
        reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
        actual = tuple(" ".join((value or "").split()) for value in next(reader))
    except Exception as exc:
        raise ValueError("Catalonia export is not a valid UTF-8 CSV") from exc
    if actual != tuple(HEADERS):
        raise ValueError("Catalonia CSV schema drift")
    target = output_root / SOURCE_ID / run_id / "source.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".csv.tmp")
    try:
        temporary.write_bytes(body)
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    retrieved = transport.utc_now()
    result = {"source_id": SOURCE_ID, "run_id": run_id, "acquisition_method": "current_catalog_metadata_and_export",
              "adapter_version": "es-cat-acquisition-v1", "config_version": "es-cat-socrata-m48e-zdz9-v1",
              "artifact": target.name, "artifact_path": str(target), "byte_size": len(body), "sha256": hashlib.sha256(body).hexdigest(),
              "requested_at_utc": retrieved, "retrieved_at_utc": retrieved,
              "catalog_url": f"https://analisi.transparenciacatalunya.cat/d/{DATASET_ID}",
              "metadata_url": METADATA_URL, "metadata_final_url": metadata_final,
              "metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(), "metadata_headers": metadata_headers,
              "requested_url": CSV_URL, "final_url": final, "provenance_url": f"https://analisi.transparenciacatalunya.cat/d/{DATASET_ID}", "response_headers": headers,
              "publication_metadata": {k: v for k, v in headers.items() if k.lower() in {"last-modified", "etag", "x-soda2-truth-last-modified"}},
              "effective_date": "unknown", "coverage": "Catalonia autonomous community only; feed and specified SANDACH register",
              "terms_review": review}
    atomic_json(target.parent / "acquisition-metadata.json", result)
    return result
