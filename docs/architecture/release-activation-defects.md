# Deferred release activation reproductions

Sprint 01 keeps the known activation defects visible while the source-rights
gate is added. These are synthetic, private launch blockers; this lane does
not redesign activation or rollback.

## Failed replacement build can remove the active release

Create a promoted release `synthetic-a`, a validated release `synthetic-b`,
and exact cleared source-rights decisions for each artifact in `synthetic-b`.
Run `promote-release.py synthetic-b --no-distributed-artifacts`, then inject a
failure before `build_public_discovery_read_model.py synthetic-b` commits its
model (the builder's `fail_after_rows` hook is the existing injection point).
The current promotion transaction demotes `synthetic-a` before the model is
built. A public read therefore has no usable promoted model after the failed
build. The existing `pipeline/tests/e2e/test_public_discovery_read_model.py`
interruption test proves row/model rollback inside the builder, but does not
claim cross-stage active-release safety.

## Re-promoting an old release collides with its immutable manifest

Promote `synthetic-a`, promote `synthetic-b`, then set `synthetic-a` back to
`validated` in the disposable database without changing its existing
`uec.release_manifests` row. Running `promote-release.py synthetic-a` reaches
the unconditional manifest insert and fails on the manifest primary key. The
immutable manifest is preserved, but the old release cannot be selected again
through the current command. The following sprint must stage validation and
active-release selection so A→B→A and an injected build failure preserve a
usable active service.

These reproductions contain no real records or approvals. Source-rights
validation is still required before either promotion attempt; the fixture
decisions are synthetic and do not authorize publication.
