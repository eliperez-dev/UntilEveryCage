#!/usr/bin/env python3
"""Export/restore a selected-column public-serving derivative.

Targets must already use normal migrations. This tool never exports raw source,
acquisition, or geocoder payloads, and prints aggregate evidence only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from pipeline.common.release_serving import export_specs, grant_sql, package_manifest  # noqa: E402

OPTIONAL_LEGACY_RELATIONS = {"uec.public_release_history"}
RESTORE_ORDER = (
    "uec.schema_migrations",
    "uec.sources", "uec.raw_artifacts", "uec.source_records", "uec.facilities", "uec.observations",
    "uec.facility_source_links", "uec.releases", "uec.release_manifests", "uec.public_release_history",
    "uec.record_access_events", "uec.publication_review_events", "uec.publication_review_release_scopes",
    "uec.source_rights_decisions",
    "uec.graph_public_evidence_metadata_clearance_events",
    "uec.facility_lifecycle_events", "uec.taxonomy_crosswalks", "uec.release_cohort_review_documents",
    "uec.release_cohort_review_scopes", "uec.observation_taxonomy_assignment_sets",
    "uec.observation_taxonomy_assignments", "uec.public_discovery_read_models",
    "uec.public_discovery_read_model_rows", "uec.public_suppression_generation",
    "uec.graph_public_projection_builds", "uec.graph_public_projection_endpoints",
    "uec.graph_public_projection_edges", "uec.graph_public_projection_edge_supports",
    "uec.graph_public_projection_anchors", "uec.graph_public_projection_evidence_refs",
    "uec.graph_public_projection_org_labels",
    "uec.graph_projection_generation",
)


def _copy_out(connection, spec, releases: list[str], path: Path) -> int:
    query = spec.query.replace("$1", "%s")
    parameters = tuple(releases for _ in range(query.count("%s"))) or None
    with connection.cursor() as cursor:
        count = cursor.execute("SELECT count(*) FROM (" + query + ") selected_rows", parameters).fetchone()[0]
        copy_context = cursor.copy("COPY (" + query + ") TO STDOUT WITH (FORMAT binary)", parameters)
        with copy_context as copy, path.open("wb") as output:
            for block in copy: output.write(block)
    return int(count)


def _payload_descriptor(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as input_file:
        while block := input_file.read(1024 * 1024):
            digest.update(block); size += len(block)
    return {"name": path.name, "sha256": digest.hexdigest(), "byte_size": size}


def _migration_inventory_digest(connection) -> str:
    rows = connection.execute("SELECT version,sha256 FROM uec.schema_migrations ORDER BY version").fetchall()
    inventory = [{"name": f"{version}.sql", "sha256": digest.strip()} for version, digest in rows]
    return hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate_selected_releases(release_ids: list[str], rows) -> None:
    """Require exact, non-test releases that are currently or historically public."""
    selected = set(release_ids)
    by_id = {row[0]: row[1:] for row in rows}
    if set(by_id) != selected:
        raise ValueError("selected release inventory is incomplete")
    for release_id in selected:
        test_only, status, history_present, manifest_digest, read_model_digest = by_id[release_id]
        if test_only is not False or (status != "promoted" and not history_present):
            raise ValueError("selected release is not publicly eligible")
        if not manifest_digest or manifest_digest != read_model_digest:
            raise ValueError("selected release manifest does not match its read model")


def _assert_empty_target(cursor, specs) -> None:
    """Reject reuse of a target that already contains serving data.

    Migrated targets seed two generation singletons. Those may contain only
    their initial zero value; package restore replaces them with the selected
    source generation. Every other allowlisted relation must be empty.
    """
    seeded = {
        "uec.public_suppression_generation": ("singleton", "generation"),
        "uec.graph_projection_generation": ("singleton", "generation"),
    }
    for spec in specs:
        cursor.execute("SELECT count(*) FROM " + spec.relation)
        count = int(cursor.fetchone()[0])
        if spec.relation in seeded:
            cursor.execute("SELECT singleton,generation FROM " + spec.relation)
            rows = cursor.fetchall()
            if count != 1 or rows != [(True, 0)]:
                raise ValueError("target generation singleton is not pristine")
        elif count:
            raise ValueError("target serving relation is not empty")


def export_package(source_url: str, output: Path, releases: list[str], inventory: str, schema_artifacts: dict[str, str] | None = None) -> dict[str, object]:
    import psycopg
    if output.exists(): raise ValueError("package output must not already exist")
    output.mkdir(parents=False); data = output / "data"; data.mkdir()
    counts: dict[str, int] = {}
    try:
        with psycopg.connect(source_url, autocommit=False) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            release_rows = connection.execute(
                "SELECT release.release_id,release.test_only,release.status,"
                "EXISTS (SELECT 1 FROM uec.public_release_history history "
                "WHERE history.release_id=release.release_id AND history.profile=release.profile),"
                "manifest.manifest_sha256,model.manifest_sha256 "
                "FROM uec.releases release "
                "LEFT JOIN uec.release_manifests manifest USING(release_id) "
                "LEFT JOIN uec.public_discovery_read_models model USING(release_id) "
                "WHERE release.release_id=ANY(%s)", (releases,),
            ).fetchall()
            _validate_selected_releases(releases, release_rows)
            specs = []
            for spec in export_specs():
                exists = connection.execute("SELECT to_regclass(%s)", (spec.relation,)).fetchone()[0]
                if exists is None:
                    if spec.relation in OPTIONAL_LEGACY_RELATIONS:
                        continue
                    raise ValueError("source schema is missing required allowlisted relation")
                specs.append(spec)
            for ordinal, spec in enumerate(specs):
                counts[spec.relation] = _copy_out(connection, spec, releases, data / f"{ordinal:02d}.copy")
    except Exception:
        for child in data.glob("*"): child.unlink()
        data.rmdir(); output.rmdir(); raise
    payload_files = [_payload_descriptor(data / f"{ordinal:02d}.copy") for ordinal, _ in enumerate(specs)]
    manifest = package_manifest(release_ids=releases, migration_inventory_sha256=inventory, table_counts=counts, specs=tuple(specs), payload_files=payload_files, schema_artifacts=schema_artifacts)
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {"release_count": len(releases), "relations": len(counts), "rows": sum(counts.values()), "package_sha256": manifest["package_sha256"]}


def restore_package(target_url: str, package: Path, apply_grants: bool) -> dict[str, object]:
    import psycopg
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    known = {spec.relation: spec for spec in export_specs()}
    specs = tuple(known[item["relation"]] for item in manifest.get("data_relation_allowlist", []) if item.get("relation") in known)
    if len(specs) != len(manifest.get("data_relation_allowlist", [])): raise ValueError("package relation allowlist is unsupported")
    payload_files = manifest.get("payload_files")
    if not isinstance(payload_files, list): raise ValueError("package payload inventory is missing")
    schema_derivative = manifest.get("serving_schema_derivative")
    if not isinstance(schema_derivative, dict) or not isinstance(schema_derivative.get("artifacts_sha256"), dict):
        raise ValueError("package schema derivative inventory is missing")
    expected = package_manifest(release_ids=manifest["release_ids"], migration_inventory_sha256=manifest["migration_inventory_sha256"], table_counts=manifest.get("table_counts"), specs=specs, payload_files=payload_files, schema_artifacts=schema_derivative["artifacts_sha256"])
    if manifest.get("package_sha256") != expected["package_sha256"]: raise ValueError("package manifest digest is invalid")
    for item in payload_files:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or "/" in item["name"] or "\\" in item["name"]:
            raise ValueError("package payload inventory is invalid")
        actual = _payload_descriptor(package / "data" / item["name"])
        if actual != item: raise ValueError("package payload digest is invalid")
    copied = 0
    relation = "preflight"
    try:
      with psycopg.connect(target_url, autocommit=False) as connection:
        with connection.cursor() as cursor:
            positions = {spec.relation: ordinal for ordinal, spec in enumerate(specs)}
            _assert_empty_target(cursor, specs)
            for spec in sorted(specs, key=lambda item: RESTORE_ORDER.index(item.relation)):
                relation = spec.relation
                source = package / "data" / f"{positions[spec.relation]:02d}.copy"
                if not source.is_file(): raise ValueError("package data file is missing")
                cursor.execute("SELECT to_regclass(%s)", (spec.relation,))
                if cursor.fetchone()[0] is None: raise ValueError("target schema is missing allowlisted relation")
                # Migration 054 seeds this singleton. Replace only that empty
                # bootstrap value with the source's truthful current generation.
                if spec.relation == "uec.public_suppression_generation":
                    cursor.execute("DELETE FROM uec.public_suppression_generation")
                if spec.relation == "uec.graph_projection_generation":
                    cursor.execute("DELETE FROM uec.graph_projection_generation")
                target_relation = spec.relation
                if spec.relation == "uec.publication_review_release_scopes":
                    cursor.execute("CREATE TEMP TABLE serving_scope_stage (LIKE uec.publication_review_release_scopes) ON COMMIT DROP")
                    target_relation = "serving_scope_stage"
                with cursor.copy("COPY " + target_relation + " (" + ",".join(spec.columns) + ") FROM STDIN WITH (FORMAT binary)") as copy, source.open("rb") as input_file:
                    while block := input_file.read(1024 * 1024): copy.write(block)
                if spec.relation == "uec.schema_migrations" and _migration_inventory_digest(connection) != manifest["migration_inventory_sha256"]:
                    raise ValueError("target migration inventory does not match package")
                if spec.relation == "uec.publication_review_release_scopes":
                    cursor.execute("INSERT INTO uec.publication_review_release_scopes (publication_review_event_id,release_id) SELECT publication_review_event_id,release_id FROM serving_scope_stage ON CONFLICT DO NOTHING")
                    expected = cursor.execute("SELECT count(*) FROM serving_scope_stage").fetchone()[0]
                    actual = cursor.execute("SELECT count(*) FROM uec.publication_review_release_scopes scope JOIN serving_scope_stage stage USING(publication_review_event_id,release_id)").fetchone()[0]
                    if actual != expected: raise ValueError("selected review scope closure did not restore")
                copied += int(manifest["table_counts"].get(spec.relation, 0))
            if apply_grants: cursor.execute(grant_sql())
        connection.commit()
    except Exception as error:
        constraint = getattr(getattr(error, "diag", None), "constraint_name", None)
        suffix = (" constraint=" + constraint) if constraint else ""
        raise ValueError("restore relation failed: " + relation + suffix + " error=" + type(error).__name__) from error
    return {"release_count": len(manifest["release_ids"]), "relations": len(specs), "rows": copied, "package_sha256": manifest["package_sha256"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export"); export.add_argument("--source-database-url-env", required=True); export.add_argument("--release-id", action="append", required=True); export.add_argument("--migration-inventory-sha256", required=True); export.add_argument("--schema-artifact", action="append", default=[], metavar="NAME=SHA256"); export.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore"); restore.add_argument("--target-database-url-env", required=True); restore.add_argument("--package", type=Path, required=True); restore.add_argument("--apply-api-grants", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            source_url = os.environ.get(args.source_database_url_env)
            if not source_url: raise ValueError("source database URL environment variable is unavailable")
            schema_artifacts = {}
            for item in args.schema_artifact:
                name, separator, digest = item.partition("=")
                if not separator or not name or not name.replace("_", "").isalnum(): raise ValueError("schema artifact must be NAME=SHA256")
                schema_artifacts[name] = digest
            result = export_package(source_url, args.output, args.release_id, args.migration_inventory_sha256, schema_artifacts)
        else:
            target_url = os.environ.get(args.target_database_url_env)
            if not target_url: raise ValueError("target database URL environment variable is unavailable")
            result = restore_package(target_url, args.package, args.apply_api_grants)
        print(json.dumps({"status": args.command + "ed", **result}, sort_keys=True)); return 0
    except Exception as error:
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(json.dumps({"status": "blocked", "reason": reason[:160]}, sort_keys=True)); return 2


if __name__ == "__main__": raise SystemExit(main())
