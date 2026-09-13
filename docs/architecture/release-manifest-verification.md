# Release manifest verification

Every public release must include a machine-readable manifest containing the release ID, profile, ruleset/configuration versions, source coverage, creation time, and SHA-256 checksums for each distributed artifact. Consumers should calculate SHA-256 locally and compare it with the manifest obtained from a trusted project channel.

Checksums detect alteration relative to a trusted reference; they do not prove factual accuracy, privacy eligibility, or government-source correctness. Withdrawn or sanitized artifacts must remain marked and must not be silently replaced. Signing is not claimed until key custody, distribution, rotation, revocation, and compromised-release handling are separately reviewed and tested.
