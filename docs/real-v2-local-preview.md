# Private real V2 local preview

Start with `python scripts/dev.py real-preview up`; inspect with `status` and
`probe`; stop with `python scripts/dev.py real-preview down`. `down` preserves
the isolated database. `python scripts/dev.py real-preview reset` is the
explicit destructive operation and removes only the Compose resources bearing
the exact `uec-real-preview` project and `uec-real-preview-postgres` volume
markers.

The web app listens only on loopback at `http://127.0.0.1:34173/`. The API and
Postgres use loopback ports 38000 and 55432. Expected aggregates are 34,840
facility candidates: 31,990 numeric source-coordinate records and 2,850
city/postal placements. Numeric source coordinates are source claims; they are
not a statement of verified facility entrances. City/postal placement is
coarse and must not be drawn as an invented precise point. Actual imports must
derive and validate their aggregates; startup fails closed on disagreement.

The importer/API integration contract is deliberately narrow. Lane 1 provides
`pipeline/scripts/maintenance/import-real-preview.py`; it accepts
`--root-env UEC_REAL_PREVIEW_ROOT --database-url-env UEC_DATABASE_URL --json`,
reads the private root and DB URL only from those environment variables, verifies retained manifests and
hashes, performs an idempotent private import, and writes exactly one JSON
object containing nonnegative aggregate integer counts to stdout. It must not
write rows, paths, credentials, or tokens to stdout/stderr. Schema migrations
are the repository `pipeline/migrations` applied by
`pipeline/scripts/maintenance/apply-migrations.py --database-url ...` before
the importer runs. The preview API starts as the `uec-api` Cargo binary with
`UEC_RUNTIME_MODE=development`, `UEC_ENABLE_DEV_PREVIEW=true`,
`UEC_BIND_HOST=127.0.0.1`, `UEC_DEV_PREVIEW_TOKEN`, and the preview database
URL. The token is minted per `up`, kept in API process memory, and is passed by
header, never URL or frontend build configuration. Lane 1 must implement a
safe in-memory browser bootstrap that does not expose it through a public
bundle, URL, persistent browser storage, or logs; until that integration is
available the authenticated API probe/import contract is necessary but the
frontend must not be treated as connected.

Select real preview by starting this command. CI synthetic data remains an
explicit test/scenario choice; it is not a fallback for a failed real preview.
The handoffs are private and not project-approved or published. This tool
does not create a release or public projection.

If credentials expire, stop and run `up` again to mint fresh API credentials.
If any loopback port is occupied, stop the identified owner or use a reviewed
port allocation change; this command will not take over a foreign listener.
If handoff hashes drift, repair the retained handoff through its owning
workflow; do not bypass verification. After Docker restarts, use `status`, then
`up`; the database volume is preserved by `down`.
