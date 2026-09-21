# D3 evidence-source framework

The shared private refresh runner distinguishes two source kinds:

* `facility_master` describes source-local facility observations that may enter
  the facility candidate handoff after validation.
* `evidence_event` describes dated observations such as registrations,
  inspections, reports, or enforcement events. Evidence events retain
  source-native identifiers and do not assert a canonical facility.

The runner rejects an adapter/capability source-kind mismatch. A facility
handoff cannot enter the evidence sink, and evidence events cannot be sent to
the generic facility candidate importer. The evidence sink is private,
idempotent, review-required, and publication-blocked; it creates no release,
public API rows, map rows, or graph migration.

The D3 APHIS adapters reuse the existing profile-explicit parser and private
handoff workflow:

* `us.aphis` uses the registrations profile.
* `us.inspections` uses the inspections profile while retaining its distinct
  source ID.

Both preserve source-native certificate/customer/report identifiers, event
date or reporting period, evidence type, source-row provenance, and explicit
linkage candidates. Missing event identity remains unresolved and is never
filled with a guessed facility ID. Fixture and preserved-local-artifact modes
are supported; live acquisition remains operator-assisted and fail-closed.

The checked-in fixtures are synthetic contract fixtures only. They do not
represent public source rows, completeness, factual review, privacy approval,
or publication permission.

