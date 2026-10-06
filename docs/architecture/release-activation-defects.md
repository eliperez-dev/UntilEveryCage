# Release activation and recovery contract

Promotion and construction of the public discovery read model are one database
transaction. The promoter serializes activations by profile, rechecks current
rights, review, suppression, coordinate, and publication gates, writes or
revalidates the immutable manifest, selects the new release, and builds its
read model before commit. If any step fails, the transaction restores the
previous release selection and removes the attempted manifest/model writes.
The standalone read-model builder remains available for already promoted
releases; activation calls its shared transaction-level builder on the same
connection.

Reactivation (A→B→A) reuses A's original immutable manifest. Before changing
release state, the promoter verifies the stored manifest digest and compares
its release/profile/ruleset, source coverage and counts, distributed artifact
inventory, map artifact, rights/review state, and suppression generation with
the current candidate inputs. Artifact changes, changed publication state, or
a newer suppression generation block reactivation. The promoter never
rewrites an existing manifest. Map releases must supply the matching map
artifact manifest again when reactivated.

The per-profile transaction lock prevents concurrent promotions from selecting
two active releases or racing their manifest/model writes. A pre-existing
promoted release must have a complete read model whose manifest digest and row
count agree; otherwise replacement is refused. The check does not make
external file distribution atomic. Exporting `--manifest` to the operator's
filesystem remains a separate step after the database transaction, as
described in the [manifest verification contract](release-manifest-verification.md).

These controls do not create review or rights decisions, weaken any release
gate, or prove that listed distribution artifacts were complete. Tests must
exercise interrupted replacement rollback, successful A→B→A reuse, and
rejection of changed artifact and suppression inputs using disposable PostGIS
fixtures; those results establish only the behavior exercised by those tests.
