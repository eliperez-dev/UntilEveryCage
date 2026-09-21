"""Optional disposable Postgres/PostGIS sink for the D2 synthetic contract.

The sink is deliberately private: it inserts synthetic source evidence and
review-required candidate observations, but never creates a release or a
public read model.  It is only constructed when the caller explicitly passes
the disposable database URL (normally from the Docker E2E fixture).
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Sequence

from pipeline.common.d2_e2e_readiness import FIXTURE_CASES, FIXTURE_VERSION, FixtureCase


COUNTRY_BY_SOURCE = {
    "dk.smiley": "DK",
    "be.locations": "BE",
    "ca.ontario.meat-plants": "CA",
    "ca.cfia.federal-meat": "CA",
    "fr.dgal.section-i": "FR",
    "fr.dgal.section-ii": "FR",
    "it.853-2004": "IT",
}
SYNTHETIC_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_disposable_postgis_sink(database_url: str):
    """Return an aggregate-only sink that is safe to rerun in a test DB.

    ``psycopg`` is imported lazily so non-Docker contract tests do not need a
    database driver.  The returned callable accepts the runner's source ID
    and fixture cases and returns only the number of newly linked candidate
    observations.
    """
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised by env setup
        raise RuntimeError("psycopg is required for --database-url") from exc

    def sink(source_id: str, cases: Sequence[FixtureCase] = FIXTURE_CASES) -> int:
        country = COUNTRY_BY_SOURCE[source_id]
        payload = f"{FIXTURE_VERSION}:{source_id}".encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        inserted_candidates = 0
        with psycopg.connect(database_url) as db:
            with db.transaction():
                db.execute(
                    """INSERT INTO uec.sources
                       (source_id,country_code,name,official_url,access_method,origin_type,status)
                       VALUES (%s,%s,%s,%s,'d2-synthetic-fixture','official','active')
                       ON CONFLICT (source_id) DO NOTHING""",
                    (source_id, country, f"D2 synthetic {source_id}", "https://example.invalid/d2-synthetic"),
                )
                artifact = db.execute(
                    """INSERT INTO uec.raw_artifacts
                       (storage_key,sha256,byte_size,media_type,retrieved_at)
                       VALUES (%s,%s,%s,'application/x-d2-synthetic',%s)
                       ON CONFLICT (sha256) DO UPDATE SET sha256=EXCLUDED.sha256
                       RETURNING artifact_id""",
                    (f"d2-synthetic/{source_id}/{FIXTURE_VERSION}", digest, len(payload), SYNTHETIC_AT),
                ).fetchone()[0]
                run = db.execute(
                    "SELECT run_id FROM uec.acquisition_runs WHERE source_id=%s AND config_version=%s LIMIT 1",
                    (source_id, FIXTURE_VERSION),
                ).fetchone()
                if run is None:
                    run_id = db.execute(
                        """INSERT INTO uec.acquisition_runs
                           (source_id,checked_at,retrieved_at,ingested_at,status,source_url,code_version,config_version)
                           VALUES (%s,%s,%s,%s,'review_required',%s,%s,%s) RETURNING run_id""",
                        (source_id, SYNTHETIC_AT, SYNTHETIC_AT, SYNTHETIC_AT,
                         "https://example.invalid/d2-synthetic", FIXTURE_VERSION, FIXTURE_VERSION),
                    ).fetchone()[0]
                else:
                    run_id = run[0]
                db.execute(
                    "INSERT INTO uec.acquisition_run_artifacts(run_id,artifact_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (run_id, artifact),
                )
                for index, case in enumerate(cases, start=1):
                    key = f"{FIXTURE_VERSION}:{case.display_state}"
                    record = db.execute(
                        """INSERT INTO uec.source_records
                           (source_id,source_record_key,artifact_id,raw_fields,parsed_at,source_state)
                           VALUES (%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (source_id,source_record_key,artifact_id) DO NOTHING
                           RETURNING source_record_id""",
                        (source_id, key, artifact, json.dumps({"synthetic_fixture": True, "display_state": case.display_state}),
                         SYNTHETIC_AT, "rejected" if case.quarantined else "present"),
                    ).fetchone()
                    if record is None:
                        record = db.execute(
                            "SELECT source_record_id FROM uec.source_records WHERE source_id=%s AND source_record_key=%s AND artifact_id=%s",
                            (source_id, key, artifact),
                        ).fetchone()
                    record_id = record[0]
                    if not case.candidate:
                        continue
                    existing = db.execute(
                        "SELECT facility_id FROM uec.facility_source_links WHERE source_record_id=%s LIMIT 1",
                        (record_id,),
                    ).fetchone()
                    if existing is not None:
                        continue
                    facility = db.execute(
                        """INSERT INTO uec.facilities
                           (canonical_name,country_code,city,location)
                           VALUES (%s,%s,'Synthetic City',
                             CASE WHEN %s IN ('exact','city')
                                  THEN ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography
                                  ELSE NULL END)
                           RETURNING facility_id""",
                        (f"D2 synthetic {source_id} {case.display_state}", country, case.display_state,
                         -100.0 + index, 40.0 + index),
                    ).fetchone()[0]
                    db.execute(
                        """INSERT INTO uec.facility_source_links
                           (facility_id,source_record_id,match_method,review_status)
                           VALUES (%s,%s,'d2-synthetic-fixture','review_required')""",
                        (facility, record_id),
                    )
                    coordinate = "ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography" if case.display_state in {"exact", "city"} else "NULL"
                    db.execute(
                        f"""INSERT INTO uec.observations
                            (facility_id,source_record_id,observed_at,observation,classification,
                             ruleset_id,rule_id,classification_category,classification_review_status,
                             default_visible,coordinate,coordinate_method,coordinate_precision,
                             coordinate_review_status,first_observed_at)
                            VALUES (%s,%s,%s,%s,%s,'d2-synthetic','fixture','processing','review_required',false,
                                    {coordinate},'synthetic-fixture',%s,'review_required',%s)""",
                        (facility, record_id, SYNTHETIC_AT, json.dumps({"synthetic_fixture": True}),
                         json.dumps({"display_state": case.display_state}),
                         *(([(-100.0 + index), (40.0 + index)] if coordinate != "NULL" else [])),
                         "exact" if case.display_state == "exact" else "city" if case.display_state == "city" else None,
                         SYNTHETIC_AT),
                    )
                    db.execute(
                        """INSERT INTO uec.publication_review_events
                           (source_record_id,factual_review_status,privacy_screening_status,maintainer_approval,publication_eligible,reviewer_role)
                           VALUES (%s,'unreviewed','pending','pending',false,'d2-synthetic-fixture')""",
                        (record_id,),
                    )
                    inserted_candidates += 1
        return inserted_candidates

    return sink
