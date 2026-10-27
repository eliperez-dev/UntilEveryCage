"""Bounded, opt-in acceptance for a published country release.

This is a CLI helper, deliberately not a discovered unittest. It only contacts
an explicitly configured loopback API; see ``--help`` for the contract shape.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


MAX_SOURCES = 32
MAX_MAPPED_IDS = 75_000  # Public map/matches endpoint hard ceiling.
MAX_TOTAL_COUNT = 1_000_000_000
MAX_GRAPH_SAMPLE_PAGES = 2
MAX_APHIS_PAGES = 100
TIMEOUT_SECONDS = 30
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AcceptanceFailure(Exception):
    """A safe diagnostic label, never a response body or query value."""


def validate_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise AcceptanceFailure("origin_must_be_loopback_http")
    return origin.rstrip("/")


def _int(value, label: str, maximum: int = 10**9) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum:
        raise AcceptanceFailure("invalid_" + label)
    return value


def validate_contract(contract: dict) -> dict:
    if not isinstance(contract, dict):
        raise AcceptanceFailure("contract_not_object")
    for key in ("release_id", "profile"):
        if not isinstance(contract.get(key), str) or not contract[key].strip():
            raise AcceptanceFailure("invalid_" + key)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", contract["release_id"]):
        raise AcceptanceFailure("invalid_release_id")
    if contract["profile"] not in {"official", "secondary", "community"}:
        raise AcceptanceFailure("invalid_profile")
    if not isinstance(contract.get("manifest_sha256"), str) or not HEX_SHA256.fullmatch(contract["manifest_sha256"]):
        raise AcceptanceFailure("invalid_manifest_sha256")
    sources = contract.get("sources")
    if not isinstance(sources, dict) or not 1 <= len(sources) <= MAX_SOURCES:
        raise AcceptanceFailure("invalid_sources")
    for source_id, expected in sources.items():
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", source_id) or not isinstance(expected, dict):
            raise AcceptanceFailure("invalid_source_contract")
        total = _int(expected.get("total_count"), "source_total_count", MAX_TOTAL_COUNT)
        mapped = _int(expected.get("mapped_count"), "source_mapped_count", MAX_MAPPED_IDS)
        if mapped > total:
            raise AcceptanceFailure("invalid_source_counts")
        if "category_counts" in expected:
            values = expected["category_counts"]
            if not isinstance(values, dict) or any(not isinstance(k, str) or not k for k in values):
                raise AcceptanceFailure("invalid_source_category_counts")
            for value in values.values():
                _int(value, "category_count", MAX_TOTAL_COUNT)
    if len(sources) > MAX_SOURCES:
        raise AcceptanceFailure("too_many_sources")
    for retained in contract.get("retained_releases", []):
        if not isinstance(retained, dict) or not isinstance(retained.get("release_id"), str):
            raise AcceptanceFailure("invalid_retained_release")
        if not isinstance(retained.get("manifest_sha256"), str) or not HEX_SHA256.fullmatch(retained["manifest_sha256"]):
            raise AcceptanceFailure("invalid_retained_digest")
        for key in ("total_count", "mapped_count"):
            _int(retained.get(key), "retained_" + key, MAX_TOTAL_COUNT if key == "total_count" else MAX_MAPPED_IDS)
    return contract


class LocalApi:
    def __init__(self, origin: str):
        self.origin = validate_origin(origin)
        self.requests = 0

    def get(self, route: str, params: dict | None = None) -> tuple[dict, dict]:
        if self.requests >= 600:
            raise AcceptanceFailure("request_budget_exceeded")
        self.requests += 1
        query = urllib.parse.urlencode(params or {})
        url = self.origin + route + ("?" + query if query else "")
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise AcceptanceFailure("response_too_large")
                if response.status != 200:
                    raise AcceptanceFailure("http_status_" + str(response.status))
        except AcceptanceFailure:
            raise
        except Exception:
            # Never surface URLs, queries, provider payloads, or exception text.
            raise AcceptanceFailure("request_failed") from None
        try:
            payload = json.loads(body)
        except Exception:
            raise AcceptanceFailure("invalid_json_response") from None
        if not isinstance(payload, dict):
            raise AcceptanceFailure("invalid_response_shape")
        return payload, dict(response.headers)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _data(payload: dict):
    if "data" not in payload:
        raise AcceptanceFailure("missing_data")
    return payload["data"]


def _meta(payload: dict) -> dict:
    value = payload.get("meta")
    if not isinstance(value, dict):
        raise AcceptanceFailure("missing_meta_object")
    return value


def _manifest(api: LocalApi, release_id: str, profile: str, expected_sha: str) -> dict:
    payload, _ = api.get("/api/v2/releases/manifest", {"release_id": release_id, "profile": profile})
    data = _data(payload)
    if data.get("release_id") != release_id or data.get("manifest_sha256") != expected_sha:
        raise AcceptanceFailure("manifest_identity_mismatch")
    return data


def _check_retained(api: LocalApi, retained: dict, profile: str) -> None:
    _manifest(api, retained["release_id"], profile, retained["manifest_sha256"])
    payload, _ = api.get("/api/v2/locations", {
        "release_id": retained["release_id"], "profile": profile, "limit": 1,
    })
    meta = _meta(payload)
    if (meta.get("total_count") != retained["total_count"]
            ):
        raise AcceptanceFailure("retained_aggregate_mismatch")
    mapped, _ = api.get("/api/v2/map/matches", {
        "release_id": retained["release_id"], "profile": profile,
    })
    mapped_data, mapped_meta = _data(mapped), _meta(mapped)
    ids = mapped_data.get("facility_ids") if isinstance(mapped_data, dict) else None
    if (not isinstance(ids, list) or len(ids) > MAX_MAPPED_IDS
            or mapped_meta.get("manifest_sha256") != retained["manifest_sha256"]
            or mapped_meta.get("total_count") != retained["total_count"]
            or mapped_meta.get("mapped_count") != retained["mapped_count"]
            or len(ids) != retained["mapped_count"] or len(set(ids)) != len(ids)):
        raise AcceptanceFailure("retained_aggregate_mismatch")


def _check_sources(api: LocalApi, contract: dict) -> None:
    release_id, profile = contract["release_id"], contract["profile"]
    for source_id, expected in contract["sources"].items():
        params = {"release_id": release_id, "profile": profile, "source_id": source_id}
        list_payload, _ = api.get("/api/v2/locations", {**params, "limit": 1})
        list_meta = _meta(list_payload)
        if list_meta.get("total_count") != expected["total_count"]:
            raise AcceptanceFailure("source_total_mismatch")

        map_payload, _ = api.get("/api/v2/map/matches", params)
        map_meta, map_data = _meta(map_payload), _data(map_payload)
        ids = map_data.get("facility_ids")
        if not isinstance(ids, list) or len(ids) > MAX_MAPPED_IDS or any(not isinstance(v, str) for v in ids):
            raise AcceptanceFailure("invalid_map_membership")
        if len(set(ids)) != len(ids):
            raise AcceptanceFailure("duplicate_map_membership")
        if (map_meta.get("manifest_sha256") != contract["manifest_sha256"]
                or map_meta.get("total_count") != expected["total_count"]
                or map_meta.get("mapped_count") != expected["mapped_count"]
                or len(ids) != expected["mapped_count"]):
            raise AcceptanceFailure("source_map_count_mismatch")

        # One member is enough to check detail/search lineage without repeating
        # the full mapped-membership transfer.
        sample_rows = _data(list_payload)
        sample = sample_rows[0] if isinstance(sample_rows, list) and sample_rows else None
        if expected["total_count"] and not isinstance(sample, dict):
            raise AcceptanceFailure("source_sample_missing")
        if sample:
            facility_id = sample.get("facility_id")
            if not isinstance(facility_id, str):
                raise AcceptanceFailure("source_sample_missing")
            detail_payload, _ = api.get(
                "/api/v2/locations/" + urllib.parse.quote(facility_id, safe=""),
                {"release_id": release_id, "profile": profile},
            )
            detail = _data(detail_payload)
            if detail.get("facility_id") != facility_id or detail.get("provenance_source_id") != source_id:
                raise AcceptanceFailure("source_detail_lineage_mismatch")
            if not all(isinstance(detail.get(key), str) and detail[key].strip() for key in (
                "provenance_source_name", "provenance_source_url", "provenance_retrieved_at",
            )):
                raise AcceptanceFailure("source_provenance_incomplete")
            classification = detail.get("taxonomy_primary_categories")
            if not isinstance(classification, list):
                raise AcceptanceFailure("source_classification_missing")
            term = detail.get("canonical_name") or detail.get("city")
            if not isinstance(term, str) or not term.strip():
                raise AcceptanceFailure("source_sample_not_searchable")
            search_payload, _ = api.get("/api/v2/locations", {
                **params, "q": term.strip()[:120], "limit": 1,
            })
            rows = _data(search_payload)
            if not isinstance(rows, list) or not rows:
                raise AcceptanceFailure("source_search_sample_missing")
            if not any(row.get("provenance_source_id") == source_id for row in rows if isinstance(row, dict)):
                raise AcceptanceFailure("source_search_lineage_mismatch")
        if "category_counts" in expected:
            # Explicit taxonomy selectors allow aggregate checks without
            # downloading the release or source rows.
            for selector, count in expected["category_counts"].items():
                selected, _ = api.get("/api/v2/locations", {
                    **params, "category_keys": selector, "limit": 1,
                })
                if _meta(selected).get("total_count") != count:
                    raise AcceptanceFailure("source_classification_count_mismatch")


def _check_graph(api: LocalApi, contract: dict) -> None:
    for expected in contract.get("graph_preservation", []):
        release_id = expected["release_id"]
        source_id = expected.get("source_id")
        entity_id = expected.get("entity_id")
        if not source_id and not entity_id:
            raise AcceptanceFailure("graph_sample_requires_source_or_entity_selector")
        if entity_id and not re.fullmatch(r"[0-9a-fA-F-]{36}", entity_id):
            raise AcceptanceFailure("invalid_graph_entity_selector")
        expected_ruleset = expected.get("ruleset_version")
        cursor = None
        pages = 0
        sampled = 0
        while True:
            params = {"release_id": release_id, "profile": contract["profile"], "limit": 100}
            if source_id:
                params["source_id"] = source_id
            if entity_id:
                params["entity_id"] = entity_id
            if cursor:
                params["cursor"] = cursor
            payload, _ = api.get("/api/v2/graph/connections", params)
            meta = _meta(payload)
            if (meta.get("release_id") != release_id
                    or (expected_ruleset and meta.get("ruleset_version") != expected_ruleset)):
                raise AcceptanceFailure("graph_release_mismatch")
            rows = _data(payload)
            if not isinstance(rows, list):
                raise AcceptanceFailure("invalid_graph_page")
            for row in rows:
                if not isinstance(row, dict):
                    raise AcceptanceFailure("invalid_graph_edge_shape")
                from_node, to_node = row.get("from"), row.get("to")
                if not isinstance(from_node, dict) or not isinstance(to_node, dict):
                    raise AcceptanceFailure("invalid_graph_edge_shape")
                if source_id and source_id not in {from_node.get("source_id"), to_node.get("source_id")}:
                    raise AcceptanceFailure("graph_source_filter_mismatch")
                if entity_id and entity_id not in {from_node.get("entity_id"), to_node.get("entity_id")}:
                    raise AcceptanceFailure("graph_entity_filter_mismatch")
            sampled += len(rows)
            pages += 1
            if pages >= MAX_GRAPH_SAMPLE_PAGES:
                break
            cursor = meta.get("next_cursor")
            if not cursor:
                break
        minimum = _int(expected.get("minimum_sample_edges", 1), "graph_minimum_sample_edges", MAX_GRAPH_SAMPLE_PAGES * 100)
        if sampled < minimum:
            raise AcceptanceFailure("graph_sample_too_small")


def _check_aphis(api: LocalApi, contract: dict) -> None:
    for expected in contract.get("aphis_preservation", []):
        facility_id = expected.get("facility_id")
        kind = expected.get("kind")
        if not isinstance(facility_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", facility_id):
            raise AcceptanceFailure("invalid_aphis_selector")
        if kind not in {"annual_reports", "inspections"}:
            raise AcceptanceFailure("invalid_aphis_kind")
        remaining = _int(expected.get("count"), "aphis_count", MAX_APHIS_PAGES * 100)
        release_id = expected.get("release_id", contract["release_id"])
        cursor = None
        pages = 0
        while True:
            params = {"release_id": release_id, "profile": contract["profile"], "kind": kind, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            payload, _ = api.get(
                "/api/v2/locations/" + facility_id + "/aphis-report-links", params,
            )
            meta = _meta(payload)
            if meta.get("release_id") != release_id or meta.get("kind") != kind:
                raise AcceptanceFailure("aphis_release_or_kind_mismatch")
            rows = _data(payload)
            if not isinstance(rows, list):
                raise AcceptanceFailure("invalid_aphis_page")
            remaining -= len(rows)
            if remaining < 0:
                raise AcceptanceFailure("aphis_count_exceeded")
            pages += 1
            if pages > MAX_APHIS_PAGES:
                raise AcceptanceFailure("aphis_page_budget_exceeded")
            cursor = meta.get("next_cursor")
            if not cursor:
                break
        if remaining:
            raise AcceptanceFailure("aphis_count_mismatch")


def run_acceptance(origin: str, contract: dict) -> dict:
    contract = validate_contract(contract)
    api = LocalApi(origin)
    _manifest(api, contract["release_id"], contract["profile"], contract["manifest_sha256"])
    current, _ = api.get("/api/v2/releases/manifest", {"profile": contract["profile"]})
    current_data = _data(current)
    if (current_data.get("release_id") != contract["release_id"]
            or current_data.get("manifest_sha256") != contract["manifest_sha256"]):
        raise AcceptanceFailure("current_release_mismatch")
    for retained in contract.get("retained_releases", []):
        _check_retained(api, retained, contract["profile"])
    _check_sources(api, contract)
    _check_graph(api, contract)
    _check_aphis(api, contract)
    return {"result": "passed", "source_count": len(contract["sources"]), "request_count": api.requests}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", default=os.getenv("UEC_COUNTRY_RELEASE_API_ORIGIN"))
    parser.add_argument("--contract", default=os.getenv("UEC_COUNTRY_RELEASE_EXPECTED_JSON"))
    args = parser.parse_args(argv)
    if not args.origin or not args.contract:
        parser.error("provide --origin and --contract (or their UEC_COUNTRY_RELEASE_* environment variables)")
    try:
        path = Path(args.contract)
        raw = path.read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            raise AcceptanceFailure("contract_too_large")
        contract = json.loads(raw)
        result = run_acceptance(args.origin, contract)
    except AcceptanceFailure as exc:
        print("country_release_acceptance=failed check=" + str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("country_release_acceptance=failed check=invalid_contract_or_unexpected_failure", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
