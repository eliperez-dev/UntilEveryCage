# Source-adapter contract

Adapters receive a preserved raw artifact and `SourceArtifact` facts: source URL,
UTC retrieval time, SHA-256, byte size, supplied publication/effective dates,
code/config versions, rights/privacy caveats, and coverage. They must retain
source values, make uncertainty explicit, quarantine malformed or unresolved
records, and write deterministic parsed/normalized/quarantined JSONL plus a
manifest. The manifest is private staging (`release_state: not-created`);
passing validation is not approval, health, or publication authorization.

Denmark's `DenmarkSmileyAdapter` is the proving implementation. Network
acquisition remains the existing reviewed acquisition command; raw/private
artifacts are intentionally not fixtures or committed data.
