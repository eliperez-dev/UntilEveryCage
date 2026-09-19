"""Small deterministic helpers for delimited government source artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from collections import Counter
from typing import Any, Iterable


class TabularSchemaError(ValueError):
    """The artifact does not match the source-local tabular contract."""


def canonical_header(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lstrip("\ufeff"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char.lower() for char in text if char.isalnum())


def decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise TabularSchemaError("artifact is not valid UTF-8 or CP1252 text")


def detect_delimiter(text: str) -> str:
    line = next((line for line in text.splitlines() if line.strip()), "")
    scores = {delimiter: line.count(delimiter) for delimiter in (";", "\t", ",", "|")}
    delimiter, score = max(scores.items(), key=lambda item: (item[1], {";": 4, "\t": 3, ",": 2, "|": 1}[item[0]]))
    if score == 0:
        raise TabularSchemaError("could not detect a delimited header")
    return delimiter


def read_rows(content: bytes, aliases: dict[str, Iterable[str]], *, required: Iterable[str]) -> tuple[tuple[str, ...], list[dict[str, str]], str, str]:
    text = decode_text(content)
    delimiter = detect_delimiter(text)
    try:
        reader = csv.DictReader(text.splitlines(), delimiter=delimiter, strict=True)
        headers = tuple(reader.fieldnames or ())
        if not headers or len(set(headers)) != len(headers):
            raise TabularSchemaError("missing or duplicate header columns")
        resolved = resolve_mapping(headers, aliases)
        missing = sorted(set(required) - resolved.keys())
        if missing:
            raise TabularSchemaError("schema drift; missing columns: " + ", ".join(missing))
        rows: list[dict[str, str]] = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise TabularSchemaError("schema drift; row has an inconsistent column count")
            rows.append({str(key): str(value) for key, value in row.items()})
    except csv.Error as error:
        raise TabularSchemaError("malformed delimited artifact") from error
    fingerprint = hashlib.sha256(json.dumps(tuple(canonical_header(header) for header in headers), separators=(",", ":")).encode()).hexdigest()
    return headers, rows, delimiter, fingerprint


def resolve_mapping(headers: Iterable[str], aliases: dict[str, Iterable[str]]) -> dict[str, str]:
    canonical = {canonical_header(header): header for header in headers}
    resolved: dict[str, str] = {}
    alias_map = {field: {canonical_header(alias) for alias in names} for field, names in aliases.items()}
    for field, names in alias_map.items():
        match = next((canonical_name for canonical_name in canonical if canonical_name in names), None)
        if match:
            resolved[field] = canonical[match]
    return resolved


def value(row: dict[str, str], mapping: dict[str, str], field: str) -> str | None:
    source_key = mapping.get(field)
    if source_key is None:
        return None
    raw = row.get(source_key, "")
    return raw.strip() or None


def row_identity(row: dict[str, str], occurrence: int) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{payload}|{occurrence}".encode()).hexdigest()


def occurrence_key(row: dict[str, str], mapping: dict[str, str], fields: Iterable[str]) -> tuple[str | None, ...]:
    return tuple(value(row, mapping, field) for field in fields)


def count_values(rows: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row.get("normalized", {}).get(field) or "unknown") for row in rows)
    return dict(sorted(counts.items()))
