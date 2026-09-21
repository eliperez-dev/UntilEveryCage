# Source redistribution decisions

The release gates require a recorded redistribution decision for every
immutable source artifact that contributes a default-visible row to the
selected release. The decision key is the canonical `source_id`, release
`profile`, `release_id`, and the exact `raw_artifacts.artifact_id` plus its
immutable SHA-256 digest. A release that combines two source snapshots needs
two decisions even when both snapshots use the same source ID.

`uec.source_rights_decisions` is append-only. Each entry records
`cleared`, `unknown`, or `restricted`, an attributable decision actor, a
decision reference, and the decision time. The actor value is an audit
reference; it does not establish that the actor was authorized. The trusted
operator and approval boundary must enforce that separately. No pipeline gate
creates a decision or grants source rights.

The shared gate evaluates all exact requirements. It uses the newest decision
time for each source/artifact/release scope. Multiple decisions at that time
are acceptable only when they agree; conflicting newest decisions are
ambiguous and block. Missing, `unknown`, `restricted`, profile-mismatched,
release-mismatched, and artifact-mismatched decisions block closed-world.
Attribution text remains source metadata and may describe an attribution
obligation, but it never substitutes for a redistribution decision.

Acquisition permission is a separate source or run decision. A permitted
acquisition does not imply redistribution permission, and a cleared
redistribution decision does not authorize a new acquisition. This sprint
checks the decision at validation, promotion, discovery read-model build, and
package export time. It does not implement ongoing revocation or expiry of
already-served releases; those remain launch blockers.
