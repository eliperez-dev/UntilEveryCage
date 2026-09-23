# Private real V2 local preview

Start with `python scripts/dev.py real-preview up`; inspect with `status` and
`probe`; stop with `python scripts/dev.py real-preview down`. `down` preserves
the isolated database. `python scripts/dev.py real-preview reset` is the
explicit destructive operation and removes only the Compose resources bearing
the exact `uec-real-preview` project and `uec-real-preview-postgres` volume
markers.

The API and Postgres use loopback ports 38000 and 55432. If the lane-3 frontend
is installed, it listens at `http://127.0.0.1:34173/`; otherwise `up` reports
`backend_ready_frontend_unavailable` after making the API usable. The API exposes
35,073 source-scoped candidate groups (31,990 coordinate groups and 3,083 coarse
groups). Of the coordinate groups, 24,749 have `source-precision-unknown`, 7,241
have `source-provided`, and 486 Italy groups have the source pair `(0,0)`; all
remain approximate and pending review. The separate row-free cross-source union
metric is 34,840 groups (31,990 coordinate and 2,850 coarse) after subtracting
233 France overlap signals. No source records are merged. City/postal placement
is coarse and has no invented point. Imports validate the source grouping and
union metrics against the checked-in aggregate.

France Section II has 1,068 observations and 1,067 distinct establishment
groups. Its selected normalized artifact has SHA-256
`f9f4ed4b9105c01a2985ef41e3c603a9268891d1136619fa031d710cbc560f9d`, matching
the manifest and retained bytes. A prior copy independently has the same hash
and count. The sorted Section II source-row-key hash is
`a5dc1329ded15e8bb919040ee4d85c54d81bb3ecaf41abd259e4d13053d814e9` (1,068
unique keys); its sorted establishment-group-key hash is
`349df50a134549857f9f4000cfa888ecdff8d5cfdd915a9456d8e8bbefcac11e` (1,067
groups). The 233 cross-section overlap keys hash to
`c18f3a1b89da58fd7999296f7475daa23ebe71214e5ac20296cc878d9da5d981`. The
checked-in observation aggregate now records 1,068.

The importer/API integration contract is deliberately narrow. Lane 1 provides
`pipeline/scripts/maintenance/import-real-preview.py`; it accepts an explicit
`--root` plus `--database-url-env UEC_DATABASE_URL --json`, selects only
`d6-graph-mvp/handoffs/{allowlisted-source}/manifest.json`, verifies normalized
artifact hashes, performs an idempotent private import, and writes one
aggregate-only JSON object to stdout. It never selects APHIS. Original source
artifacts are absent from the retained root, so their manifest hashes cannot
be independently verified; the import result records this limitation. The
preview is not provenance-complete and is not a release check. It must not
write rows, paths, credentials, or tokens to stdout/stderr. Schema migrations
are the repository `pipeline/migrations` applied by
`pipeline/scripts/maintenance/apply-migrations.py --database-url ...` before
the importer runs. The preview API starts as the `uec-api` Cargo binary with
`UEC_RUNTIME_MODE=development`, `UEC_DEV_PREVIEW=true`,
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
